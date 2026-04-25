"""
Data processing and normalization for Binance CSV exports.

Handles parsing, validation, normalization, and classification of transactions
according to Polish crypto tax law.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models import (
    NormalizedTransaction,
    OperationType,
    TaxEventType,
    ValidationError,
)

logger = logging.getLogger(__name__)


class OperationClassifier:
    """
    Classifies transactions as cost, revenue, or ignored per Polish tax law.

    Per Polish law (PIT-38 as of 2026):
    - Crypto → Crypto: NOT taxable
    - Crypto → Fiat: taxable (revenue)
    - Fiat → Crypto: increases cost basis
    - Fees: increase cost if acquisition-related, reduce revenue if sale-related

    Key principle: Global cost pooling (not FIFO).
    Unused costs carry over to future years.
    """

    # Standard fiat currencies recognized by Polish tax authority
    FIAT_CURRENCIES = {"PLN", "USD", "EUR", "GBP", "CHF", "JPY", "AUD", "CAD"}

    # Operations that increase cost basis
    COST_INCREASING_OPS = {
        OperationType.BUY_CRYPTO_WITH_FIAT,
        OperationType.FIAT_DEPOSIT,
    }

    # Operations that generate taxable revenue
    REVENUE_GENERATING_OPS = {
        OperationType.FIAT_WITHDRAW,
        OperationType.TRANSACTION_SOLD,
        OperationType.TRANSACTION_SPEND,  # Spending crypto is disposal
    }

    # Operations that are explicitly non-taxable
    NON_TAXABLE_OPS = {
        OperationType.TRANSACTION_BUY,  # Crypto-crypto swap
        OperationType.BINANCE_CONVERT,  # Crypto-crypto swap
        OperationType.DEPOSIT_CRYPTO,  # Transfer in
        OperationType.WITHDRAW_CRYPTO,  # Transfer out
    }

    # Optional operations (may be taxable depending on config)
    OPTIONAL_OPS = {
        OperationType.AIRDROP,
        OperationType.REWARD,
        OperationType.STAKING,
        OperationType.EARNING,
    }

    def __init__(self, treat_airdrops_as_income: bool = False):
        """
        Initialize classifier.

        Args:
            treat_airdrops_as_income: If True, treat airdrops as taxable income.
                                      If False (default), ignore them per conservative
                                      interpretation of Polish law.
        """
        self.treat_airdrops_as_income = treat_airdrops_as_income

    def classify(self, operation_name: str) -> OperationType:
        """
        Map raw operation name to OperationType enum.

        Binance export operation names vary slightly, so this does fuzzy matching.

        Args:
            operation_name: Raw operation name from CSV

        Returns:
            Classified OperationType

        Raises:
            ValueError: If operation cannot be classified
        """
        op_upper = operation_name.strip().upper()

        # Direct match attempts
        for op_type in OperationType:
            if op_type.value.upper() == op_upper:
                return op_type

        # Fuzzy matching for common variations
        if "BUY" in op_upper and "FIAT" in op_upper:
            return OperationType.BUY_CRYPTO_WITH_FIAT
        if "FIAT" in op_upper and ("WITHDRAW" in op_upper or "SELL" in op_upper):
            return OperationType.FIAT_WITHDRAW
        if "SOLD" in op_upper:
            return OperationType.TRANSACTION_SOLD
        if "SPEND" in op_upper:
            return OperationType.TRANSACTION_SPEND
        if "CONVERT" in op_upper:
            return OperationType.BINANCE_CONVERT
        if "BUY" in op_upper and "CRYPTO" in op_upper:
            return OperationType.TRANSACTION_BUY
        if "AIRDROP" in op_upper:
            return OperationType.AIRDROP
        if "REWARD" in op_upper or "EARNING" in op_upper:
            return OperationType.REWARD
        if "STAKING" in op_upper:
            return OperationType.STAKING
        if "FEE" in op_upper or "COMMISSION" in op_upper:
            return OperationType.TRANSACTION_FEE

        raise ValueError(f"Unknown operation type: {operation_name}")

    def get_tax_event_type(
        self,
        operation_type: OperationType,
        asset: str,
    ) -> TaxEventType:
        """
        Determine if transaction is a cost, revenue, or ignored event.

        Args:
            operation_type: Classified operation type
            asset: Asset symbol (crypto or fiat)

        Returns:
            TaxEventType classification
        """
        if operation_type in self.COST_INCREASING_OPS:
            return TaxEventType.COST

        if operation_type in self.REVENUE_GENERATING_OPS:
            return TaxEventType.REVENUE

        if operation_type in self.NON_TAXABLE_OPS:
            return TaxEventType.IGNORED

        if operation_type in self.OPTIONAL_OPS:
            if (
                self.treat_airdrops_as_income
                and operation_type == OperationType.AIRDROP
            ):
                return TaxEventType.REVENUE
            return TaxEventType.OPTIONAL

        if operation_type == OperationType.TRANSACTION_FEE:
            # Fees are absorbed into cost or revenue, not separate
            return TaxEventType.COST

        return TaxEventType.IGNORED

    def is_fiat_asset(self, asset: str) -> bool:
        """Check if asset is a fiat currency."""
        return asset.upper() in self.FIAT_CURRENCIES


class DataNormalizer:
    """
    Normalizes raw Binance CSV data.

    Handles:
    - Parsing datetime strings
    - Converting amounts to Decimal
    - Validating data integrity
    - Normalizing column names
    """

    # Expected columns in Binance CSV
    EXPECTED_COLUMNS = {
        "Czas",  # Timestamp
        "Operacja",  # Operation
        "Moneta",  # Asset/Coin
        "Zmien",  # Amount (Change)
    }

    def __init__(self):
        """Initialize normalizer."""
        self.validation_errors: list[ValidationError] = []

    def normalize_row(
        self,
        row: dict,
        row_index: int,
        classifier: OperationClassifier,
    ) -> Optional[NormalizedTransaction]:
        """
        Normalize a single row from Binance CSV.

        Args:
            row: Dictionary with keys: Czas, Operacja, Moneta, Zmien
            row_index: Row number (for error reporting)
            classifier: OperationClassifier instance

        Returns:
            NormalizedTransaction or None if validation fails
        """
        try:
            # Validate required fields
            if not all(col in row for col in self.EXPECTED_COLUMNS):
                missing = self.EXPECTED_COLUMNS - set(row.keys())
                self._add_error(
                    row_index, "missing_columns", f"Missing columns: {missing}", row
                )
                return None

            # Parse timestamp
            try:
                # Binance format: "2026-01-15 14:32:05"
                timestamp = datetime.strptime(row["Czas"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Try alternative format
                try:
                    timestamp = datetime.fromisoformat(row["Czas"])
                except ValueError:
                    self._add_error(
                        row_index,
                        "invalid_timestamp",
                        f"Cannot parse timestamp: {row['Czas']}",
                        row,
                    )
                    return None

            # Parse amount
            try:
                amount = Decimal(str(row["Zmien"]))
            except (ValueError, TypeError):
                self._add_error(
                    row_index,
                    "invalid_amount",
                    f"Cannot parse amount: {row['Zmien']}",
                    row,
                )
                return None

            if amount == 0:
                self._add_error(
                    row_index, "zero_amount", "Transaction amount is zero", row
                )
                return None

            # Classify operation
            try:
                operation_type = classifier.classify(row["Operacja"])
            except ValueError as e:
                self._add_error(row_index, "unknown_operation", str(e), row)
                return None

            # Normalize asset
            asset = row["Moneta"].strip().upper()

            # Determine tax event type
            tax_event_type = classifier.get_tax_event_type(operation_type, asset)

            # Determine currency (if fiat-related)
            currency = asset if classifier.is_fiat_asset(asset) else None

            # Create normalized transaction
            normalized = NormalizedTransaction(
                timestamp=timestamp,
                operation_type=operation_type,
                tax_event_type=tax_event_type,
                asset=asset,
                amount=abs(amount),  # Always store absolute value
                currency=currency,
                original_row=row,
            )

            return normalized

        except Exception as e:
            self._add_error(
                row_index, "unexpected_error", f"Unexpected error: {str(e)}", row
            )
            return None

    def _add_error(
        self,
        row_index: int,
        error_type: str,
        message: str,
        original_data: Optional[dict] = None,
    ) -> None:
        """Record a validation error."""
        error = ValidationError(
            row_index=row_index,
            error_type=error_type,
            message=message,
            original_data=original_data,
        )
        self.validation_errors.append(error)
        logger.warning(f"Row {row_index}: {error_type} - {message}")

    def get_errors(self) -> list[ValidationError]:
        """Get all validation errors."""
        return self.validation_errors.copy()

    def has_errors(self) -> bool:
        """Check if there are any validation errors."""
        return len(self.validation_errors) > 0

    def clear_errors(self) -> None:
        """Clear error list."""
        self.validation_errors.clear()
