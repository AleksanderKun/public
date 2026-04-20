"""
Comprehensive test suite for the cryptocurrency tax calculator.

Tests cover:
- Configuration loading and validation
- Transaction parsing and normalization
- Operation classification
- Tax calculation accuracy
- Edge cases and error handling
"""

from datetime import datetime
from pathlib import Path

import pytest

from src.tax.config import load_tax_config
from src.tax.nbp import NBPRateService
from src.tax.processor import CryptoTaxCalculator
from src.tax.types import (
    LedgerEntry,
    OperationClassification,
    TaxConfig,
    TaxSummary,
    Transaction,
)
from src.tax.validation import TransactionValidator


class MockRateService:
    """Mock NBP rate service for testing."""

    def __init__(self, rate: float = 4.0):
        self.rate = rate
        self.calls = []

    def get_rate(self, asset, transaction_date):
        self.calls.append((asset, transaction_date))
        return self.rate


# ============================================================================
# Configuration Tests
# ============================================================================


def test_load_tax_config_default() -> None:
    """Test loading configuration with defaults."""
    config = load_tax_config("config/tax_config.yml")
    
    assert config.tax_year == 2026
    assert "PLN" in config.fiat_currencies
    assert "USD" in config.fiat_currencies
    assert config.stablecoin_map["USDT"] == "USD"
    assert config.nbp_base_url == "https://api.nbp.pl/api/exchangerates/rates"


def test_tax_config_normalization() -> None:
    """Test that configuration values are normalized."""
    config = TaxConfig(
        fiat_currencies=["pln", "usd"],
        stablecoin_map={"usdt": "usd"},
        nbp_table="a",
        nbp_base_url="https://api.nbp.pl",
        nbp_cache_path=Path("test_cache.json"),
        ignore_operations=["Transaction Buy"],
        optional_operations=["Airdrop"],
    )
    
    assert config.fiat_currencies == ["PLN", "USD"]
    assert config.stablecoin_map == {"USDT": "USD"}


# ============================================================================
# Transaction Parsing Tests
# ============================================================================


def test_parse_timestamp_standard_format() -> None:
    """Test parsing standard Binance timestamp format."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    ts = calculator.parse_timestamp("24-10-16 13:43:49")
    assert ts.year == 2024
    assert ts.month == 10
    assert ts.day == 16


def test_parse_timestamp_two_digit_year() -> None:
    """Test parsing with 2-digit year."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    ts = calculator.parse_timestamp("99-01-01 00:00:00")
    assert ts.year == 2099


def test_parse_timestamp_invalid() -> None:
    """Test that invalid timestamps raise error."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    with pytest.raises(ValueError, match="Unable to parse timestamp"):
        calculator.parse_timestamp("invalid-timestamp")


def test_normalize_csv(tmp_path: Path) -> None:
    """Test CSV normalization."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,100.0,Purchase\n"
        "24-10-16 14:00:00,Spot,Transaction Fee,USDC,-1.0,\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    frame = calculator.normalize(csv_path)
    
    assert frame.shape[0] == 2
    assert frame["operation"][0] == "Buy Crypto With Fiat"
    assert frame["asset"][0] == "USDC"
    assert frame["amount"][0] == 100.0


def test_normalize_bybit_csv(tmp_path: Path) -> None:
    """Test Bybit CSV normalization and classification."""
    csv_content = (
        "UID: 123\n"
        "Uid,Currency,Contract,Type,Direction,Quantity,Filled Price,Fee Paid,Cash Flow,Change,Wallet Balance,Action,Time(UTC)\n"
        "123,USDT,ETHUSDT,TRADE,BUY,0.1,2000,0,-0.1001,-0.1001,1000,,2025-01-10 10:00:00\n"
        "123,USDT,ETHUSDT,TRADE,SELL,-0.2,2000,0,0.2002,0.2002,1000,,2025-01-11 10:00:00\n"
    )
    csv_path = tmp_path / "bybit.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)

    summary, ledger = calculator.compute_tax(csv_path)

    assert summary.total_cost_pln == 0.4
    assert summary.total_revenue_pln == 0.8
    assert summary.income == 0.4


# ============================================================================
# Operation Classification Tests
# ============================================================================


def test_classify_operation_buy_crypto() -> None:
    """Test classification of buy operations."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    result = calculator.classify_operation("Buy Crypto With Fiat")
    assert result == OperationClassification.COST


def test_classify_operation_fiat_withdraw() -> None:
    """Test classification of fiat withdraw (revenue)."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    result = calculator.classify_operation("Fiat Withdraw")
    assert result == OperationClassification.REVENUE


def test_classify_operation_crypto_to_crypto() -> None:
    """Test that crypto-to-crypto transactions are ignored."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    result = calculator.classify_operation("Transaction Buy")
    assert result == OperationClassification.IGNORED
    
    result = calculator.classify_operation("Transaction Spend")
    assert result == OperationClassification.IGNORED


def test_classify_operation_with_context() -> None:
    """Test fee classification with context."""
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    
    # Fee associated with revenue
    context = {"related_classifications": {OperationClassification.REVENUE}}
    result = calculator.classify_operation("Transaction Fee", context)
    assert result == OperationClassification.REVENUE_FEE
    
    # Fee associated with cost
    context = {"related_classifications": {OperationClassification.COST}}
    result = calculator.classify_operation("Transaction Fee", context)
    assert result == OperationClassification.COST_FEE


# ============================================================================
# Tax Calculation Tests
# ============================================================================


def test_tax_calculation_simple_buy_sell(tmp_path: Path) -> None:
    """Test basic buy and sell scenario."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,100.0,\n"
        "24-10-17 14:00:00,Spot,Fiat Withdraw,USDC,150.0,\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # 100 * 4.0 = 400 PLN cost
    # 150 * 4.0 = 600 PLN revenue
    # Income = 600 - 400 = 200 PLN
    assert summary.total_cost_pln == 400.0
    assert summary.total_revenue_pln == 600.0
    assert summary.income == 200.0
    assert summary.loss_to_carry == 0.0


def test_tax_calculation_loss_carryforward(tmp_path: Path) -> None:
    """Test loss carry-forward when revenue < costs."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,200.0,\n"
        "24-10-17 14:00:00,Spot,Fiat Withdraw,USDC,100.0,\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # 200 * 4.0 = 800 PLN cost
    # 100 * 4.0 = 400 PLN revenue
    # Income = 400 - 800 = -400 PLN
    # Loss to carry = 400 PLN
    assert summary.total_cost_pln == 800.0
    assert summary.total_revenue_pln == 400.0
    assert summary.income == -400.0
    assert summary.loss_to_carry == 400.0


def test_tax_calculation_with_fees(tmp_path: Path) -> None:
    """Test proper fee handling."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,100.0,\n"
        "24-10-16 13:43:50,Spot,Transaction Fee,USDC,-2.0,Purchase fee\n"
        "24-10-17 14:00:00,Spot,Fiat Withdraw,USDC,150.0,\n"
        "24-10-17 14:00:01,Spot,Transaction Fee,USDC,-3.0,Withdrawal fee\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # Cost: (100 + 2) * 4.0 = 408 PLN
    # Revenue: (150 - 3) * 4.0 = 588 PLN
    # Income = 588 - 408 = 180 PLN
    assert summary.total_cost_pln == 408.0
    assert summary.total_revenue_pln == 588.0
    assert summary.income == 180.0


def test_tax_calculation_ignores_crypto_to_crypto(tmp_path: Path) -> None:
    """Test that crypto-to-crypto transactions are not taxed."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,100.0,\n"
        "24-10-16 14:00:00,Spot,Transaction Buy,BTC,0.001,Swap to BTC\n"
        "24-10-16 14:00:01,Spot,Transaction Spend,USDC,-100.0,Cost of swap\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # Only the initial buy is counted as cost
    # The swap transactions are ignored
    assert summary.total_cost_pln == 400.0
    assert summary.total_revenue_pln == 0.0
    assert summary.income == -400.0


def test_tax_calculation_stablecoins(tmp_path: Path) -> None:
    """Test that stablecoins are converted through their paired currency."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDT,100.0,\n"
        "24-10-17 14:00:00,Spot,Fiat Withdraw,USDT,100.0,\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)  # 1 USD = 4.0 PLN
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # USDT should be resolved to USD, then converted
    # 100 * 4.0 = 400 PLN for both
    assert summary.total_cost_pln == 400.0
    assert summary.total_revenue_pln == 400.0
    assert summary.income == 0.0


# ============================================================================
# Ledger Export Tests
# ============================================================================


def test_ledger_structure(tmp_path: Path) -> None:
    """Test that ledger has correct structure."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy Crypto With Fiat,USDC,100.0,Test\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=4.0)
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    assert ledger.shape[0] == 1
    assert "date" in ledger.columns
    assert "operation" in ledger.columns
    assert "asset" in ledger.columns
    assert "amount" in ledger.columns
    assert "pln_value" in ledger.columns
    assert "type" in ledger.columns


# ============================================================================
# Validation Tests
# ============================================================================


def test_validator_missing_columns(tmp_path: Path) -> None:
    """Test validation detects missing required columns."""
    csv_content = (
        "Czas,Operacja,Moneta\n"
        "24-10-16 13:43:49,Buy,USDC\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    validator = TransactionValidator()
    results = validator.validate_csv(csv_path)
    
    assert not results["is_valid"]
    assert results["error_count"] > 0


def test_validator_invalid_amount(tmp_path: Path) -> None:
    """Test validation detects invalid amounts."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-10-16 13:43:49,Spot,Buy,USDC,invalid,\n"
    )
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    validator = TransactionValidator()
    results = validator.validate_csv(csv_path)
    
    assert not results["is_valid"]
    assert results["error_count"] > 0


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_workflow(tmp_path: Path) -> None:
    """Test complete workflow from CSV to exports."""
    csv_content = (
        "Czas,Konto,Operacja,Moneta,Zmien,Uwagi\n"
        "24-01-01 10:00:00,Spot,Buy Crypto With Fiat,BTC,0.1,Purchase\n"
        "24-01-02 11:00:00,Spot,Transaction Fee,BTC,-0.001,Fee\n"
        "24-12-31 15:00:00,Spot,Fiat Withdraw,BTC,0.08,Partial sell\n"
    )
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    
    config = load_tax_config("config/tax_config.yml")
    rate_service = MockRateService(rate=100000.0)  # 1 BTC = 100k PLN
    calculator = CryptoTaxCalculator(config, rate_service=rate_service)
    
    summary, ledger = calculator.compute_tax(csv_path)
    
    # Export and verify
    ledger_csv = tmp_path / "ledger.csv"
    summary_json = tmp_path / "summary.json"
    
    calculator.export_ledger_csv(ledger, ledger_csv)
    calculator.export_summary_json(summary, summary_json)
    
    assert ledger_csv.exists()
    assert summary_json.exists()
    assert ledger.shape[0] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

