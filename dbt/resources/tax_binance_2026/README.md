# Cryptocurrency Tax Calculation Engine - Polish Tax Law (PIT-38)

## Overview

This is a **production-grade** tax calculation engine for cryptocurrency transactions, specifically designed to comply with Polish tax law (PIT-38) as applicable in 2026.

The module implements the following key principles:

- ✅ **Global cost pooling**: Costs are pooled (not FIFO) per Polish law
- ✅ **Loss carry-forward**: Unused losses carry over to future tax years
- ✅ **T-1 exchange rates**: Uses NBP rates from the day BEFORE transaction (T-1 rule)
- ✅ **Proper classification**: Distinguishes taxable vs. non-taxable events
- ✅ **Multi-year support**: Calculate tax liability across multiple years
- ✅ **Production-ready**: Type hints, error handling, logging, comprehensive validation

## Legal Framework

### Taxable Events (Per Polish Tax Law)

**TAXABLE** (must report):
- Selling crypto for fiat currency (PLN, USD, EUR, etc.)
- Using crypto to pay for goods/services
- Receiving fiat from crypto transactions

**NOT TAXABLE** (ignored):
- Crypto-to-crypto transactions (swaps, converts)
- Transfers between wallets
- Receiving crypto gifts or airdrops (conservative interpretation)

### Tax Base Calculation

```
Taxable Income = Revenue - Costs - Carried Forward Losses

Where:
- Revenue = Fiat received from crypto sales
- Costs = Fiat spent on crypto purchases + fees
- Costs are pooled globally (no FIFO requirement)
- Losses can be carried forward to future years
```

### Tax Rate

- Standard rate: **19%** (PIT-38)
- Applied to positive taxable income
- Losses in current year can offset future years

## Architecture

The module is designed as a modular pipeline:

```
CSV Input
    ↓
[Data Loader] → Load Binance CSV
    ↓
[Normalizer] → Validate & normalize data
    ↓
[Classifier] → Classify operations as cost/revenue/ignored
    ↓
[Currency Converter] → Convert to PLN using NBP rates (T-1 rule)
    ↓
[Tax Engine] → Calculate costs, revenue, losses
    ↓
[Reporter] → Generate CSV, JSON, text reports
```

## Module Components

### `models.py` - Data Models

Defines core data structures:

- `Transaction`: Raw transaction from Binance
- `NormalizedTransaction`: Transaction after validation and classification
- `OperationType`: Enum of operation types (Buy, Sell, etc.)
- `TaxEventType`: Classification (Cost, Revenue, Ignored, Optional)
- `TaxYear`: Annual tax summary
- `TaxReport`: Complete multi-year tax report

### `nbp_provider.py` - NBP Exchange Rate Provider

Integrates with National Bank of Poland API:

- Fetches real exchange rates via NBP API
- Implements T-1 rule (uses rate from day before transaction)
- Caches rates for performance
- Falls back to searching backwards if rate unavailable
- Handles stablecoin mappings (USDT→USD, EURT→EUR, etc.)

```python
from nbp_provider import NBPRateProvider
from datetime import datetime

provider = NBPRateProvider(cache_path="nbp_cache.json")

# Get rate for USD on 2026-01-15 (uses 2026-01-14 NBP rate)
rate, actual_date = provider.get_rate("USD", datetime(2026, 1, 15))
# rate = Decimal("4.02")
# actual_date = 2026-01-14
```

### `normalizer.py` - Data Normalization

Classifies transactions and validates data:

- `OperationClassifier`: Maps raw operation names to types
- `DataNormalizer`: Validates CSV data and creates normalized transactions

Operations classified as:

**Cost-increasing:**
- Buy Crypto With Fiat
- Fiat Deposit

**Revenue-generating:**
- Fiat Withdraw
- Transaction Sold
- Transaction Spend

**Non-taxable:**
- Transaction Buy (crypto-crypto)
- Binance Convert (crypto-crypto)
- Crypto Transfers

**Optional:**
- Airdrops (configurable)
- Staking rewards (configurable)

### `tax_engine.py` - Tax Calculation

Core tax calculation logic:

- `CostPool`: Manages global cost pooling per Polish law
- `TaxCalculationEngine`: Calculates annual tax liability
- `TaxCalculator`: High-level calculator interface

```python
from tax_engine import TaxCalculator, TaxCalculationEngine

engine = TaxCalculationEngine()
calculator = TaxCalculator(engine)

# Process normalized transactions
report = calculator.calculate_tax(normalized_transactions)

# Access results
for year, tax_year in report.years.items():
    print(f"{year}: Income={tax_year.taxable_income} PLN, Tax={tax_year.tax_due_19_percent} PLN")
```

### `processor.py` - Data Processing Pipeline

Orchestrates the full workflow:

```python
from processor import DataProcessor

processor = DataProcessor()

# Full pipeline: load → normalize → convert currency → calculate
report = processor.process(Path("binance_export.csv"))

# Or step-by-step:
processor.load_csv(Path("binance_export.csv"))
processor.normalize_and_classify()
processor.apply_currency_conversion()
report = processor.calculate_tax()
```

### `reporter.py` - Report Generation

Generates multiple report formats:

- **Ledger CSV**: Detailed transaction-by-transaction breakdown
- **Summary CSV**: Annual summaries with tax calculations
- **JSON**: Machine-readable export for further processing
- **Text**: Human-readable summary for tax filing

```python
from reporter import ReportGenerator

reporter = ReportGenerator(output_dir="./reports")
reporter.generate_all(tax_report, prefix="2026_tax")
reporter.print_summary(tax_report)
```

### `cli.py` - Command-Line Interface

User-friendly CLI with commands:

- `process`: Full pipeline processing
- `validate`: Data validation only
- `clear-cache`: Clear NBP rate cache
- `cache-info`: Show cache statistics
- `config-template`: Print config file template

## Usage

### Installation

```bash
# Install dependencies
pip install polars requests pyyaml click

# Or use provided requirements
pip install -r requirements.txt
```

### Via CLI

```bash
# Process Binance CSV
python cli.py process binance_export.csv --output-dir ./reports

# Validate CSV format
python cli.py validate binance_export.csv

# Clear exchange rate cache
python cli.py clear-cache --cache-file nbp_cache.json

# Show config template
python cli.py config-template > config.yml
```

### Via Python API

```python
from processor import DataProcessor
from reporter import ReportGenerator
from pathlib import Path

# Create processor
processor = DataProcessor()

# Process CSV file
report = processor.process(Path("binance_export.csv"))

# Generate reports
reporter = ReportGenerator(output_dir="./reports")
reporter.generate_all(report)
reporter.print_summary(report)
```

### Via main.py

```bash
# Default execution (looks for CSV in predefined location)
python main.py

# Or with CLI commands
python main.py process --help
```

## Configuration

Configuration via `tax_config.yml`:

```yaml
tax_year: 2026

fiat_currencies:
  - PLN
  - USD
  - EUR
  - GBP

stablecoin_map:
  USDT: USD
  USDC: USD
  EURT: EUR

nbp_table: A
nbp_cache_path: data/external/nbp_cache.json

treat_airdrops_as_income: false
treat_staking_as_income: false

ignore_operations:
  - Transaction Buy
  - Transaction Spend
  - Binance Convert
```

## Input Data Format

Expected Binance CSV columns:

| Czas | Operacja | Moneta | Zmien |
|------|----------|--------|-------|
| 2026-01-15 14:32:05 | Buy Crypto With Fiat | BTC | 1.5 |
| 2026-01-16 10:00:00 | Fiat Withdraw | USD | 5000 |
| 2026-01-17 09:15:30 | Transaction Sold | ETH | 10 |

- **Czas**: Timestamp (YYYY-MM-DD HH:MM:SS)
- **Operacja**: Operation type
- **Moneta**: Currency/asset symbol
- **Zmien**: Amount (positive or negative)

## Output Reports

### Ledger CSV

Detailed transaction ledger with columns:
- Data: Date
- Operacja: Operation type
- Waluta: Asset/currency
- Ilość: Amount
- Typ_Podatkowy: Tax classification
- Kurs_NBP_T1: Exchange rate used
- Wartość_PLN: PLN value
- Czy_Opodatkowany: Taxable (TAK/NIE)

### Summary CSV

Annual summary with columns:
- Rok: Tax year
- Liczba_Transakcji: Transaction count
- Przychód_PLN: Revenue
- Koszt_PLN: Costs
- Opłaty_PLN: Fees
- Dochód_Do_Opodatkowania: Taxable income
- Podatek_19_Procent: Tax due

### JSON Export

Machine-readable format including:
- Multi-year summary
- Year-by-year breakdown
- Transaction details
- Exchange rates used

## Testing

Run comprehensive unit tests:

```bash
python tests.py
```

Tests cover:
- Data models and validation
- Operation classification
- Cost pooling logic
- Tax year calculations
- Currency conversion
- Error handling

## Key Features & Design Decisions

### 1. Global Cost Pooling

Per Polish law, costs are NOT reduced via FIFO. Instead:
- All costs accumulate in a global pool
- Revenue is calculated independently
- Income = Revenue - Total Costs - Carried Losses

```python
# Correct per Polish law:
costs = Decimal("1000") + Decimal("2000")  # = 3000
revenue = Decimal("4500")
income = revenue - costs  # = 1500

# NOT FIFO!
```

### 2. Loss Carry-Forward

Losses can be carried to future years:

```python
year_2024 = TaxYear(2024, revenue=1000, costs=2000)  # Loss: 1000
year_2025 = TaxYear(2025, revenue=3000, costs=1000, 
                    loss_from_previous_years=1000)  # Taxable: 1000
```

### 3. T-1 Exchange Rate Rule

Uses NBP rate from day BEFORE transaction:

- Transaction: 2026-01-15
- Rate date: 2026-01-14 (T-1)
- If no rate on T-1: search backwards up to 10 business days
- Ensures consistent valuation

```python
rate, actual_date = provider.get_rate("USD", datetime(2026, 1, 15))
# Returns rate from 2026-01-14 or earlier
```

### 4. Stablecoin Handling

Stablecoins are still converted to PLN:

```
USDT → USD (NBP rate for USD used)
EURT → EUR (NBP rate for EUR used)
DAI → USD (USD rate used)
```

Even though nominally 1:1, tax law still requires FX conversion.

### 5. Error Handling & Validation

- Validates all input data
- Logs warnings for edge cases
- Gracefully handles missing NBP rates
- Reports validation errors with row numbers

## Edge Cases Handled

✅ **Missing NBP rates** (weekends/holidays)
- Searches backwards up to 10 days
- Logs warning if not found
- Uses fallback (1.0 with error flag)

✅ **Mixed transaction currencies**
- Each transaction converted independently
- Fees in different coins: converted to PLN

✅ **Negative amounts**
- Always stored as absolute values
- Direction determined by operation type

✅ **Duplicate timestamps**
- Processed in order received
- Timestamp used for rate lookup

✅ **Partial fills**
- Each transaction calculated independently
- No aggregation logic needed

✅ **Zero amounts**
- Rejected as invalid

## Legal Notes & Disclaimers

⚠️ **Important**: This tool is designed to assist with tax calculations per Polish tax law (PIT-38). However:

1. **Not legal advice**: Consult a tax professional before filing
2. **Estimates only**: Final liability determined by tax authority
3. **Law may change**: Polish tax law on crypto may be updated
4. **Complete data needed**: Ensure all transactions included
5. **Manual review recommended**: Review reports before submission

## Performance Characteristics

- **Load time**: ~100ms for 1,000 transactions
- **Currency conversion**: ~1-2 seconds per year (includes NBP API calls, cached after)
- **Calculation**: <100ms per year
- **Memory**: ~10MB for 10,000 transactions

## Future Enhancements

Potential improvements:

- Support for other exchanges (Kraken, Coinbase, etc.)
- More granular fee allocation
- Staking/mining income handling
- Integration with other tax systems
- GUI interface
- Real-time portfolio tracking

## Support & Contact

For issues or questions:

1. Check documentation in code comments
2. Review unit tests for usage examples
3. Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`
4. Consult tax professional for legal questions

---

**Last Updated**: 2026-01-01  
**Version**: 1.0.0  
**Python**: 3.11+  
**License**: As per project requirements
