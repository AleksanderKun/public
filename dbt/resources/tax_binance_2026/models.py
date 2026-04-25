"""
Data models for cryptocurrency tax calculation according to Polish tax law (PIT-38).

This module defines the core data structures used throughout the tax calculation process.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from decimal import Decimal


class OperationType(str, Enum):
    """Classification of transaction operations per Polish tax law."""

    # Cost-increasing (fiat → crypto)
    BUY_CRYPTO_WITH_FIAT = "Buy Crypto With Fiat"
    FIAT_DEPOSIT = "Deposit"  # When fiat is deposited

    # Revenue-generating (crypto → fiat)
    FIAT_WITHDRAW = "Fiat Withdraw"
    TRANSACTION_SOLD = "Transaction Sold"
    TRANSACTION_SPEND = "Transaction Spend"

    # Non-taxable
    TRANSACTION_BUY = "Transaction Buy"
    BINANCE_CONVERT = "Binance Convert"
    DEPOSIT_CRYPTO = "Deposit"  # When crypto is deposited (transfer)
    WITHDRAW_CRYPTO = "Withdraw"  # When crypto is withdrawn (transfer)

    # Optional / special handling
    AIRDROP = "Airdrop Assets"
    REWARD = "Reward"
    STAKING = "Staking"
    EARNING = "Earn"

    # Fees
    TRANSACTION_FEE = "Transaction Fee"
    COMMISSION = "Commission"


class TaxEventType(str, Enum):
    """Classification of taxable events per Polish law."""

    COST = "KOSZT"  # Cost (fiat spent on crypto purchase)
    REVENUE = "PRZYCHÓD"  # Revenue (fiat received from crypto sale)
    IGNORED = "IGNOROWANE"  # Non-taxable event
    OPTIONAL = "OPCJONALNE"  # Optional (airdrop, staking, etc.)


@dataclass
class Transaction:
    """
    Represents a single transaction from Binance export.

    Attributes:
        timestamp: Transaction date/time
        operation: Type of operation
        asset: Cryptocurrency or fiat symbol
        amount: Transaction amount (can be negative)
        original_row: Raw row data for traceability
    """

    timestamp: datetime
    operation: str
    asset: str
    amount: Decimal
    original_row: Optional[dict] = None

    def __post_init__(self):
        """Validate transaction data."""
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))

        if self.amount == 0:
            raise ValueError("Transaction amount cannot be zero")


@dataclass
class NormalizedTransaction:
    """
    Transaction after normalization and classification.

    Attributes:
        timestamp: Normalized datetime
        operation_type: Classified operation type
        tax_event_type: Whether this is a cost, revenue, or ignored event
        asset: Normalized asset symbol
        amount: Absolute amount
        currency: Fiat currency (if applicable)
        pln_value: Calculated PLN value (if applicable)
        exchange_rate: Applied exchange rate (T-1)
        rate_date: Date for which rate was applied
        fee_amount_pln: Associated fees in PLN (if applicable)
    """

    timestamp: datetime
    operation_type: OperationType
    tax_event_type: TaxEventType
    asset: str
    amount: Decimal
    currency: Optional[str] = None
    pln_value: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None
    rate_date: Optional[datetime] = None
    fee_amount_pln: Optional[Decimal] = None
    original_row: Optional[dict] = None

    def __post_init__(self):
        """Validate normalized transaction."""
        if self.pln_value is not None and self.pln_value < 0:
            raise ValueError("PLN value cannot be negative")


@dataclass
class TaxYear:
    """
    Tax summary for a single year.

    Attributes:
        year: Tax year
        total_costs_pln: Total fiat spent on crypto purchases
        total_revenue_pln: Total fiat received from crypto sales
        total_fees_pln: Total fees paid
        transaction_count: Number of taxable transactions
        loss_from_previous_years: Loss carried forward from previous years
    """

    year: int
    total_costs_pln: Decimal = Decimal("0")
    total_revenue_pln: Decimal = Decimal("0")
    total_fees_pln: Decimal = Decimal("0")
    transaction_count: int = 0
    loss_from_previous_years: Decimal = Decimal("0")

    @property
    def total_cost_with_fees(self) -> Decimal:
        """Cost including fees."""
        return self.total_costs_pln + self.total_fees_pln

    @property
    def taxable_income(self) -> Decimal:
        """Taxable income = revenue - total costs (including fees) - carried losses."""
        income = self.total_revenue_pln - self.total_cost_with_fees
        return max(income - self.loss_from_previous_years, Decimal("0"))

    @property
    def loss(self) -> Decimal:
        """Loss to carry forward."""
        income = self.total_revenue_pln - self.total_cost_with_fees
        if income < 0:
            return abs(income)
        return Decimal("0")

    @property
    def tax_due_19_percent(self) -> Decimal:
        """Tax due at 19% PIT rate."""
        return self.taxable_income * Decimal("0.19")


@dataclass
class TaxReport:
    """
    Complete tax report for one or more years.

    Attributes:
        report_date: Date report was generated
        years: Dictionary of TaxYear objects keyed by year
        transactions: List of normalized transactions used in calculation
        exchange_rates_used: Dictionary of exchange rates applied
    """

    report_date: datetime
    years: dict[int, TaxYear] = field(default_factory=dict)
    transactions: list[NormalizedTransaction] = field(default_factory=list)
    exchange_rates_used: dict[str, dict[str, Decimal]] = field(default_factory=dict)

    def get_multi_year_summary(self) -> dict:
        """Generate multi-year tax summary."""
        total_costs = sum(ty.total_costs_pln for ty in self.years.values())
        total_revenue = sum(ty.total_revenue_pln for ty in self.years.values())
        total_fees = sum(ty.total_fees_pln for ty in self.years.values())
        total_taxable_income = sum(ty.taxable_income for ty in self.years.values())
        total_tax = sum(ty.tax_due_19_percent for ty in self.years.values())

        return {
            "total_costs_pln": total_costs,
            "total_revenue_pln": total_revenue,
            "total_fees_pln": total_fees,
            "total_taxable_income": total_taxable_income,
            "total_tax_due": total_tax,
            "transaction_count": len(self.transactions),
            "years_covered": sorted(self.years.keys()),
        }


@dataclass
class ValidationError:
    """Represents a data validation error."""

    row_index: int
    error_type: str
    message: str
    original_data: Optional[dict] = None
