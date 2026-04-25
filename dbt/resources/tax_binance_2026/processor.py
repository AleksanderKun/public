"""
Data processing pipeline for cryptocurrency transactions.

Orchestrates the full workflow:
1. Data loading and validation
2. Data normalization and classification
3. Currency conversion via NBP
4. Tax calculation
5. Report generation
"""

import csv
import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from models import NormalizedTransaction, TaxEventType
from normalizer import OperationClassifier, DataNormalizer
from nbp_provider import NBPRateProvider
from tax_engine import TaxCalculationEngine, TaxReport

logger = logging.getLogger(__name__)


class DataProcessor:
    """
    Main data processing pipeline.

    Responsible for:
    - Loading Binance CSV exports
    - Validating data
    - Normalizing and classifying transactions
    - Converting currencies to PLN
    - Calculating taxes
    - Generating reports
    """

    def __init__(
        self,
        nbp_provider: Optional[NBPRateProvider] = None,
        classifier: Optional[OperationClassifier] = None,
        treat_airdrops_as_income: bool = False,
    ):
        """
        Initialize data processor.

        Args:
            nbp_provider: NBP rate provider. If None, creates default in-memory.
            classifier: Operation classifier. If None, creates default.
            treat_airdrops_as_income: Whether to treat airdrops as taxable income.
        """
        self.nbp_provider = nbp_provider or NBPRateProvider()
        self.classifier = classifier or OperationClassifier(
            treat_airdrops_as_income=treat_airdrops_as_income
        )
        self.normalizer = DataNormalizer()
        self.engine = TaxCalculationEngine()

        self.loaded_transactions: list[dict] = []
        self.normalized_transactions: list[NormalizedTransaction] = []
        self.tax_report: Optional[TaxReport] = None

    def load_csv(self, csv_path: Path) -> int:
        """
        Load Binance CSV export.

        Expected columns: Czas, Operacja, Moneta, Zmien

        Args:
            csv_path: Path to Binance CSV file

        Returns:
            Number of transactions loaded

        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        logger.info(f"Loading CSV from {csv_path}")
        self.loaded_transactions = []

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                # Validate columns
                if not reader.fieldnames:
                    raise ValueError("CSV file has no header")

                expected_columns = DataNormalizer.EXPECTED_COLUMNS
                csv_columns = set(reader.fieldnames)

                if not expected_columns.issubset(csv_columns):
                    missing = expected_columns - csv_columns
                    raise ValueError(f"CSV missing required columns: {missing}")

                # Load rows
                for row in reader:
                    self.loaded_transactions.append(row)

        except csv.Error as e:
            raise ValueError(f"CSV parsing error: {e}")

        logger.info(f"Loaded {len(self.loaded_transactions)} transactions from CSV")
        return len(self.loaded_transactions)

    def normalize_and_classify(self) -> tuple[int, int]:
        """
        Normalize and classify all loaded transactions.

        Performs:
        1. Data validation
        2. Column normalization
        3. Operation classification
        4. Tax event type determination

        Returns:
            Tuple of (successful normalizations, validation errors)
        """
        if not self.loaded_transactions:
            logger.warning("No transactions to normalize")
            return 0, 0

        logger.info(f"Normalizing {len(self.loaded_transactions)} transactions...")
        self.normalized_transactions = []
        self.normalizer.clear_errors()

        for idx, row in enumerate(self.loaded_transactions, start=1):
            normalized = self.normalizer.normalize_row(row, idx, self.classifier)
            if normalized:
                self.normalized_transactions.append(normalized)

        success_count = len(self.normalized_transactions)
        error_count = len(self.normalizer.get_errors())

        logger.info(
            f"Normalization complete: {success_count} successful, {error_count} errors"
        )

        if error_count > 0:
            logger.warning("Normalization errors:")
            for error in self.normalizer.get_errors():
                logger.warning(
                    f"  Row {error.row_index}: {error.error_type} - {error.message}"
                )

        return success_count, error_count

    def apply_currency_conversion(self) -> int:
        """
        Convert all non-PLN values to PLN using NBP rates.

        Applies T-1 rule: use exchange rate from day before transaction.

        Returns:
            Number of transactions with currency conversion applied
        """
        if not self.normalized_transactions:
            logger.warning("No normalized transactions to convert")
            return 0

        logger.info(
            f"Applying currency conversion for {len(self.normalized_transactions)} transactions..."
        )
        converted_count = 0

        for txn in self.normalized_transactions:
            # Skip if no currency conversion needed
            if txn.currency is None or txn.currency == "PLN":
                if txn.tax_event_type != TaxEventType.IGNORED:
                    # Non-fiat transactions don't get PLN value
                    txn.pln_value = Decimal("0")
                continue

            # Get exchange rate
            rate, rate_date = self.nbp_provider.get_rate(txn.currency, txn.timestamp)

            # Calculate PLN value
            pln_value = txn.amount * rate
            txn.pln_value = pln_value
            txn.exchange_rate = rate
            txn.rate_date = rate_date

            converted_count += 1

            logger.debug(
                f"{txn.timestamp.date()} {txn.asset}: "
                f"{txn.amount} {txn.currency} = {pln_value} PLN (rate={rate})"
            )

        logger.info(f"Currency conversion applied to {converted_count} transactions")
        return converted_count

    def calculate_tax(self) -> TaxReport:
        """
        Calculate tax liability.

        Must call normalize_and_classify() and apply_currency_conversion() first.

        Returns:
            Complete TaxReport

        Raises:
            RuntimeError: If pipeline not complete
        """
        if not self.normalized_transactions:
            raise RuntimeError(
                "No transactions to calculate. Call normalize_and_classify() first."
            )

        logger.info("Calculating tax...")
        self.tax_report = self.engine.calculate_tax(self.normalized_transactions)

        logger.info("Tax calculation complete")
        return self.tax_report

    def process(self, csv_path: Path) -> TaxReport:
        """
        Full processing pipeline: load → normalize → convert → calculate.

        Args:
            csv_path: Path to Binance CSV file

        Returns:
            Complete TaxReport

        Raises:
            Various exceptions for data or processing issues
        """
        logger.info("Starting full processing pipeline...")

        # Step 1: Load CSV
        self.load_csv(csv_path)

        # Step 2: Normalize and classify
        success, errors = self.normalize_and_classify()
        if errors > 0:
            logger.warning(f"Processing continued with {errors} validation errors")

        # Step 3: Convert currencies
        self.apply_currency_conversion()

        # Step 4: Calculate tax
        self.tax_report = self.calculate_tax()

        logger.info("Processing pipeline complete")
        return self.tax_report

    def get_report(self) -> Optional[TaxReport]:
        """Get current tax report."""
        return self.tax_report

    def get_validation_errors(self) -> list:
        """Get data validation errors."""
        return self.normalizer.get_errors()

    def get_transaction_count(self) -> int:
        """Get number of processed transactions."""
        return len(self.normalized_transactions)
