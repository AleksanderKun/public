"""
Type definitions and enums for cryptocurrency tax calculation.

This module defines all data structures used in the tax calculation engine,
including transaction types, operation classifications, and summary statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class OperationClassification(str, Enum):
    """Classification of a transaction for tax purposes."""

    COST = "cost"
    COST_FEE = "cost_fee"
    REVENUE = "revenue"
    REVENUE_FEE = "revenue_fee"
    FEE = "fee"
    IGNORED = "ignored"
    OPTIONAL = "optional"


class OperationType(str, Enum):
    """Binance operation types."""

    BUY_CRYPTO_WITH_FIAT = "Buy Crypto With Fiat"
    FIAT_WITHDRAW = "Fiat Withdraw"
    TRANSACTION_SOLD = "Transaction Sold"
    TRANSACTION_BUY = "Transaction Buy"
    TRANSACTION_SPEND = "Transaction Spend"
    TRANSACTION_FEE = "Transaction Fee"
    TRANSACTION_REVENUE = "Transaction Revenue"
    BINANCE_CONVERT = "Binance Convert"
    DEPOSIT = "Deposit"
    WITHDRAW = "Withdraw"
    AIRDROP = "Airdrop"
    REWARD = "Reward"
    STAKING = "Staking"
    EARN = "Earn"


@dataclass
class TaxConfig:
    """Configuration for tax calculation."""

    fiat_currencies: List[str]
    stablecoin_map: Dict[str, str]
    nbp_table: str
    nbp_base_url: str
    nbp_cache_path: Path
    ignore_operations: List[str]
    optional_operations: List[str]
    tax_year: int = 2026

    def __post_init__(self) -> None:
        """Normalize and validate configuration."""
        self.fiat_currencies = [c.upper() for c in self.fiat_currencies]
        self.stablecoin_map = {
            k.upper(): v.upper() for k, v in self.stablecoin_map.items()
        }


@dataclass
class Transaction:
    """Represents a single transaction from Binance or Bybit CSV."""

    timestamp: datetime
    operation: str
    asset: str
    amount: float
    source: str = "binance"
    account: str = ""
    notes: str = ""
    contract: str = ""
    direction: str = ""

    def __post_init__(self) -> None:
        """Normalize transaction data."""
        self.operation = self.operation.strip()
        self.asset = self.asset.upper().strip()
        self.source = self.source.strip().lower()
        self.account = self.account.strip()
        self.notes = self.notes.strip()
        self.contract = self.contract.strip().upper()
        self.direction = self.direction.strip().upper()


@dataclass
class LedgerEntry:
    """A single row in the tax ledger."""

    date: str
    operation: str
    asset: str
    amount: float
    pln_value: float
    classification: OperationClassification
    notes: str = ""
    account: str = ""

    @property
    def type(self) -> str:
        """Backward compatibility property."""
        return self.classification.value


@dataclass
class TaxSummary:
    """Summary of tax calculation results."""

    total_cost_pln: float = 0.0
    total_revenue_pln: float = 0.0
    income: float = 0.0
    loss_to_carry: float = 0.0
    tax_year: int = 2026
    transactions_processed: int = 0
    transactions_ignored: int = 0

    def __post_init__(self) -> None:
        """Recalculate income based on costs and revenues."""
        self.income = self.total_revenue_pln - self.total_cost_pln
        self.loss_to_carry = max(0.0, -self.income)

    def to_dict(self) -> Dict[str, float | int]:
        """Convert to dictionary for serialization."""
        return {
            "total_cost_pln": round(self.total_cost_pln, 2),
            "total_revenue_pln": round(self.total_revenue_pln, 2),
            "income": round(self.income, 2),
            "loss_to_carry": round(self.loss_to_carry, 2),
            "tax_year": self.tax_year,
            "transactions_processed": self.transactions_processed,
            "transactions_ignored": self.transactions_ignored,
        }


@dataclass
class ValidationError:
    """Represents a validation error in transaction processing."""

    row_number: int
    timestamp: Optional[str]
    message: str
    severity: str = "warning"  # "warning" or "error"
