"""
TAX MODULE DOCUMENTATION

Cryptocurrency Tax Calculation Engine for Polish PIT-38 (2026)

===============================================================================
OVERVIEW
===============================================================================

This module calculates cryptocurrency tax obligations according to Polish tax
law (PIT-38) as applicable in 2026. It supports Binance-style transaction
exports and automatically fetches exchange rates from the National Bank of
Poland (NBP) API.

Key Features:
- Polish tax law compliance (PIT-38)
- Automatic NBP exchange rate lookup using T-1 rule
- Pooled cost basis tracking (no FIFO requirement)
- Comprehensive transaction validation
- Multiple export formats (CSV, JSON)
- Production-grade error handling and logging
- Comprehensive test coverage


===============================================================================
QUICK START
===============================================================================

1. Prepare your transaction data:
   - Export transactions from Binance as CSV
   - Required columns: Czas, Operacja, Moneta, Zmien
   - Ensure timestamps are in format: YY-MM-DD HH:MM:SS

2. Run the tax calculation:
   python -m src.tax.cli --input transactions.csv

3. Check the results:
   - tax_ledger.csv: Detailed transaction ledger
   - tax_summary.json: Summary with total costs, revenue, and income


===============================================================================
LEGAL FRAMEWORK (POLAND)
===============================================================================

Polish PIT-38 TAX RULES (2026):

1. TAXABLE EVENTS:
   - Selling cryptocurrency for fiat (PLN, EUR, USD, etc.)
   - Using cryptocurrency to pay for goods/services
   - NOT taxable: Crypto-to-crypto transactions

2. TAX BASE CALCULATION:
   income = revenue - costs

3. COSTS:
   - Only fiat spent on cryptocurrency purchases
   - Includes transaction fees related to purchases
   - Costs accumulate over time (no expiration)
   - Uses POOLED cost basis (global, not FIFO)

4. EXCHANGE RATES:
   - Use NBP rate from T-1 (day before transaction)
   - If T-1 not available, go back up to 14 days
   - Stablecoins converted through their underlying currency
     e.g., USDT → USD → PLN

5. LOSS CARRYFORWARD:
   - If income is negative, carry forward as loss to next year
   - Unused costs do NOT expire

6. IMPORTANT ASSUMPTIONS:
   - Assumes all transactions are personal investment income (not business)
   - Does not handle margin trading or futures
   - Does not handle staking/DeFi yield (optional flag available)


===============================================================================
USAGE EXAMPLES
===============================================================================

EXAMPLE 1: Basic CLI Usage
────────────────────────────────────────────────────────────────────────────

# Run with default settings
python -m src.tax.cli --input transactions.csv

# Run with validation enabled
python -m src.tax.cli --input transactions.csv --validate

# Run with debug logging
python -m src.tax.cli --input transactions.csv --verbose

# Custom output paths
python -m src.tax.cli \
  --input transactions.csv \
  --ledger-csv my_ledger.csv \
  --ledger-json my_ledger.json \
  --summary-json my_summary.json


EXAMPLE 2: Programmatic Usage
────────────────────────────────────────────────────────────────────────────

from pathlib import Path
from src.tax import CryptoTaxCalculator, load_tax_config

# Load configuration
config = load_tax_config("config/tax_config.yml")

# Create calculator
calculator = CryptoTaxCalculator(config)

# Process transactions
summary, ledger = calculator.compute_tax(Path("transactions.csv"))

# Export results
calculator.export_ledger_csv(ledger, Path("ledger.csv"))
calculator.export_ledger_json(ledger, Path("ledger.json"))
calculator.export_summary_json(summary, Path("summary.json"))

# Access summary data
print(f"Total Costs: {summary.total_cost_pln} PLN")
print(f"Total Revenue: {summary.total_revenue_pln} PLN")
print(f"Taxable Income: {summary.income} PLN")


EXAMPLE 3: Validation
────────────────────────────────────────────────────────────────────────────

from src.tax.validation import TransactionValidator
from pathlib import Path

validator = TransactionValidator()
results = validator.validate_csv(Path("transactions.csv"))

if not results["is_valid"]:
    print(f"Found {results['error_count']} errors")
    for error in results["errors"]:
        print(f"  Row {error.row_number}: {error.message}")
else:
    print("✓ Validation passed!")


===============================================================================
CONFIGURATION FILE (YAML)
===============================================================================

The config/tax_config.yml file controls tax calculation behavior:

tax_year: 2026                      # Tax year to calculate for
fiat_currencies:                    # Currencies considered as fiat
  - PLN
  - USD
  - EUR
  - GBP

stablecoin_map:                     # Stablecoin → currency mapping
  USDT: USD
  USDC: USD
  EURT: EUR

nbp_table: A                        # NBP table to use (A = current rates)
nbp_base_url: https://api.nbp.pl/api/exchangerates/rates
nbp_cache_path: data/external/nbp_rate_cache.json

ignore_operations:                  # Operations NOT included in tax
  - Transaction Buy
  - Transaction Spend
  - Binance Convert
  - Deposit
  - Withdraw

optional_operations:                # Optional income (airdrops, rewards)
  - Airdrop
  - Reward
  - Staking
  - Earn


===============================================================================
TRANSACTION CLASSIFICATION
===============================================================================

The system classifies transactions into categories:

COST (Taxable Base Increase):
- Buy Crypto With Fiat
- Transaction Fees related to purchases

REVENUE (Taxable Income):
- Fiat Withdraw (selling crypto for fiat)
- Transaction Sold (if fiat involved)
- Transaction Fees related to sales (reduce revenue)

IGNORED (Not Taxable):
- Transaction Buy (crypto-to-crypto, no value change)
- Transaction Spend (crypto payment, non-fiat)
- Binance Convert (internal swap)
- Deposit / Withdraw (internal transfers)

OPTIONAL (Income if configured):
- Airdrop Assets
- Reward / Staking (DeFi income)


===============================================================================
BINANCE CSV FORMAT
===============================================================================

Expected CSV format from Binance:

Czas                        DateTime in format: YY-MM-DD HH:MM:SS
Operacja                    Operation type (e.g., "Buy Crypto With Fiat")
Moneta                      Cryptocurrency symbol (e.g., "BTC", "USDT")
Zmien                       Amount (positive for incoming, negative for outgoing)
Uwagi                       (Optional) Notes/comments
Konto                       (Optional) Account name/type

Example rows:

24-01-01 10:00:00,Buy Crypto With Fiat,BTC,0.1,Purchase from EUR
24-01-02 11:00:00,Transaction Fee,BTC,-0.001,Network fee
24-12-31 15:00:00,Fiat Withdraw,BTC,0.08,Partial sale


===============================================================================
OUTPUT FORMATS
===============================================================================

1. TAX LEDGER (CSV)
────────────────────────────────────────────────────────────────────────────

A detailed transaction-by-transaction ledger:

date,operation,asset,amount,pln_value,type,notes,account
2024-01-01 10:00:00,Buy Crypto With Fiat,BTC,0.1,123456.78,cost,
2024-01-02 11:00:00,Transaction Fee,BTC,-0.001,-123.46,cost_fee,
2024-12-31 15:00:00,Fiat Withdraw,BTC,0.08,98765.43,revenue,

Columns:
- date: Transaction timestamp
- operation: Original operation from Binance
- asset: Cryptocurrency symbol
- amount: Amount in original currency
- pln_value: Amount in PLN (absolute value)
- type: Classification (cost, revenue, ignored, etc.)
- notes: Optional notes from CSV


2. TAX SUMMARY (JSON)
────────────────────────────────────────────────────────────────────────────

{
  "total_cost_pln": 500000.00,
  "total_revenue_pln": 600000.00,
  "income": 100000.00,
  "loss_to_carry": 0.00,
  "tax_year": 2026,
  "transactions_processed": 150,
  "transactions_ignored": 45
}

Fields:
- total_cost_pln: Sum of all acquisition costs in PLN
- total_revenue_pln: Sum of all sales revenue in PLN
- income: Taxable income (revenue - costs)
- loss_to_carry: Loss to carry forward if income is negative
- tax_year: Year calculated for
- transactions_processed: Number of taxable transactions
- transactions_ignored: Number of ignored transactions


===============================================================================
ERROR HANDLING & TROUBLESHOOTING
===============================================================================

ERROR: "Unable to parse timestamp"
─────────────────────────────────────
Solution: Check timestamp format. Expected: YY-MM-DD HH:MM:SS
Supported formats: %y-%m-%d %H:%M:%S, %Y-%m-%d %H:%M:%S, %d-%m-%y %H:%M:%S

ERROR: "Unable to find NBP rate for {currency}"
─────────────────────────────────────────────────
Solution:
1. Check your internet connection
2. The transaction date might be during NBP holidays
3. Try using --verbose to see which dates were attempted
4. Ensure currency code is correct

ERROR: "Missing required columns"
────────────────────────────────────
Solution: Verify CSV has these columns:
- Czas (timestamp)
- Operacja (operation)
- Moneta (asset)
- Zmien (amount)

MISSING EXCHANGE RATES:
──────────────────────
The system attempts to find rates up to 14 days back. If no rate is found:
1. The transaction is logged with a warning
2. The amount is used as-is (no conversion)
3. Manual rate injection may be needed


===============================================================================
RUNNING TESTS
===============================================================================

Run all tests:
  pytest tests/ -v

Run specific test file:
  pytest tests/test_tax_calculator.py -v

Run with coverage:
  pytest tests/ --cov=src.tax --cov-report=html


===============================================================================
EDGE CASES HANDLED
===============================================================================

✓ Missing exchange rates (14-day lookback)
✓ Weekend/holiday dates (automatic backfill)
✓ Stablecoins (mapped to underlying currency)
✓ Mixed currency fees (converted via NBP)
✓ Duplicate timestamps (flagged in validation)
✓ Zero amounts (flagged as warning)
✓ Negative income (calculates loss carryforward)
✓ Pre-2002 dates (error - no NBP data available)
✓ Multiple transactions per second (supported)


===============================================================================
IMPORTANT ASSUMPTIONS & LIMITATIONS
===============================================================================

ASSUMPTIONS:
1. All transactions are personal investment income (not business)
2. User is resident of Poland for tax purposes
3. Transactions are investment activity, not business/trading
4. No margin trading, futures, or leveraged positions
5. No internal transfers between exchanges (marked as ignored)
6. Exchange rates from NBP Table A are accurate and complete

LIMITATIONS:
1. Does NOT calculate actual tax liability (only income)
2. Does NOT handle staking/DeFi yield (optional flag available)
3. Does NOT handle margin trading or futures contracts
4. Does NOT validate business vs personal use distinction
5. Does NOT calculate quarterly advance payments (US-style)
6. Assumes cost basis is GLOBAL (not per-coin or per-wallet)

LEGAL DISCLAIMER:
This tool is provided for informational purposes. It calculates taxable
income according to Polish PIT-38 rules, but does NOT constitute tax advice.
Always consult with a tax professional before filing your returns.


===============================================================================
API REFERENCE
===============================================================================

Main Classes:
- CryptoTaxCalculator: Main calculation engine
- NBPRateService: Exchange rate fetching and caching
- TransactionValidator: Data validation
- TaxConfig: Configuration management

Key Methods:

CryptoTaxCalculator.compute_tax(data_path, include_optional=False)
  Returns: (TaxSummary, ledger DataFrame)

CryptoTaxCalculator.export_ledger_csv(ledger, output_path)
CryptoTaxCalculator.export_ledger_json(ledger, output_path)
CryptoTaxCalculator.export_summary_json(summary, output_path)

TransactionValidator.validate_csv(data_path)
  Returns: dict with error/warning counts and details


===============================================================================
SUPPORT & CONTRIBUTION
===============================================================================

For issues, questions, or contributions, please refer to the project README.md.

The code is structured for extensibility:
- Add custom operation classifications in processor.py
- Add custom rate sources by extending NBPRateService
- Add custom validation checks in validation.py


===============================================================================
"""
