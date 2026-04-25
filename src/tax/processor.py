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
from typing import Any, Dict, Iterable, List, Optional, Tuple

import polars as pl

from .config import TaxConfig
from .nbp import NBPRateService
from .types import (
    LedgerEntry,
    OperationClassification,
    OperationType,
    TaxSummary,
    Transaction,
    ValidationError,
)

logger = logging.getLogger(__name__)


class CryptoTaxCalculator:
    """Calculates cryptocurrency tax obligations according to Polish law."""

    # Standard date formats from Binance CSV
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
        """
        Initialize the tax calculator.

        Args:
            config: Tax configuration.
            rate_service: NBP rate service (created if not provided).
        """
        self.config = config
        self.rate_service = rate_service or NBPRateService(config)
        logger.debug("CryptoTaxCalculator initialized for tax year %d", config.tax_year)

    def parse_timestamp(self, value: str) -> datetime:
        """
        Parse timestamp from various formats.

        Args:
            value: Timestamp string.

        Returns:
            Parsed datetime.

        Raises:
            ValueError: If timestamp cannot be parsed.
        """
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
        """Detect the CSV format based on header contents."""
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
        """Return True when the first CSV row contains metadata rather than headers."""
        with data_path.open("r", encoding="utf-8") as fp:
            first_line = fp.readline().strip().lstrip("\ufeff")
        return first_line.upper().startswith("UID:")

    def _normalize_bybit(self, frame: pl.DataFrame) -> pl.DataFrame:
        """Normalize Bybit CSV rows into the standard transaction shape."""
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
            msg = f"Missing required Bybit columns: {missing}"
            logger.error(msg)
            raise ValueError(msg)

        if "contract" not in frame.columns:
            frame = frame.with_columns(pl.lit("").alias("contract"))
        if "action" not in frame.columns:
            frame = frame.with_columns(pl.lit("").alias("action"))
        if "account" not in frame.columns:
            frame = frame.with_columns(pl.lit("").alias("account"))

        timestamps = []
        operations = []
        assets = []
        amounts = []
        notes = []
        accounts = []
        contracts = []
        directions = []

        for row in frame.to_dicts():
            try:
                timestamps.append(self.parse_timestamp(row["timestamp"]))
            except ValueError as e:
                logger.warning("Skipping Bybit row with invalid timestamp: %s", e)
                continue

            asset = str(row.get("asset", "") or "").strip().upper()
            contract = str(row.get("contract", "") or "").strip().upper()
            direction = str(row.get("direction", "") or "").strip().upper()
            currency = asset

            operation = " ".join(
                part
                for part in (
                    str(row.get("type", "") or "").strip().upper(),
                    direction,
                )
                if part
            )
            if not operation:
                operation = "UNKNOWN BYBIT OPERATION"

            try:
                amounts.append(float(row.get("amount", 0.0) or 0.0))
            except (TypeError, ValueError):
                logger.warning("Invalid Bybit amount: %s, using 0.0", row.get("amount"))
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
            assets.append(currency)
            operations.append(operation)
            accounts.append(str(row.get("account", "") or "").strip())
            contracts.append(contract)
            directions.append(direction)

        normalized = pl.DataFrame(
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
        )

        normalized = normalized.sort("timestamp")
        logger.info("Loaded and normalized %d Bybit transactions", normalized.shape[0])
        return normalized

    def normalize(self, data_path: Path) -> pl.DataFrame:
        """
        Normalize and validate transaction data from CSV.

        Performs:
        - Column name standardization
        - Type conversion
        - Chronological sorting
        - Null handling

        Args:
            data_path: Path to Binance-style CSV.

        Returns:
            Normalized Polars DataFrame.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If required columns are missing.
        """
        if not data_path.exists():
            msg = f"Data file not found: {data_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        logger.info("Loading transaction data from %s", data_path)
        
        file_format = self._detect_csv_format(data_path)
        skip_rows = 1 if self._should_skip_first_row(data_path) else 0

        try:
            frame = pl.read_csv(
                data_path,
                skip_rows=skip_rows,
                try_parse_dates=False,
                infer_schema_length=1000,
                ignore_errors=True,
                truncate_ragged_lines=True,
            )
        except Exception as e:
            msg = f"Failed to read CSV: {e}"
            logger.error(msg)
            raise ValueError(msg) from e

        if file_format == "bybit":
            return self._normalize_bybit(frame)

        # Map Binance column names to standardized names
        column_mapping = {
            "Czas": "timestamp",
            "Operacja": "operation",
            "Moneta": "asset",
            "Zmien": "amount",
            "Uwagi": "notes",
            "Konto": "account",
        }

        # Rename columns that exist
        for binance_col, standard_col in column_mapping.items():
            if binance_col in frame.columns:
                frame = frame.rename({binance_col: standard_col})

        # Ensure required columns exist
        required_cols = ["timestamp", "operation", "asset", "amount"]
        missing = [c for c in required_cols if c not in frame.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            logger.error(msg)
            raise ValueError(msg)

        if "notes" not in frame.columns:
            frame = frame.with_columns(pl.lit("").alias("notes"))
        if "account" not in frame.columns:
            frame = frame.with_columns(pl.lit("").alias("account"))

        timestamps = []
        operations = []
        assets = []
        amounts = []
        notes = []
        accounts = []
        sources = []

        for row in frame.to_dicts():
            try:
                timestamps.append(self.parse_timestamp(row["timestamp"]))
            except ValueError as e:
                logger.warning("Skipping row with invalid timestamp: %s", e)
                continue

            operations.append(str(row.get("operation", "")).strip())
            assets.append(str(row.get("asset", "")).strip().upper())
            
            try:
                amount_val = row.get("amount")
                amounts.append(float(amount_val) if amount_val not in (None, "") else 0.0)
            except (ValueError, TypeError):
                logger.warning("Invalid amount: %s, using 0.0", row.get("amount"))
                amounts.append(0.0)

            notes.append(str(row.get("notes", "")).strip())
            accounts.append(str(row.get("account", "")).strip())
            sources.append("binance")

        normalized = pl.DataFrame(
            {
                "timestamp": timestamps,
                "operation": operations,
                "asset": assets,
                "amount": amounts,
                "notes": notes,
                "account": accounts,
                "source": sources,
            }
        )

        normalized = normalized.sort("timestamp")
        logger.info("Loaded and normalized %d transactions", normalized.shape[0])
        return normalized

    def classify_operation(self, operation: str, context: Optional[Dict[str, Any]] = None) -> OperationClassification:
        """
        Classify a transaction for tax purposes.

        Classification rules per Polish tax law:
        - COST: Buying crypto with fiat (increases cost basis)
        - REVENUE: Selling crypto for fiat (generates taxable income)
        - IGNORED: Crypto-to-crypto transfers (not taxable)
        - FEE: Transaction fees (classified based on related operation)

        Args:
            operation: Operation name from CSV.
            context: Additional context (e.g., related operations in same batch).

        Returns:
            Operation classification.
        """
        op = operation.strip()

        # Cost-increasing operations (buying stablecoins with fiat only)
        if op == "Buy Crypto With Fiat":
            if context and isinstance(context, dict):
                asset = str(context.get("asset", "")).strip().upper()
                # Only count if buying stablecoins (fiat equivalent)
                if asset in self.config.stablecoin_map:
                    return OperationClassification.COST
            # Other crypto purchases (e.g., SUI, ETH) are not fiat buys
            return OperationClassification.IGNORED

        # Revenue-generating operations (selling crypto for fiat)
        if op in ("Fiat Withdraw", "Transaction Sold"):
            return OperationClassification.REVENUE

        # Binance deposit/withdraw with fiat should be included
        if op == "Deposit" and context and isinstance(context, dict):
            asset = str(context.get("asset", "")).strip().upper()
            if asset in self.config.fiat_currencies:
                return OperationClassification.COST

        if op in ("Withdraw",) and context and isinstance(context, dict):
            asset = str(context.get("asset", "")).strip().upper()
            if asset in self.config.fiat_currencies:
                return OperationClassification.REVENUE

        # Non-taxable operations (crypto-to-crypto)
        if any(
            op.startswith(token)
            for token in (
                "Transaction Buy",
                "Transaction Spend",
                "Binance Convert",
            )
        ):
            return OperationClassification.IGNORED

        # Fees
        if "Fee" in op:
            # Try to classify based on context
            if context and isinstance(context, dict):
                related_ops = context.get("related_classifications", set())
                if OperationClassification.REVENUE in related_ops:
                    return OperationClassification.REVENUE_FEE
                if OperationClassification.COST in related_ops:
                    return OperationClassification.COST_FEE

            return OperationClassification.FEE

        # Bybit trade lines are taxable only for actual fiat currency trades (not stablecoins).
        # This matches the DBT script which only considers EUR, PLN, USD, GBP as taxable.
        if context and isinstance(context, dict):
            source = str(context.get("source", "")).strip().lower()
            asset = str(context.get("asset", "")).strip().upper()
            amount = float(context.get("amount", 0.0) or 0.0)
            # Only check against actual fiat currencies, not stablecoins
            if source == "bybit" and op == "TRADE BUY":
                if asset in self.config.fiat_currencies:
                    return OperationClassification.COST
                return OperationClassification.IGNORED
            if source == "bybit" and op == "TRADE SELL":
                if asset in self.config.fiat_currencies:
                    return OperationClassification.REVENUE
                return OperationClassification.IGNORED

        # Optional operations (may be treated as income if configured)
        if any(token in op for token in ("Airdrop", "Reward", "Staking", "Earn")):
            return OperationClassification.OPTIONAL

        # Default: ignore unknown operations
        logger.debug("Unknown operation, classifying as ignored: %s", op)
        return OperationClassification.IGNORED

    def _infer_fee_classification(
        self, txn: Transaction, index: int, transactions: List[Transaction]
    ) -> OperationClassification:
        """Infer fee classification from neighboring taxable transactions."""
        for offset in (-1, 1, -2, 2, -3, 3):
            neighbor_index = index + offset
            if neighbor_index < 0 or neighbor_index >= len(transactions):
                continue

            neighbor = transactions[neighbor_index]
            if "Fee" in neighbor.operation:
                continue

            neighbor_class = self.classify_operation(
                neighbor.operation,
                {
                    "asset": neighbor.asset,
                    "amount": neighbor.amount,
                    "source": neighbor.source,
                },
            )
            if neighbor_class == OperationClassification.COST:
                return OperationClassification.COST_FEE
            if neighbor_class == OperationClassification.REVENUE:
                return OperationClassification.REVENUE_FEE

        return OperationClassification.FEE

    def _calculate_pln_value(self, amount: float, asset: str, transaction_date: datetime) -> float:
        """
        Convert amount to PLN using NBP T-1 rate.

        Args:
            amount: Amount in original currency/asset.
            asset: Asset symbol.
            transaction_date: Transaction date.

        Returns:
            Amount in PLN.
        """
        try:
            rate = self.rate_service.get_rate(asset, transaction_date.date())
            pln_value = abs(amount) * rate
            return pln_value
        except ValueError as e:
            logger.warning(
                "Failed to get rate for %s on %s: %s. Using amount as-is.",
                asset,
                transaction_date.date(),
                e,
            )
            return abs(amount)

    def _group_by_timestamp(
        self, transactions: List[Transaction]
    ) -> Dict[str, List[Transaction]]:
        """Group transactions by timestamp to identify related operations."""
        groups: Dict[str, List[Transaction]] = {}
        for txn in transactions:
            key = txn.timestamp.isoformat()
            groups.setdefault(key, []).append(txn)
        return groups

    def compute_tax(
        self, data_path: Path, include_optional: bool = False
    ) -> Tuple[TaxSummary, pl.DataFrame]:
        """
        Compute tax summary and detailed ledger.

        Implements the full tax calculation algorithm:
        1. Load and normalize data
        2. Classify each operation
        3. Convert to PLN using T-1 NBP rates
        4. Track cumulative costs and revenues
        5. Calculate income/loss

        Args:
            data_path: Path to transaction CSV.
            include_optional: Whether to count optional operations as income.

        Returns:
            Tuple of (TaxSummary, detailed ledger DataFrame).
        """
        logger.info("Starting tax calculation for %s", data_path.name)
        
        # Load and normalize
        frame = self.normalize(data_path)
        rows = frame.to_dicts()

        # Convert to Transaction objects
        transactions: List[Transaction] = []
        for i, row in enumerate(rows):
            try:
                txn = Transaction(
                    timestamp=row["timestamp"],
                    operation=row["operation"],
                    asset=row["asset"],
                    amount=row["amount"],
                    source=row.get("source", "binance"),
                    account=row.get("account", ""),
                    notes=row.get("notes", ""),
                    contract=row.get("contract", ""),
                    direction=row.get("direction", ""),
                )
                transactions.append(txn)
            except Exception as e:
                logger.warning("Skipping malformed transaction at row %d: %s", i, e)
                continue

        # Group by timestamp for context-aware classification
        groups = self._group_by_timestamp(transactions)

        # Process each transaction
        ledger_entries: List[LedgerEntry] = []
        total_cost_pln = 0.0
        total_revenue_pln = 0.0
        transactions_processed = 0
        transactions_ignored = 0

        for index, txn in enumerate(transactions):
            # Classify operation
            group_key = txn.timestamp.isoformat()
            group = groups.get(group_key, [txn])
            related_classifications = {
                self.classify_operation(t.operation, {"asset": t.asset, "amount": t.amount, "source": t.source})
                for t in group
                if t.operation != txn.operation
            }
            context = {
                "related_classifications": related_classifications,
                "asset": txn.asset,
                "amount": txn.amount,
                "source": txn.source,
                "contract": txn.contract,
                "direction": txn.direction,
            }
            classification = self.classify_operation(txn.operation, context)
            if classification == OperationClassification.FEE:
                inferred = self._infer_fee_classification(txn, index, transactions)
                classification = inferred

            # Calculate PLN value
            pln_value = self._calculate_pln_value(
                txn.amount,
                txn.asset,
                txn.timestamp,
            )

            # Create ledger entry
            entry = LedgerEntry(
                date=txn.timestamp.isoformat(sep=" "),
                operation=txn.operation,
                asset=txn.asset,
                amount=txn.amount,
                pln_value=pln_value,
                classification=classification,
                notes=txn.notes,
                account=txn.account,
            )
            ledger_entries.append(entry)

            # Update totals based on classification
            if classification == OperationClassification.COST:
                total_cost_pln += pln_value
                transactions_processed += 1
                logger.debug("Cost: +%.2f PLN (%s)", pln_value, txn.asset)

            elif classification == OperationClassification.COST_FEE:
                total_cost_pln += pln_value
                transactions_processed += 1
                logger.debug("Cost fee: +%.2f PLN (%s)", pln_value, txn.asset)

            elif classification == OperationClassification.REVENUE:
                total_revenue_pln += pln_value
                transactions_processed += 1
                logger.debug("Revenue: +%.2f PLN (%s)", pln_value, txn.asset)

            elif classification == OperationClassification.REVENUE_FEE:
                total_revenue_pln -= pln_value  # Fees reduce revenue
                transactions_processed += 1
                logger.debug("Revenue fee: -%.2f PLN (%s)", pln_value, txn.asset)

            elif classification == OperationClassification.OPTIONAL:
                if include_optional:
                    total_revenue_pln += pln_value
                    transactions_processed += 1
                else:
                    transactions_ignored += 1

            else:  # IGNORED or FEE without context
                transactions_ignored += 1

        # Create ledger DataFrame
        ledger_data = [
            {
                "date": e.date,
                "operation": e.operation,
                "asset": e.asset,
                "amount": e.amount,
                "pln_value": round(e.pln_value, 2),
                "type": e.type,
                "notes": e.notes,
                "account": e.account,
            }
            for e in ledger_entries
        ]
        ledger_df = pl.DataFrame(ledger_data)

        # Create summary
        summary = TaxSummary(
            total_cost_pln=round(total_cost_pln, 2),
            total_revenue_pln=round(total_revenue_pln, 2),
            income=round(total_revenue_pln - total_cost_pln, 2),
            loss_to_carry=round(max(0.0, -(total_revenue_pln - total_cost_pln)), 2),
            tax_year=self.config.tax_year,
            transactions_processed=transactions_processed,
            transactions_ignored=transactions_ignored,
        )

        logger.info(
            "Tax calculation completed: %d processed, %d ignored. "
            "Income: %.2f PLN",
            transactions_processed,
            transactions_ignored,
            summary.income,
        )

        return summary, ledger_df

    def export_ledger_csv(self, ledger: pl.DataFrame, output_path: Path) -> None:
        """Export ledger to CSV."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_csv(output_path)
        logger.info("Ledger exported to CSV: %s", output_path)

    def export_ledger_json(self, ledger: pl.DataFrame, output_path: Path) -> None:
        """Export ledger to JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_json(output_path)
        logger.info("Ledger exported to JSON: %s", output_path)

    def export_summary_json(self, summary: TaxSummary, output_path: Path) -> None:
        """
        Export summary to JSON.

        Args:
            summary: Tax summary.
            output_path: Output file path.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        with output_path.open("w", encoding="utf-8") as fp:
            json.dump(summary.to_dict(), fp, indent=2, ensure_ascii=False)
        
        logger.info("Summary exported to JSON: %s", output_path)

