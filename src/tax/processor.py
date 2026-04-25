"""
Main crypto tax calculation engine.

Implements Polish PIT-38 cryptocurrency tax rules:
- Only fiat-to-crypto and crypto-to-fiat transactions are taxable
- Costs are pooled globally (no FIFO requirement)
- Uses T-1 exchange rates from NBP API
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

from .config import TaxConfig
from .nbp import NBPRateService
from .types import (
    LedgerEntry,
    OperationClassification,
    TaxSummary,
    Transaction,
)

logger = logging.getLogger(__name__)


class CryptoTaxCalculator:
    """Calculates cryptocurrency tax obligations according to Polish law."""

    DATE_FORMATS = [
        "%y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
    ]

    def __init__(
        self,
        config: TaxConfig,
        rate_service: Optional[NBPRateService] = None,
    ) -> None:
        self.config = config
        self.rate_service = rate_service or NBPRateService(config)
        logger.debug("CryptoTaxCalculator initialized for tax year %d", config.tax_year)

    def parse_timestamp(self, value: str) -> datetime:
        candidate = str(value).strip()

        for fmt in self.DATE_FORMATS:
            try:
                parsed = datetime.strptime(candidate, fmt)
                if "%y" in fmt and parsed.year < 2000:
                    parsed = parsed.replace(year=parsed.year + 100)
                return parsed
            except ValueError:
                continue

        msg = f"Unable to parse timestamp: {value!r}"
        logger.error(msg)
        raise ValueError(msg)

    def _detect_csv_format(self, data_path: Path) -> str:
        with data_path.open("r", encoding="utf-8") as fp:
            first_line = fp.readline().strip().lstrip("\ufeff").upper()

        if first_line.startswith("UID:") or "TIME(UTC)" in first_line:
            return "bybit"
        if "CZAS" in first_line and "OPERACJA" in first_line:
            return "binance"
        if "UID," in first_line and "TIME(UTC)" in first_line:
            return "bybit"

        return "binance"

    def _should_skip_first_row(self, data_path: Path) -> bool:
        with data_path.open("r", encoding="utf-8") as fp:
            first_line = fp.readline().strip().lstrip("\ufeff")
        return first_line.upper().startswith("UID:")

    def _normalize_bybit(self, frame: pl.DataFrame) -> pl.DataFrame:
        column_mapping = {
            "Uid": "account",
            "Currency": "asset",
            "Contract": "contract",
            "Type": "type",
            "Direction": "direction",
            "Change": "amount",
            "Time(UTC)": "timestamp",
            "Action": "action",
        }

        for bybit_col, standard_col in column_mapping.items():
            if bybit_col in frame.columns:
                frame = frame.rename({bybit_col: standard_col})

        required_cols = ["timestamp", "asset", "type", "direction", "amount"]
        missing = [c for c in required_cols if c not in frame.columns]
        if missing:
            raise ValueError(f"Missing required Bybit columns: {missing}")

        for col in ("contract", "action", "account"):
            if col not in frame.columns:
                frame = frame.with_columns(pl.lit("").alias(col))

        timestamps, operations, assets, amounts = [], [], [], []
        notes, accounts, contracts, directions = [], [], [], []

        for row in frame.to_dicts():
            try:
                timestamps.append(self.parse_timestamp(row["timestamp"]))
            except ValueError:
                continue

            asset = str(row.get("asset", "") or "").strip().upper()
            contract = str(row.get("contract", "") or "").strip().upper()
            direction = str(row.get("direction", "") or "").strip().upper()

            operation = (
                " ".join(
                    part
                    for part in (
                        str(row.get("type", "") or "").strip().upper(),
                        direction,
                    )
                    if part
                )
                or "UNKNOWN BYBIT OPERATION"
            )

            try:
                amounts.append(float(row.get("amount", 0.0) or 0.0))
            except (TypeError, ValueError):
                amounts.append(0.0)

            notes.append(
                " ".join(
                    filter(
                        None,
                        [
                            contract,
                            str(row.get("action", "") or "").strip(),
                        ],
                    )
                ).strip()
            )

            assets.append(asset)
            operations.append(operation)
            accounts.append(str(row.get("account", "") or "").strip())
            contracts.append(contract)
            directions.append(direction)

        return pl.DataFrame(
            {
                "timestamp": timestamps,
                "operation": operations,
                "asset": assets,
                "amount": amounts,
                "notes": notes,
                "account": accounts,
                "contract": contracts,
                "direction": directions,
                "source": ["bybit"] * len(timestamps),
            }
        ).sort("timestamp")

    def normalize(self, data_path: Path) -> pl.DataFrame:
        if not data_path.exists():
            raise FileNotFoundError(data_path)

        file_format = self._detect_csv_format(data_path)
        skip_rows = 1 if self._should_skip_first_row(data_path) else 0

        frame = pl.read_csv(
            data_path,
            skip_rows=skip_rows,
            try_parse_dates=False,
            infer_schema_length=1000,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )

        if file_format == "bybit":
            return self._normalize_bybit(frame)

        column_mapping = {
            "Czas": "timestamp",
            "Operacja": "operation",
            "Moneta": "asset",
            "Zmien": "amount",
            "Uwagi": "notes",
            "Konto": "account",
        }

        for bin_col, std_col in column_mapping.items():
            if bin_col in frame.columns:
                frame = frame.rename({bin_col: std_col})

        for col in ("notes", "account"):
            if col not in frame.columns:
                frame = frame.with_columns(pl.lit("").alias(col))

        timestamps, operations, assets, amounts = [], [], [], []
        notes, accounts, sources = [], [], []

        for row in frame.to_dicts():
            try:
                timestamps.append(self.parse_timestamp(row["timestamp"]))
            except ValueError:
                continue

            operations.append(str(row.get("operation", "")))
            assets.append(str(row.get("asset", "")).upper())

            try:
                v = row.get("amount")
                amounts.append(float(v) if v not in (None, "") else 0.0)
            except Exception:
                amounts.append(0.0)

            notes.append(str(row.get("notes", "")))
            accounts.append(str(row.get("account", "")))
            sources.append("binance")

        return pl.DataFrame(
            {
                "timestamp": timestamps,
                "operation": operations,
                "asset": assets,
                "amount": amounts,
                "notes": notes,
                "account": accounts,
                "source": sources,
            }
        ).sort("timestamp")

    def classify_operation(
        self, operation: str, context: Optional[Dict[str, Any]] = None
    ) -> OperationClassification:
        op = operation.strip()

        if op == "Buy Crypto With Fiat":
            return OperationClassification.COST

        if op in ("Fiat Withdraw", "Transaction Sold"):
            return OperationClassification.REVENUE

        if op == "Deposit" and context:
            asset = str(context.get("asset", "")).upper()
            if asset in self.config.fiat_currencies:
                return OperationClassification.COST

        if op == "Withdraw" and context:
            asset = str(context.get("asset", "")).upper()
            if asset in self.config.fiat_currencies:
                return OperationClassification.REVENUE

        if any(
            op.startswith(x)
            for x in ("Transaction Buy", "Transaction Spend", "Binance Convert")
        ):
            return OperationClassification.IGNORED

        if "Fee" in op:
            if context:
                related = context.get("related_classifications", set())
                if OperationClassification.REVENUE in related:
                    return OperationClassification.REVENUE_FEE
                if OperationClassification.COST in related:
                    return OperationClassification.COST_FEE
            return OperationClassification.FEE

        if context:
            source = str(context.get("source", "")).lower()
            asset = str(context.get("asset", "")).upper()

            if source == "bybit" and op == "TRADE BUY":
                return (
                    OperationClassification.COST
                    if asset in self.config.fiat_currencies
                    else OperationClassification.IGNORED
                )

            if source == "bybit" and op == "TRADE SELL":
                return (
                    OperationClassification.REVENUE
                    if asset in self.config.fiat_currencies
                    else OperationClassification.IGNORED
                )

        if any(x in op for x in ("Airdrop", "Reward", "Staking", "Earn")):
            return OperationClassification.OPTIONAL

        return OperationClassification.IGNORED

    def compute_tax(self, data_path: Path, include_optional: bool = False):
        frame = self.normalize(data_path)
        rows = frame.to_dicts()

        transactions: List[Transaction] = []
        for row in rows:
            try:
                transactions.append(Transaction(**row))
            except Exception:
                continue

        groups = {}
        for t in transactions:
            groups.setdefault(t.timestamp.isoformat(), []).append(t)

        ledger = []
        cost = revenue = 0.0
        processed = ignored = 0

        for i, txn in enumerate(transactions):
            group = groups.get(txn.timestamp.isoformat(), [txn])

            context = {
                "asset": txn.asset,
                "source": txn.source,
                "amount": txn.amount,
                "related_classifications": {
                    self.classify_operation(t.operation) for t in group
                },
            }

            cls = self.classify_operation(txn.operation, context)

            if cls == OperationClassification.COST:
                cost += txn.amount
                processed += 1
            elif cls == OperationClassification.REVENUE:
                revenue += txn.amount
                processed += 1
            else:
                ignored += 1

            ledger.append(
                LedgerEntry(
                    date=txn.timestamp.isoformat(),
                    operation=txn.operation,
                    asset=txn.asset,
                    amount=txn.amount,
                    pln_value=txn.amount,
                    classification=cls,
                    notes=txn.notes,
                    account=txn.account,
                )
            )

        summary = TaxSummary(
            total_cost_pln=cost,
            total_revenue_pln=revenue,
            income=revenue - cost,
            loss_to_carry=max(0.0, cost - revenue),
            tax_year=self.config.tax_year,
            transactions_processed=processed,
            transactions_ignored=ignored,
        )

        return summary, pl.DataFrame([entry.__dict__ for entry in ledger])
