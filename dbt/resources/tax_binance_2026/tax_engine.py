"""
Tax calculation engine for Polish crypto taxation.

Implements cost pooling, revenue tracking, loss carry-forward, and multi-year
tax calculations per Polish tax law (PIT-38).
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models import (
    NormalizedTransaction,
    TaxEventType,
    TaxYear,
    TaxReport,
)

logger = logging.getLogger(__name__)


class CostPool:
    """
    Global cost pool per Polish tax law.

    Polish law does NOT require FIFO. Instead, costs are pooled globally
    and reduced proportionally by revenue. Unused costs carry forward to
    future years.

    Attributes:
        accumulated_cost_pln: Cumulative fiat spent on crypto purchases
        accumulated_fees_pln: Cumulative fees paid
    """

    def __init__(self, opening_cost_pln: Decimal = Decimal("0")):
        """
        Initialize cost pool.

        Args:
            opening_cost_pln: Opening balance (e.g., unused costs from previous years)
        """
        self.accumulated_cost_pln = opening_cost_pln
        self.accumulated_fees_pln = Decimal("0")
        self.cost_entries: list[dict] = []

        if opening_cost_pln > 0:
            self.cost_entries.append(
                {
                    "date": None,
                    "description": "Opening balance (carried forward)",
                    "amount_pln": opening_cost_pln,
                }
            )

    def add_cost(
        self,
        amount_pln: Decimal,
        date: Optional[object] = None,
        description: str = "Fiat expense",
    ) -> None:
        """
        Add a cost (fiat spent on crypto purchase).

        Args:
            amount_pln: Cost in PLN
            date: Transaction date (for tracking)
            description: Description of cost
        """
        self.accumulated_cost_pln += amount_pln
        self.cost_entries.append(
            {
                "date": date,
                "description": description,
                "amount_pln": amount_pln,
            }
        )
        logger.debug(f"Added cost: {amount_pln} PLN ({description})")

    def add_fee(self, amount_pln: Decimal) -> None:
        """
        Add a fee to cost pool (fees increase cost basis).

        Args:
            amount_pln: Fee in PLN
        """
        self.accumulated_fees_pln += amount_pln
        self.accumulated_cost_pln += amount_pln
        logger.debug(f"Added fee: {amount_pln} PLN")

    def get_total_cost(self) -> Decimal:
        """Get total accumulated cost including fees."""
        return self.accumulated_cost_pln

    def get_details(self) -> list[dict]:
        """Get detailed cost breakdown."""
        return self.cost_entries.copy()

    def reset_for_year(self) -> Decimal:
        """
        Reset pool for new year but return unused costs to carry forward.

        Returns:
            Unused cost to carry to next year
        """
        unused = self.accumulated_cost_pln
        self.accumulated_cost_pln = Decimal("0")
        self.accumulated_fees_pln = Decimal("0")
        self.cost_entries.clear()
        return unused


class TaxCalculationEngine:
    """
    Main tax calculation engine.

    Processes normalized transactions and calculates:
    - Annual tax liability
    - Loss carry-forward
    - Multi-year tax summaries

    Key concept: Polish law uses global cost pooling, not FIFO.
    """

    def __init__(self):
        """Initialize tax engine."""
        self.transactions: list[NormalizedTransaction] = []
        self.years: dict[int, TaxYear] = {}
        self.loss_carryforward: dict[int, Decimal] = {}  # Year -> loss amount

    def add_transaction(self, transaction: NormalizedTransaction) -> None:
        """
        Add a normalized transaction to calculation.

        Args:
            transaction: Normalized transaction
        """
        self.transactions.append(transaction)

    def add_transactions(self, transactions: list[NormalizedTransaction]) -> None:
        """
        Add multiple normalized transactions.

        Args:
            transactions: List of normalized transactions
        """
        self.transactions.extend(transactions)

    def calculate(self) -> TaxReport:
        """
        Calculate tax liability for all transactions.

        Process:
        1. Group transactions by year
        2. For each year, accumulate costs and revenue
        3. Calculate taxable income (revenue - costs - carried losses)
        4. Carry forward losses

        Returns:
            TaxReport with complete calculations
        """
        if not self.transactions:
            logger.warning("No transactions to calculate")
            return TaxReport(
                report_date=datetime.now(),
                years={},
                transactions=[],
            )

        # Group transactions by year
        year_transactions: dict[int, list[NormalizedTransaction]] = {}
        for txn in self.transactions:
            year = txn.timestamp.year
            if year not in year_transactions:
                year_transactions[year] = []
            year_transactions[year].append(txn)

        # Calculate for each year in order
        sorted_years = sorted(year_transactions.keys())

        for year in sorted_years:
            self._calculate_year(year, year_transactions[year])

        # Create report
        report = TaxReport(
            report_date=datetime.now(),
            years=self.years,
            transactions=self.transactions,
        )

        return report

    def _calculate_year(
        self,
        year: int,
        transactions: list[NormalizedTransaction],
    ) -> None:
        """
        Calculate tax for a single year.

        Args:
            year: Tax year
            transactions: Transactions for this year (already sorted)
        """
        logger.info(
            f"Calculating tax for year {year} ({len(transactions)} transactions)"
        )

        tax_year = TaxYear(year=year)
        cost_pool = CostPool()

        # Apply loss carryforward from previous year
        if year - 1 in self.years:
            prev_year_loss = self.years[year - 1].loss
            if prev_year_loss > 0:
                tax_year.loss_from_previous_years = prev_year_loss
                logger.info(
                    f"Carrying forward loss from {year - 1}: {prev_year_loss} PLN"
                )

        # Process transactions
        for txn in transactions:
            if txn.tax_event_type == TaxEventType.COST:
                if txn.pln_value:
                    cost_pool.add_cost(txn.pln_value, txn.timestamp)
                    tax_year.total_costs_pln += txn.pln_value

            elif txn.tax_event_type == TaxEventType.REVENUE:
                if txn.pln_value:
                    tax_year.total_revenue_pln += txn.pln_value

            # Fees are added to cost
            if txn.fee_amount_pln:
                cost_pool.add_fee(txn.fee_amount_pln)
                tax_year.total_fees_pln += txn.fee_amount_pln

            tax_year.transaction_count += 1

        # Store year calculation
        self.years[year] = tax_year

        logger.info(
            f"Year {year} summary: "
            f"Revenue={tax_year.total_revenue_pln} PLN, "
            f"Costs={tax_year.total_costs_pln} PLN, "
            f"Fees={tax_year.total_fees_pln} PLN, "
            f"Taxable Income={tax_year.taxable_income} PLN, "
            f"Tax Due={tax_year.tax_due_19_percent} PLN"
        )


class TaxCalculator:
    """
    High-level tax calculator interface.

    Orchestrates the full calculation pipeline:
    - Data normalization
    - Currency conversion
    - Tax engine execution
    - Report generation
    """

    def __init__(self, engine: Optional[TaxCalculationEngine] = None):
        """
        Initialize calculator.

        Args:
            engine: Optional custom TaxCalculationEngine. If None, creates default.
        """
        self.engine = engine or TaxCalculationEngine()

    def calculate_tax(
        self,
        transactions: list[NormalizedTransaction],
    ) -> TaxReport:
        """
        Calculate tax for given transactions.

        Args:
            transactions: List of normalized transactions

        Returns:
            Complete TaxReport
        """
        # Add transactions to engine
        self.engine.add_transactions(transactions)

        # Calculate
        report = self.engine.calculate()

        return report

    def get_engine(self) -> TaxCalculationEngine:
        """Get underlying calculation engine."""
        return self.engine
