import polars as pl
import requests
import json
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# --- KONFIGURACJA ŚCIEŻEK ---
CURRENT_DIR = Path(__file__).resolve().parent
DBT_ROOT = CURRENT_DIR.parent.parent
CSV_PATH = DBT_ROOT / "seeds" / "Bybit_2026_AK" / "AssetChangeDetails_uta_375404132_20250101_20251231_0.csv"
OUTPUT_DIR = CURRENT_DIR 
CACHE_FILE = OUTPUT_DIR / "nbp_cache.json"

logging.basicConfig(level=logging.INFO, format='%(message)s')

class NBPRateProvider:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache = self._load()

    def _load(self):
        if self.cache_path.exists():
            with open(self.cache_path, 'r', encoding='utf-8') as f: return json.load(f)
        return {"PLN": 1.0}

    def save(self):
        with open(self.cache_path, 'w', encoding='utf-8') as f: json.dump(self.cache, f)

    def get_rate(self, currency: str, date: datetime) -> float:
        if currency in ["USDC", "USDT", "BUSD"]: currency = "USD"
        if currency == "PLN": return 1.0
        target_date = date - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")
        cache_key = f"{currency}_{date_str}"
        if cache_key in self.cache: return self.cache[cache_key]

        for i in range(10):
            search_date = (target_date - timedelta(days=i)).strftime("%Y-%m-%d")
            url = f"https://api.nbp.pl/api/exchangerates/rates/A/{currency}/{search_date}/?format=json"
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    val = r.json()['rates'][0]['mid']
                    self.cache[cache_key] = val
                    return val
            except: continue
        return 1.0

def process_bybit_tax(year: int):
    nbp = NBPRateProvider(CACHE_FILE)
    
    if not CSV_PATH.exists():
        logging.error(f"Nie znaleziono pliku: {CSV_PATH}")
        return None

    try:
        # KLUCZOWA ZMIANA: skip_rows=1 (pomijamy linię z UID)
        df = pl.read_csv(
            CSV_PATH, 
            skip_rows=1,
            infer_schema_length=10000,
            truncate_ragged_lines=True,
            ignore_errors=True
        )
        
        # Konwersja czasu i kwot (format ISO: 2025-08-28 16:08:58)
        df = df.with_columns([
            pl.col("Time(UTC)").str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False),
            pl.col("Change").cast(pl.Float64, strict=False)
        ]).filter(pl.col("Time(UTC)").is_not_null()).sort("Time(UTC)")
        
    except Exception as e:
        logging.error(f"Błąd czytania CSV: {e}")
        return None

    df_filtered = df.filter(pl.col("Time(UTC)").dt.year() == year)
    if df_filtered.is_empty(): 
        return {"rok": year, "przychod": 0.0, "koszt": 0.0}

    tax_entries = []
    total_costs = 0.0
    FIAT_CURRENCIES = ["EUR", "PLN", "USD", "GBP"]

    for row in df_filtered.iter_rows(named=True):
        # Szukamy TRADE BUY, gdzie płacimy walutą FIAT (ujemny Change)
        if row['Type'] == "TRADE" and row['Direction'] == "BUY" and row['Currency'] in FIAT_CURRENCIES:
            change = row['Change']
            if change and change < 0:
                date = row['Time(UTC)']
                currency = row['Currency']
                rate = nbp.get_rate(currency, date)
                val_pln = abs(change) * rate
                total_costs += val_pln

                tax_entries.append({
                    "Data": date,
                    "Waluta": currency,
                    "Kwota_Fiat": abs(change),
                    "Kurs_NBP_T1": round(rate, 4),
                    "Koszt_PLN": round(val_pln, 2),
                    "Kontrakt": row.get('Contract', '')
                })

    if tax_entries:
        out_path = OUTPUT_DIR / f"tax_bybit_ledger_{year}.csv"
        pl.DataFrame(tax_entries).write_csv(out_path)
        nbp.save()
        logging.info(f"✅ Rok {year}: Przetworzono {len(tax_entries)} transakcji.")
    
    return {"rok": year, "przychod": 0.0, "koszt": round(total_costs, 2)}

if __name__ == "__main__":
    summary_data = []
    for y in [2024, 2025, 2026]:
        res = process_bybit_tax(y)
        if res: summary_data.append(res)

    if summary_data:
        summary_df = pl.DataFrame(summary_data)
        summary_path = OUTPUT_DIR / "final_summary_bybit.csv"
        summary_df.write_csv(summary_path)
        print("\n📊 PODSUMOWANIE BYBIT\n", summary_df)