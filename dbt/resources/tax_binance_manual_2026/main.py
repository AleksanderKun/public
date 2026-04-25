import polars as pl
import requests
import json
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# --- KONFIGURACJA ŚCIEŻEK ---
# Lokalizacja skryptu: dbt/resources/tax_binance_2026/main.py
CURRENT_DIR = Path(__file__).resolve().parent
DBT_ROOT = CURRENT_DIR.parent.parent  # Wyjście do folderu dbt/

# Ścieżka do danych wejściowych
CSV_PATH = DBT_ROOT / "seeds" / "Binance_2026_KG" / "Binance_sample_UTC+2_KG.csv"

# Lokalizacja plików wynikowych (tam gdzie ten skrypt)
OUTPUT_DIR = CURRENT_DIR 
CACHE_FILE = OUTPUT_DIR / "nbp_cache.json"

logging.basicConfig(level=logging.INFO, format='%(message)s')

class NBPRateProvider:
    """Obsługa kursów NBP z cache'owaniem i zasadą T-1."""
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache = self._load()

    def _load(self):
        if self.cache_path.exists():
            with open(self.cache_path, 'r', encoding='utf-8') as f: 
                return json.load(f)
        return {"PLN": 1.0}

    def save(self):
        with open(self.cache_path, 'w', encoding='utf-8') as f: 
            json.dump(self.cache, f)

    def get_rate(self, currency: str, date: datetime) -> float:
        if currency in ["USDC", "USDT", "BUSD"]: currency = "USD"
        if currency == "PLN": return 1.0
        
        target_date = date - timedelta(days=1)
        date_str = target_date.strftime("%Y-%m-%d")
        cache_key = f"{currency}_{date_str}"

        if cache_key in self.cache: 
            return self.cache[cache_key]

        for i in range(10):
            search_date = (target_date - timedelta(days=i)).strftime("%Y-%m-%d")
            url = f"https://api.nbp.pl/api/exchangerates/rates/A/{currency}/{search_date}/?format=json"
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    val = r.json()['rates'][0]['mid']
                    self.cache[cache_key] = val
                    return val
            except: 
                continue
        return 1.0

def process_year(year: int):
    """Przetwarza dany rok i generuje szczegółowy ledger CSV w folderze skryptu."""
    nbp = NBPRateProvider(CACHE_FILE)
    
    if not CSV_PATH.exists():
        logging.error(f"BŁĄD: Nie znaleziono pliku CSV w: {CSV_PATH}")
        return None

    try:
        df = pl.read_csv(CSV_PATH).with_columns([
            pl.col("Czas").str.to_datetime("%y-%m-%d %H:%M:%S"),
            pl.col("Zmien").cast(pl.Float64)
        ]).sort("Czas")
    except Exception as e:
        logging.error(f"Błąd podczas wczytywania CSV: {e}")
        return None

    df_filtered = df.filter(pl.col("Czas").dt.year() == year)
    
    if df_filtered.is_empty(): 
        return {"rok": year, "przychod": 0.0, "koszt": 0.0}

    tax_entries = []
    total_revenue = 0.0
    total_costs = 0.0
    
    FIAT_CURRENCIES = ["EUR", "PLN", "USD", "GBP"]

    for row in df_filtered.iter_rows(named=True):
        op = row['Operacja']
        moneta = row['Moneta']
        amount = abs(row['Zmien'])
        date = row['Czas']
        
        is_taxable = False
        val_pln = 0.0
        rate = 0.0
        tax_type = ""

        if op == "Buy Crypto With Fiat":
            rate = nbp.get_rate(moneta, date)
            val_pln = amount * rate
            total_costs += val_pln
            is_taxable = True
            tax_type = "KOSZT (Zakup)"
            
        elif op == "Deposit" and moneta in FIAT_CURRENCIES:
            rate = nbp.get_rate(moneta, date)
            val_pln = amount * rate
            total_costs += val_pln
            is_taxable = True
            tax_type = "KOSZT (Depozyt)"
            
        elif op in ["Withdraw", "Fiat Withdraw"] and moneta in FIAT_CURRENCIES:
            rate = nbp.get_rate(moneta, date)
            val_pln = amount * rate
            total_revenue += val_pln
            is_taxable = True
            tax_type = "PRZYCHÓD"

        if is_taxable:
            tax_entries.append({
                "Data": date,
                "Operacja": op,
                "Waluta": moneta,
                "Ilość": amount,
                "Kurs_NBP_T1": round(rate, 4),
                "PLN_Wartość": round(val_pln, 2),
                "Typ_PIT": tax_type
            })

    if tax_entries:
        output_file = OUTPUT_DIR / f"tax_ledger_{year}.csv"
        pl.DataFrame(tax_entries).write_csv(output_file)
        nbp.save()
        logging.info(f"✅ Rok {year}: Zapisano ledger do {output_file.name}")
    
    return {"rok": year, "przychod": round(total_revenue, 2), "koszt": round(total_costs, 2)}

def create_zip(years: list):
    """Pakuje raporty do ZIP w folderze skryptu."""
    zip_path = OUTPUT_DIR / "raporty_podatkowe_KG.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for y in years:
            f = OUTPUT_DIR / f"tax_ledger_{y}.csv"
            if f.exists(): 
                zipf.write(f, arcname=f.name)
        
        summary_f = OUTPUT_DIR / "final_summary.csv"
        if summary_f.exists(): 
            zipf.write(summary_f, arcname=summary_f.name)
            
    logging.info(f"📦 Archiwum ZIP utworzone: {zip_path}")

if __name__ == "__main__":
    summary_data = []
    lata_do_procesu = [2024, 2025, 2026]

    for y in lata_do_procesu:
        res = process_year(y)
        if res:
            summary_data.append(res)

    if summary_data:
        summary_df = pl.DataFrame(summary_data)
        
        summary_df = summary_df.with_columns([
            (pl.col("przychod") - pl.col("koszt")).alias("dochod_strata")
        ]).with_columns([
            pl.when(pl.col("dochod_strata") > 0)
            .then(pl.col("dochod_strata") * 0.19)
            .otherwise(0.0)
            .alias("podatek_19_procent")
        ])
        
        summary_path = OUTPUT_DIR / "final_summary.csv"
        summary_df.write_csv(summary_path)
        
        print("\n" + "="*60)
        print("📊 ZBIORCZE PODSUMOWANIE PODATKOWE (PIT-38)")
        print(f"Pliki zapisane w: {OUTPUT_DIR}")
        print("="*60)
        print(summary_df)
        print("="*60)
        
        create_zip(lata_do_procesu)
    else:
        logging.warning("Brak danych do przetworzenia.")