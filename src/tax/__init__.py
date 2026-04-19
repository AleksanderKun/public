"""
Cryptocurrency tax calculation module for Polish PIT-38 (2026).

This module provides tools for calculating cryptocurrency tax obligations
according to Polish tax law, with support for Binance-style transaction data
and automatic NBP exchange rate conversion.

Key features:
- Polish tax law compliance (PIT-38)
- Automatic NBP exchange rate lookup (T-1 rule)
- Pooled cost basis tracking (no FIFO requirement)
- Comprehensive transaction validation
- Multiple export formats (CSV, JSON)
- CLI interface

Example:
    from src.tax import CryptoTaxCalculator, load_tax_config
    from pathlib import Path
    
    config = load_tax_config("config/tax_config.yml")
    calculator = CryptoTaxCalculator(config)
    summary, ledger = calculator.compute_tax(Path("transactions.csv"))
    
    calculator.export_ledger_csv(ledger, Path("ledger.csv"))
    calculator.export_summary_json(summary, Path("summary.json"))
"""

from .config import load_tax_config
from .nbp import NBPRateService
from .processor import CryptoTaxCalculator
from .types import (
    LedgerEntry,
    OperationClassification,
    OperationType,
    TaxConfig,
    TaxSummary,
    Transaction,
    ValidationError,
)
from .validation import TransactionValidator

__all__ = [
    "CryptoTaxCalculator",
    "TaxConfig",
    "TaxSummary",
    "load_tax_config",
    "NBPRateService",
    "TransactionValidator",
    "Transaction",
    "LedgerEntry",
    "OperationClassification",
    "OperationType",
    "ValidationError",
]

