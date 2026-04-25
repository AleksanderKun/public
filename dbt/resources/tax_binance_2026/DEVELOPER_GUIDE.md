# Developer's Implementation Guide

## Overview for Developers

This guide explains how the cryptocurrency tax calculation module is structured and how to extend or maintain it.

---

## Architecture Overview

```
INPUT (Binance CSV)
    ↓
[DataProcessor.load_csv()]
    ↓
[DataNormalizer.normalize_row()] × N rows
    ↓
[OperationClassifier.classify()]
    ↓
[NBPRateProvider.get_rate()]
    ↓
[TaxCalculationEngine.calculate()]
    ↓
[ReportGenerator.generate_*()]
    ↓
OUTPUT (CSV, JSON, text reports)
```

---

## Module Dependencies

```
models.py (no dependencies)
    ↓
normalizer.py (depends on models.py)
    ↓
nbp_provider.py (depends on models.py)
    ↓
tax_engine.py (depends on models.py)
    ↓
processor.py (depends on normalizer.py, nbp_provider.py, tax_engine.py)
    ↓
reporter.py (depends on models.py)
    ↓
cli.py (depends on all modules)
```

**Note:** No circular dependencies. Design is clean and modular.

---

## Data Flow Through Modules

### 1. CSV Loading → models.Transaction

```python
# Input CSV row
{
    "Czas": "2026-01-15 14:32:05",
    "Operacja": "Buy Crypto With Fiat",
    "Moneta": "BTC",
    "Zmien": "1.5"
}

# Output: Transaction object
transaction = Transaction(
    timestamp=datetime(2026, 1, 15, 14, 32, 5),
    operation="Buy Crypto With Fiat",
    asset="BTC",
    amount=Decimal("1.5")
)
```

### 2. Classification → NormalizedTransaction

```python
# Input: Transaction
transaction = Transaction(...)

# Processing
classifier = OperationClassifier()
operation_type = classifier.classify(transaction.operation)
# Result: OperationType.BUY_CRYPTO_WITH_FIAT

tax_event_type = classifier.get_tax_event_type(operation_type, "BTC")
# Result: TaxEventType.COST

# Output: NormalizedTransaction
normalized = NormalizedTransaction(
    timestamp=transaction.timestamp,
    operation_type=OperationType.BUY_CRYPTO_WITH_FIAT,
    tax_event_type=TaxEventType.COST,
    asset="BTC",
    amount=Decimal("1.5"),
    currency="USD",  # if applicable
    pln_value=None,  # to be filled by currency converter
)
```

### 3. Currency Conversion

```python
# Input: NormalizedTransaction with currency="USD"
normalized.amount = Decimal("1.5")  # 1.5 BTC
normalized.currency = "USD"
normalized.pln_value = None

# Processing
nbp = NBPRateProvider(cache_path="cache.json")
rate, rate_date = nbp.get_rate("USD", normalized.timestamp)
# rate = Decimal("4.02")
# rate_date = datetime(2026, 1, 14)  # T-1

pln_value = normalized.amount * rate
# pln_value = 1.5 * 4.02 = 6.03 (but depends on actual asset conversion)

# Output: Updated NormalizedTransaction
normalized.pln_value = Decimal("6030.00")  # Assuming full value
normalized.exchange_rate = Decimal("4.02")
normalized.rate_date = datetime(2026, 1, 14)
```

### 4. Tax Calculation

```python
# Input: List of normalized transactions grouped by year
transactions_2026 = [normalized1, normalized2, ...]

# Processing
engine = TaxCalculationEngine()
engine.add_transactions(transactions_2026)

cost_pool = CostPool()
for txn in transactions_2026:
    if txn.tax_event_type == TaxEventType.COST:
        cost_pool.add_cost(txn.pln_value)
    elif txn.tax_event_type == TaxEventType.REVENUE:
        total_revenue += txn.pln_value

# Output: TaxYear
tax_year = TaxYear(
    year=2026,
    total_costs_pln=Decimal("28381.00"),
    total_revenue_pln=Decimal("34370.00"),
    total_fees_pln=Decimal("281.00"),
)

# Calculated properties:
# taxable_income = 34370 - (28381 + 281) = 5708 PLN
# tax_due_19_percent = 5708 * 0.19 = 1084.52 PLN
```

### 5. Report Generation

```python
# Input: TaxReport with years and transactions
report = TaxReport(
    report_date=datetime.now(),
    years={2026: tax_year},
    transactions=[normalized1, normalized2, ...]
)

# Processing
reporter = ReportGenerator(output_dir="./reports")
reporter.generate_ledger_csv(report)      # CSV with all transactions
reporter.generate_summary_csv(report)     # CSV with annual summary
reporter.generate_json(report)            # JSON export
reporter.generate_text_summary(report)    # Text report

# Output files:
# - tax_report_ledger.csv
# - tax_report_summary.csv
# - tax_report.json
# - tax_report_summary.txt
```

---

## Extending the Module

### Adding a New Operation Type

1. **Add to OperationType enum** (models.py):

```python
class OperationType(str, Enum):
    # ... existing types ...
    MARGIN_INTEREST = "Margin Interest"
    LOAN_REPAYMENT = "Loan Repayment"
```

2. **Update OperationClassifier** (normalizer.py):

```python
class OperationClassifier:
    # Add to appropriate category:
    
    COST_INCREASING_OPS = {
        # ... existing ...
        OperationType.MARGIN_INTEREST,  # Interest increases cost
    }
    
    def classify(self, operation_name: str) -> OperationType:
        # Add fuzzy matching
        if "MARGIN" in op_upper and "INTEREST" in op_upper:
            return OperationType.MARGIN_INTEREST
        # ... rest of logic ...
```

3. **Update tax event classification**:

```python
def get_tax_event_type(self, operation_type, asset):
    if operation_type == OperationType.MARGIN_INTEREST:
        return TaxEventType.COST  # or REVENUE depending on treatment
    # ... rest of logic ...
```

4. **Add tests** (tests.py):

```python
def test_classify_margin_interest(self):
    op_type = self.classifier.classify("Margin Interest")
    self.assertEqual(op_type, OperationType.MARGIN_INTEREST)
```

### Adding a New Report Format

1. **Add method to ReportGenerator** (reporter.py):

```python
def generate_xml(self, report: TaxReport, prefix: str = "tax_report") -> Path:
    """Generate XML export."""
    filename = self.output_dir / f"{prefix}.xml"
    
    # Build XML structure
    # ...
    
    with open(filename, 'w', encoding='utf-8') as f:
        # Write XML
        pass
    
    return filename
```

2. **Update generate_all method**:

```python
def generate_all(self, report: TaxReport, prefix: str = "tax_report"):
    results = {}
    # ... existing reports ...
    results['xml'] = self.generate_xml(report, prefix)
    return results
```

### Adding NBP Integration for Different Country

1. **Create new provider** (similar to nbp_provider.py):

```python
class ECBRateProvider:
    """European Central Bank exchange rate provider."""
    
    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = cache_path
        self.base_url = "https://www.ecb.europa.eu/..."
        # ...
    
    def get_rate(self, currency: str, date: datetime):
        # Implement ECB API integration
        pass
```

2. **Use in processor**:

```python
ecb_provider = ECBRateProvider(cache_path="ecb_cache.json")
processor = DataProcessor(nbp_provider=ecb_provider)
```

---

## Testing Strategy

### Unit Test Structure

```python
class TestComponentName(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Initialize test objects
    
    def test_happy_path(self):
        """Test normal operation."""
        # Assert expected behavior
    
    def test_edge_case(self):
        """Test edge case."""
        # Assert graceful handling
    
    def test_error_case(self):
        """Test error handling."""
        # Assert error raised appropriately
```

### Adding New Tests

1. Create test class:

```python
class TestNewFeature(unittest.TestCase):
    def setUp(self):
        self.component = NewComponent()
    
    def test_basic_functionality(self):
        result = self.component.method()
        self.assertEqual(result, expected_value)
```

2. Run tests:

```bash
python tests.py TestNewFeature
```

### Testing with Real Data

```python
# Create mock CSV data
csv_content = """Czas,Operacja,Moneta,Zmien
2026-01-15 14:32:05,Buy Crypto With Fiat,BTC,1.5
2026-03-10 09:15:00,Transaction Sold,BTC,1.0
"""

# Write to temp file
with open("test_data.csv", "w") as f:
    f.write(csv_content)

# Process
processor = DataProcessor()
report = processor.process(Path("test_data.csv"))

# Verify
assert len(report.transactions) == 2
assert report.years[2026].total_revenue_pln > 0
```

---

## Debugging Guide

### Enable Debug Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Now run normally - will see detailed logs
processor = DataProcessor()
report = processor.process(Path("binance_export.csv"))
```

### Common Issues & Solutions

#### Issue: "No exchange rate found"

```python
# Solution 1: Check if date is valid
date = transaction.timestamp
print(f"Looking for rate on {date.date()}")

# Solution 2: Check cache
nbp = NBPRateProvider(cache_path="cache.json")
stats = nbp.get_cache_stats()
print(f"Cache has {stats['entries']} entries")

# Solution 3: Clear cache and retry
nbp.clear_cache()
rate, _ = nbp.get_rate("USD", transaction.timestamp)
```

#### Issue: "Unknown operation type"

```python
# Solution 1: Check what operations exist
processor = DataProcessor()
processor.load_csv(Path("binance_export.csv"))

# Get operations that failed
for error in processor.get_validation_errors():
    if error.error_type == "unknown_operation":
        print(f"Unknown: {error.original_data['Operacja']}")

# Solution 2: Add to classifier
classifier = OperationClassifier()
# Check classify() method for fuzzy matching
```

#### Issue: "Validation errors in rows"

```python
# See detailed errors
processor = DataProcessor()
processor.load_csv(Path("binance_export.csv"))
processor.normalize_and_classify()

for error in processor.get_validation_errors():
    print(f"Row {error.row_index}: {error.error_type}")
    print(f"  Message: {error.message}")
    print(f"  Data: {error.original_data}")
```

---

## Performance Optimization

### Current Performance

```
Load CSV: ~50ms per 1,000 rows
Normalize: ~100ms per 1,000 rows
Convert currency: ~1-2s per year (includes API calls, then cached)
Calculate tax: <100ms per year
Total: ~2-3 seconds for 1 year of data (with API calls)
```

### Optimization Opportunities

1. **Parallel processing** (multiple years):

```python
from concurrent.futures import ThreadPoolExecutor

def process_year(year):
    processor = DataProcessor()
    # Process year
    return report

years = [2024, 2025, 2026]
with ThreadPoolExecutor(max_workers=3) as executor:
    reports = executor.map(process_year, years)
```

2. **Batch API calls**:

```python
# Currently: 1 API call per unique currency
# Optimization: Batch multiple dates in single call
# (if NBP API supports it)
```

3. **Caching strategy**:

```python
# Cache is already implemented
# Current: File-based JSON cache
# Optimization: Use SQLite for faster lookups
```

---

## Code Style & Standards

### Type Hints

```python
# Good
def get_rate(self, currency: str, date: datetime) -> Decimal:
    """Get exchange rate."""
    pass

# Avoid
def get_rate(self, currency, date):
    """Get exchange rate."""
    pass
```

### Docstrings

```python
def process_year(self, year: int) -> TaxYear:
    """
    Calculate tax for a single year.
    
    Per Polish tax law, uses global cost pooling (not FIFO).
    Losses carry forward to subsequent years.
    
    Args:
        year: Tax year to process
        
    Returns:
        TaxYear object with calculations
        
    Raises:
        ValueError: If year is invalid
    """
    pass
```

### Error Handling

```python
# Good
try:
    rate = nbp.get_rate(currency, date)
    if rate is None:
        logger.warning(f"No rate for {currency} on {date}")
        rate = Decimal("1.0")
except requests.Timeout:
    logger.error(f"NBP timeout for {currency}")
    rate = Decimal("1.0")

# Avoid
try:
    rate = nbp.get_rate(currency, date)
except:
    pass  # Silent failure - bad!
```

---

## Deployment Checklist

- [ ] All unit tests pass: `python tests.py`
- [ ] Type checking passes: `mypy .`
- [ ] Code formatting: `black .`
- [ ] Linting: `flake8 .`
- [ ] Documentation updated
- [ ] Configuration file (YAML) provided
- [ ] Requirements.txt updated
- [ ] Tested with real Binance CSV
- [ ] Performance acceptable
- [ ] Error messages clear
- [ ] Logging configured
- [ ] Version number updated

---

## Maintenance Tasks

### Regular Maintenance

1. **Monitor for NBP API changes**:
   - NBP may change API format
   - Check quarterly

2. **Update exchange rate cache**:
   - Cache size grows over time
   - Can be cleared safely anytime

3. **Polish law changes**:
   - Tax law may change in future years
   - Monitor official sources
   - Update documentation/code as needed

### User Support

**Common questions:**

1. Q: What if a transaction is missing?  
   A: Re-export from Binance with correct date range

2. Q: Can I use data from multiple exchanges?  
   A: Only if converted to Binance CSV format

3. Q: What about leverage trading?  
   A: Currently not supported (complex rules)

---

## Version Control Strategy

```
Version Format: MAJOR.MINOR.PATCH

1.0.0 - Initial release
1.1.0 - Add margin trading support
1.0.1 - Bug fixes
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/add-margin-support

# Make changes, run tests
python tests.py

# Commit
git commit -m "Add margin trading support"

# Create pull request
# After review and testing:
git checkout main
git merge feature/add-margin-support
git tag v1.1.0
```

---

## Documentation Standards

### Inline Comments

```python
# Use for WHY, not WHAT
# Good
cost_pool.add_cost(amount)  # Accumulate per Polish law (global pooling)

# Avoid
cost_pool.add_cost(amount)  # Call add_cost method
```

### Module Docstrings

```python
"""
Module for cryptocurrency tax calculation per Polish law (PIT-38).

Implements:
- Global cost pooling (NOT FIFO)
- T-1 exchange rate rule
- Multi-year loss carry-forward
"""
```

---

## Related Resources

- Polish tax law: https://www.podatki.gov.pl/
- NBP API: https://api.nbp.pl/
- Python typing: https://docs.python.org/3/library/typing.html
- Click CLI: https://click.palletsprojects.com/
- Polars docs: https://pola-rs.github.io/

---

## Support & Questions

For implementation questions:
1. Check existing code comments
2. Review unit tests for examples
3. Read Polish tax law guide
4. Check module docstrings

For bug reports:
1. Create minimal reproduction case
2. Run with DEBUG logging
3. Include error message and data sample
4. Check if similar issue exists

---

**Last Updated:** 2026-01-01  
**Version:** 1.0.0
