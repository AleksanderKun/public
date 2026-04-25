"""
Unit tests for cryptocurrency tax calculation module.

Tests cover:
- Data models and validation
- Operation classification
- Currency conversion
- Tax calculation
- Cost pooling
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from models import (
    Transaction,
    NormalizedTransaction,
    OperationType,
    TaxEventType,
    TaxYear,
)
from normalizer import OperationClassifier, DataNormalizer
from nbp_provider import NBPRateProvider
from tax_engine import CostPool, TaxCalculationEngine


class TestTransaction(unittest.TestCase):
    """Tests for Transaction model."""
    
    def test_transaction_creation(self):
        """Test creating a valid transaction."""
        txn = Transaction(
            timestamp=datetime(2026, 1, 15),
            operation="Buy Crypto With Fiat",
            asset="BTC",
            amount=Decimal("1.5"),
        )
        
        self.assertEqual(txn.asset, "BTC")
        self.assertEqual(txn.amount, Decimal("1.5"))
    
    def test_transaction_amount_conversion(self):
        """Test that amounts are converted to Decimal."""
        txn = Transaction(
            timestamp=datetime(2026, 1, 15),
            operation="Buy Crypto With Fiat",
            asset="BTC",
            amount="1.5",
        )
        
        self.assertIsInstance(txn.amount, Decimal)
        self.assertEqual(txn.amount, Decimal("1.5"))
    
    def test_transaction_zero_amount_fails(self):
        """Test that zero amounts are rejected."""
        with self.assertRaises(ValueError):
            Transaction(
                timestamp=datetime(2026, 1, 15),
                operation="Buy Crypto With Fiat",
                asset="BTC",
                amount=Decimal("0"),
            )


class TestOperationClassifier(unittest.TestCase):
    """Tests for OperationClassifier."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.classifier = OperationClassifier()
    
    def test_classify_buy_crypto(self):
        """Test classifying 'Buy Crypto With Fiat' operation."""
        op_type = self.classifier.classify("Buy Crypto With Fiat")
        self.assertEqual(op_type, OperationType.BUY_CRYPTO_WITH_FIAT)
    
    def test_classify_fiat_withdraw(self):
        """Test classifying 'Fiat Withdraw' operation."""
        op_type = self.classifier.classify("Fiat Withdraw")
        self.assertEqual(op_type, OperationType.FIAT_WITHDRAW)
    
    def test_classify_transaction_sold(self):
        """Test classifying 'Transaction Sold' operation."""
        op_type = self.classifier.classify("Transaction Sold")
        self.assertEqual(op_type, OperationType.TRANSACTION_SOLD)
    
    def test_classify_crypto_transfer(self):
        """Test classifying crypto transfer operations."""
        op_buy = self.classifier.classify("Transaction Buy")
        self.assertEqual(op_buy, OperationType.TRANSACTION_BUY)
    
    def test_classify_airdrop(self):
        """Test classifying airdrop operation."""
        op_type = self.classifier.classify("Airdrop Assets")
        self.assertEqual(op_type, OperationType.AIRDROP)
    
    def test_unknown_operation_fails(self):
        """Test that unknown operations raise ValueError."""
        with self.assertRaises(ValueError):
            self.classifier.classify("Unknown Operation Type")
    
    def test_get_tax_event_type_cost(self):
        """Test classifying cost events."""
        tax_type = self.classifier.get_tax_event_type(
            OperationType.BUY_CRYPTO_WITH_FIAT,
            "BTC"
        )
        self.assertEqual(tax_type, TaxEventType.COST)
    
    def test_get_tax_event_type_revenue(self):
        """Test classifying revenue events."""
        tax_type = self.classifier.get_tax_event_type(
            OperationType.FIAT_WITHDRAW,
            "USD"
        )
        self.assertEqual(tax_type, TaxEventType.REVENUE)
    
    def test_get_tax_event_type_ignored(self):
        """Test classifying ignored (non-taxable) events."""
        tax_type = self.classifier.get_tax_event_type(
            OperationType.TRANSACTION_BUY,
            "BTC"
        )
        self.assertEqual(tax_type, TaxEventType.IGNORED)
    
    def test_is_fiat_asset(self):
        """Test fiat currency detection."""
        self.assertTrue(self.classifier.is_fiat_asset("USD"))
        self.assertTrue(self.classifier.is_fiat_asset("EUR"))
        self.assertTrue(self.classifier.is_fiat_asset("PLN"))
        self.assertFalse(self.classifier.is_fiat_asset("BTC"))
        self.assertFalse(self.classifier.is_fiat_asset("ETH"))


class TestCostPool(unittest.TestCase):
    """Tests for CostPool."""
    
    def test_cost_pool_creation(self):
        """Test creating cost pool."""
        pool = CostPool()
        self.assertEqual(pool.get_total_cost(), Decimal("0"))
    
    def test_add_cost(self):
        """Test adding costs to pool."""
        pool = CostPool()
        
        pool.add_cost(Decimal("1000"), description="Purchase 1")
        pool.add_cost(Decimal("2000"), description="Purchase 2")
        
        self.assertEqual(pool.get_total_cost(), Decimal("3000"))
    
    def test_add_fee(self):
        """Test that fees increase cost basis."""
        pool = CostPool()
        
        pool.add_cost(Decimal("1000"))
        pool.add_fee(Decimal("50"))
        
        self.assertEqual(pool.get_total_cost(), Decimal("1050"))
        self.assertEqual(pool.accumulated_fees_pln, Decimal("50"))
    
    def test_opening_balance(self):
        """Test cost pool with opening balance (carried forward loss)."""
        pool = CostPool(opening_cost_pln=Decimal("500"))
        
        pool.add_cost(Decimal("1000"))
        
        self.assertEqual(pool.get_total_cost(), Decimal("1500"))
    
    def test_reset_for_year(self):
        """Test resetting pool and carrying forward."""
        pool = CostPool()
        pool.add_cost(Decimal("1000"))
        
        unused = pool.reset_for_year()
        
        self.assertEqual(unused, Decimal("1000"))
        self.assertEqual(pool.get_total_cost(), Decimal("0"))


class TestTaxYear(unittest.TestCase):
    """Tests for TaxYear model."""
    
    def test_taxable_income_positive(self):
        """Test positive taxable income."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("1000"),
            total_revenue_pln=Decimal("2000"),
        )
        
        expected = Decimal("1000")
        self.assertEqual(year.taxable_income, expected)
    
    def test_taxable_income_zero(self):
        """Test zero taxable income when revenue = costs."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("1000"),
            total_revenue_pln=Decimal("1000"),
        )
        
        self.assertEqual(year.taxable_income, Decimal("0"))
    
    def test_loss_positive(self):
        """Test loss calculation."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("2000"),
            total_revenue_pln=Decimal("1000"),
        )
        
        self.assertEqual(year.loss, Decimal("1000"))
    
    def test_loss_with_fees(self):
        """Test that fees increase total cost."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("1000"),
            total_fees_pln=Decimal("100"),
            total_revenue_pln=Decimal("1050"),
        )
        
        # Revenue 1050 - Costs (1000 + 100 fees) = -50 loss
        self.assertEqual(year.loss, Decimal("50"))
    
    def test_tax_calculation_19_percent(self):
        """Test 19% tax calculation."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("1000"),
            total_revenue_pln=Decimal("2000"),
        )
        
        expected = Decimal("1000") * Decimal("0.19")
        self.assertEqual(year.tax_due_19_percent, expected)
    
    def test_carryforward_reduces_taxable_income(self):
        """Test that carried forward loss reduces current year taxable income."""
        year = TaxYear(
            year=2026,
            total_costs_pln=Decimal("1000"),
            total_revenue_pln=Decimal("2500"),
            loss_from_previous_years=Decimal("300"),
        )
        
        # Income = 2500 - 1000 = 1500, minus carried loss of 300 = 1200
        self.assertEqual(year.taxable_income, Decimal("1200"))


class TestNormalizedTransaction(unittest.TestCase):
    """Tests for NormalizedTransaction model."""
    
    def test_normalized_transaction_creation(self):
        """Test creating normalized transaction."""
        txn = NormalizedTransaction(
            timestamp=datetime(2026, 1, 15),
            operation_type=OperationType.BUY_CRYPTO_WITH_FIAT,
            tax_event_type=TaxEventType.COST,
            asset="BTC",
            amount=Decimal("1.5"),
            currency="USD",
            pln_value=Decimal("6000"),
            exchange_rate=Decimal("4.0"),
        )
        
        self.assertEqual(txn.asset, "BTC")
        self.assertEqual(txn.pln_value, Decimal("6000"))
        self.assertEqual(txn.exchange_rate, Decimal("4.0"))


class TestNBPRateProvider(unittest.TestCase):
    """Tests for NBPRateProvider."""
    
    def test_normalize_currency_pln(self):
        """Test that PLN is always normalized to PLN."""
        provider = NBPRateProvider()
        self.assertEqual(provider._normalize_currency("PLN"), "PLN")
    
    def test_normalize_currency_stablecoin(self):
        """Test stablecoin normalization."""
        provider = NBPRateProvider()
        self.assertEqual(provider._normalize_currency("USDT"), "USD")
        self.assertEqual(provider._normalize_currency("USDC"), "USD")
        self.assertEqual(provider._normalize_currency("EURT"), "EUR")
    
    def test_get_rate_pln_returns_one(self):
        """Test that PLN rate always returns 1.0."""
        provider = NBPRateProvider()
        rate, date = provider.get_rate("PLN", datetime(2026, 1, 15))
        
        self.assertEqual(rate, Decimal("1.0"))
        self.assertEqual(date, datetime(2026, 1, 15))
    
    def test_normalize_currency_case_insensitive(self):
        """Test that currency normalization is case-insensitive."""
        provider = NBPRateProvider()
        
        self.assertEqual(provider._normalize_currency("usd"), "USD")
        self.assertEqual(provider._normalize_currency("Eur"), "EUR")


class TestDataNormalizer(unittest.TestCase):
    """Tests for DataNormalizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.normalizer = DataNormalizer()
        self.classifier = OperationClassifier()
    
    def test_normalize_valid_row(self):
        """Test normalizing a valid transaction row."""
        row = {
            'Czas': '2026-01-15 14:32:05',
            'Operacja': 'Buy Crypto With Fiat',
            'Moneta': 'BTC',
            'Zmien': '1.5',
        }
        
        normalized = self.normalizer.normalize_row(row, 1, self.classifier)
        
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.asset, "BTC")
        self.assertEqual(normalized.amount, Decimal("1.5"))
        self.assertEqual(normalized.operation_type, OperationType.BUY_CRYPTO_WITH_FIAT)
    
    def test_invalid_timestamp(self):
        """Test that invalid timestamps are caught."""
        row = {
            'Czas': 'invalid-date',
            'Operacja': 'Buy Crypto With Fiat',
            'Moneta': 'BTC',
            'Zmien': '1.5',
        }
        
        normalized = self.normalizer.normalize_row(row, 1, self.classifier)
        
        self.assertIsNone(normalized)
        self.assertTrue(self.normalizer.has_errors())
    
    def test_invalid_amount(self):
        """Test that invalid amounts are caught."""
        row = {
            'Czas': '2026-01-15 14:32:05',
            'Operacja': 'Buy Crypto With Fiat',
            'Moneta': 'BTC',
            'Zmien': 'not-a-number',
        }
        
        normalized = self.normalizer.normalize_row(row, 1, self.classifier)
        
        self.assertIsNone(normalized)
        self.assertTrue(self.normalizer.has_errors())
    
    def test_missing_columns(self):
        """Test that missing columns are detected."""
        row = {
            'Czas': '2026-01-15 14:32:05',
            'Operacja': 'Buy Crypto With Fiat',
        }
        
        normalized = self.normalizer.normalize_row(row, 1, self.classifier)
        
        self.assertIsNone(normalized)
    
    def test_zero_amount_rejected(self):
        """Test that zero amounts are rejected."""
        row = {
            'Czas': '2026-01-15 14:32:05',
            'Operacja': 'Buy Crypto With Fiat',
            'Moneta': 'BTC',
            'Zmien': '0',
        }
        
        normalized = self.normalizer.normalize_row(row, 1, self.classifier)
        
        self.assertIsNone(normalized)


def run_tests():
    """Run all tests."""
    unittest.main(argv=[''], verbosity=2, exit=False)


if __name__ == '__main__':
    run_tests()
