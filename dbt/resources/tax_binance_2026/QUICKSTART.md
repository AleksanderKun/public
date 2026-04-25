# Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Export Data from Binance

1. Log into Binance
2. Go to: Account → Download Statement → Crypto Assets
3. Select date range (entire tax year)
4. Format: CSV
5. Save as: `binance_export.csv`

### 3. Run Calculation

```bash
# Option A: Using CLI
python cli.py process binance_export.csv --output-dir ./reports

# Option B: Using main.py directly
python main.py

# Option C: Validate first
python cli.py validate binance_export.csv
```

### 4. Check Results

Reports are generated in `./reports/`:

- `tax_report_ledger.csv` - Transaction-by-transaction breakdown
- `tax_report_summary.csv` - Annual summary
- `tax_report.json` - Machine-readable export
- `tax_report_summary.txt` - Human-readable summary

---

## Common Workflows

### Validate CSV Format

```bash
python cli.py validate binance_export.csv
```

Shows any data issues before processing.

### Process Multiple Years

Create separate CSV files for each year, then process each:

```bash
python cli.py process binance_2024.csv --output-dir ./reports/2024
python cli.py process binance_2025.csv --output-dir ./reports/2025
python cli.py process binance_2026.csv --output-dir ./reports/2026
```

### Clear Exchange Rate Cache

```bash
python cli.py clear-cache --cache-file nbp_cache.json
```

(Use if you want to refresh all NBP rates)

### Check Cache Statistics

```bash
python cli.py cache-info --cache-file nbp_cache.json
```

---

## Using Python API (Programmatic)

### Simple Case

```python
from processor import DataProcessor
from reporter import ReportGenerator
from pathlib import Path

# Process CSV
processor = DataProcessor()
report = processor.process(Path("binance_export.csv"))

# Generate reports
reporter = ReportGenerator(output_dir="./reports")
reporter.generate_all(report)
reporter.print_summary(report)
```

### Advanced Case

```python
from processor import DataProcessor
from nbp_provider import NBPRateProvider
from normalizer import OperationClassifier
from reporter import ReportGenerator
from pathlib import Path

# Custom configuration
nbp = NBPRateProvider(cache_path=Path("cache.json"))
classifier = OperationClassifier(treat_airdrops_as_income=True)

# Create processor
processor = DataProcessor(
    nbp_provider=nbp,
    classifier=classifier,
    treat_airdrops_as_income=True
)

# Step-by-step processing
processor.load_csv(Path("binance_export.csv"))
success, errors = processor.normalize_and_classify()
processor.apply_currency_conversion()
report = processor.calculate_tax()

# Access results
for year, tax_year in report.years.items():
    print(f"{year}: {tax_year.taxable_income} PLN -> Tax: {tax_year.tax_due_19_percent} PLN")

# Generate reports
reporter = ReportGenerator(output_dir="./reports")
reporter.generate_all(report, prefix=f"report_{datetime.now().year}")
```

---

## Understanding Output

### Ledger CSV

Shows every transaction:

| Data | Operacja | Waluta | Ilość | Typ_Podatkowy | Kurs_NBP_T1 | Wartość_PLN |
|------|----------|--------|-------|---------------|-------------|------------|
| 2026-01-15 14:32 | Buy Crypto With Fiat | USD | 5000.00 | KOSZT | 4.0200 | 20100.00 |
| 2026-03-10 09:15 | Transaction Sold | BTC | 1.00 | PRZYCHÓD | 4.0200 | 6000.00 |

- **Typ_Podatkowy**: KOSZT (cost), PRZYCHÓD (revenue), or IGNOROWANE (ignored)
- **Kurs_NBP_T1**: Exchange rate from day before transaction
- **Wartość_PLN**: Amount converted to PLN

### Summary CSV

Annual breakdown:

| Rok | Liczba_Transakcji | Przychód_PLN | Koszt_PLN | Dochód_Do_Opodatkowania | Podatek_19_Procent |
|-----|-------------------|--------------|-----------|-------------------------|------------------|
| 2026 | 47 | 34370.00 | 28381.00 | 5989.00 | 1137.91 |

- **Dochód_Do_Opodatkowania**: Income after all deductions and carried losses
- **Podatek_19_Procent**: Tax due at 19% rate

### Text Summary

Human-readable format:

```
PODSUMOWANIE PODATKOWE - KRYPTOWALUTY (PIT-38)
==============================================================

Liczba transakcji: 47
Lata obejmujące: 2026

ROK 2026:
  Liczba transakcji:        47
  Przychód:            34,370.00 PLN
  Koszt:               28,381.00 PLN
  Dochód netto:         5,989.00 PLN
  Dochód do opodatkowania: 5,989.00 PLN
  Podatek (19%):        1,137.91 PLN
```

### JSON Export

Machine-readable format for further processing:

```json
{
  "report_date": "2026-01-15T10:30:00",
  "summary": {
    "total_revenue_pln": 34370.00,
    "total_costs_pln": 28381.00,
    "total_taxable_income": 5989.00,
    "total_tax_due": 1137.91
  },
  "years": {
    "2026": {
      "total_revenue_pln": 34370.00,
      "total_costs_pln": 28381.00,
      "taxable_income": 5989.00,
      "tax_due_19_percent": 1137.91
    }
  },
  "transactions": [...]
}
```

---

## Configuration

### Via YAML Config

Create `tax_config.yml`:

```yaml
tax_year: 2026
fiat_currencies:
  - PLN
  - USD
  - EUR
treat_airdrops_as_income: false
nbp_cache_path: data/external/nbp_cache.json
```

Use with CLI:

```bash
python cli.py --config tax_config.yml process binance_export.csv
```

### Programmatically

```python
from normalizer import OperationClassifier
from nbp_provider import NBPRateProvider

classifier = OperationClassifier(treat_airdrops_as_income=False)
nbp = NBPRateProvider(cache_path="nbp_cache.json")
```

---

## Troubleshooting

### No rates found for currency

```
WARNING: No exchange rate found for USD within 10 days before 2026-01-15
```

**Solution**: 
- Check date is within NBP's available data
- Try clearing cache: `python cli.py clear-cache`
- Manually add rate to `nbp_cache.json`

### CSV column names not recognized

```
ERROR: CSV missing required columns: {'Zmien'}
```

**Solution**:
- Check CSV has correct Binance column names: `Czas`, `Operacja`, `Moneta`, `Zmien`
- If exported from different exchange, may need conversion first

### Unknown operation type

```
WARNING: Row 42: unknown_operation - Unknown operation type: "Some New Op"
```

**Solution**:
- Check if operation is new (Binance adds new ones periodically)
- Update `OperationClassifier.classify()` method or add mapping
- Or ignore with configuration

### Validation errors in many rows

```
50 validation errors encountered
```

**Solution**:
- Use `python cli.py validate` to see details
- Check data types (dates should be YYYY-MM-DD HH:MM:SS)
- Ensure numeric columns are numbers, not text
- Look for encoding issues (use UTF-8)

---

## Preparing for Tax Filing (PIT-38)

### Before Filing

1. ✅ Run this module
2. ✅ Generate all reports
3. ✅ Review ledger CSV for accuracy
4. ✅ Verify exchange rates look reasonable
5. ✅ Check multi-year summary

### What to Include in PIT-38

From module output:

- **Section IIA - Income**: Use `total_revenue_pln` from summary
- **Section III - Deductions**: Use `total_costs_pln` from summary
- **Taxable Income**: Use `dochód_do_opodatkowania` from summary
- **Tax Due**: Calculated automatically at 19% rate

### Supporting Documentation

Keep with your tax filing:

- `tax_report_ledger.csv` (transaction details)
- `tax_report_summary.csv` (annual summary)
- Original Binance CSV export
- NBP rate cache (shows rates applied)

### When Requesting Extension

If tax authority questions your report, provide:

1. Complete ledger showing all transactions
2. Explanation of operation classifications
3. NBP rates used (with dates)
4. Original Binance export
5. This module documentation (shows methodology)

---

## Advanced Topics

### Custom Operation Classification

```python
from normalizer import OperationClassifier, OperationType, TaxEventType

class CustomClassifier(OperationClassifier):
    def get_tax_event_type(self, operation_type, asset):
        # Treat airdrops as taxable
        if operation_type == OperationType.AIRDROP:
            return TaxEventType.REVENUE
        return super().get_tax_event_type(operation_type, asset)

processor = DataProcessor(classifier=CustomClassifier())
```

### Batch Processing

```python
from pathlib import Path
from processor import DataProcessor
from reporter import ReportGenerator

csv_files = Path(".").glob("binance_*.csv")

for csv_file in csv_files:
    processor = DataProcessor()
    report = processor.process(csv_file)
    
    reporter = ReportGenerator(output_dir=f"reports/{csv_file.stem}")
    reporter.generate_all(report)
```

### Integration with Other Tools

Export JSON and consume in another system:

```python
import json

with open("tax_report.json") as f:
    data = json.load(f)

# Use in accounting software, database, etc.
```

---

## Getting Help

### Check Documentation

1. `README.md` - Technical overview and API reference
2. `POLISH_TAX_LAW_GUIDE.md` - Legal framework and detailed explanations
3. Code comments - Inline documentation in each module
4. `tests.py` - Usage examples

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

processor = DataProcessor()
# Now see detailed logs during processing
```

### Common Questions

**Q: Can I process multiple exchanges together?**  
A: Exports need to be in Binance format. If using other exchanges, convert first.

**Q: What if I have transactions from 2023 and earlier?**  
A: Set `tax_year` in config and process separately. Carry losses forward manually.

**Q: Is staking income taxable?**  
A: Configurable. Conservative (default): No. Progressive: Yes. Check with advisor.

**Q: What about fees paid in different coins?**  
A: Automatically converted to PLN using T-1 rates.

**Q: Can I lose money and offset future income?**  
A: Yes - losses carry forward automatically across years.

---

## Next Steps

1. **Export your Binance data** for the full tax year
2. **Run the validation**: `python cli.py validate binance_export.csv`
3. **Process the data**: `python cli.py process binance_export.csv`
4. **Review outputs** in the reports directory
5. **Consult a tax professional** before filing
6. **File your PIT-38** with the calculated amounts

---

**For questions or issues, refer to:**
- Module documentation in README.md
- Polish tax law guide in POLISH_TAX_LAW_GUIDE.md
- Code comments in source files
- Unit tests in tests.py for API examples

