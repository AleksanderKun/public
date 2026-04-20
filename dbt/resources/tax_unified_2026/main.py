import json
import logging
import sys
import zipfile
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DBT_ROOT = CURRENT_DIR.parent.parent
REPO_ROOT = CURRENT_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.tax.config import load_tax_config
from src.tax.processor import CryptoTaxCalculator

logging.basicConfig(level=logging.INFO, format="%(message)s")

CONFIG_PATH = REPO_ROOT / "config" / "tax_config.yml"
BINANCE_CSV = DBT_ROOT / "seeds" / "Binance_2026_KG" / "Binance_sample_UTC+2_KG.csv"
BYBIT_CSV = DBT_ROOT / "seeds" / "Bybit_2026_AK" / "AssetChangeDetails_uta_375404132_20250101_20251231_0.csv"
OUTPUT_DIR = CURRENT_DIR


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def write_summary_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    import polars as pl

    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(path)


def create_zip(files: list[Path], zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files:
            if file_path.exists():
                zipf.write(file_path, arcname=file_path.name)


class UnifiedTaxResource:
    def __init__(self, config_path: Path):
        self.config = load_tax_config(config_path)
        self.calculator = CryptoTaxCalculator(self.config)

    def process_file(self, name: str, csv_path: Path) -> dict:
        if not csv_path.exists():
            logging.error(f"Plik wejściowy nie istnieje: {csv_path}")
            return {
                "source": name,
                "processed": 0,
                "ignored": 0,
                "total_cost_pln": 0.0,
                "total_revenue_pln": 0.0,
                "income_pln": 0.0,
            }

        logging.info(f"Przetwarzanie {name}: {csv_path}")
        summary, ledger = self.calculator.compute_tax(csv_path)

        ledger_path = OUTPUT_DIR / f"{name}_tax_ledger.csv"
        ledger.write_csv(ledger_path)
        logging.info(f"Zapisano ledger: {ledger_path.name}")

        summary_path = OUTPUT_DIR / f"{name}_tax_summary.json"
        save_json(summary.to_dict(), summary_path)
        logging.info(f"Zapisano podsumowanie JSON: {summary_path.name}")

        return {
            "source": name,
            "tax_year": summary.tax_year,
            "transactions_processed": summary.transactions_processed,
            "transactions_ignored": summary.transactions_ignored,
            "total_cost_pln": summary.total_cost_pln,
            "total_revenue_pln": summary.total_revenue_pln,
            "income_pln": summary.income,
            "loss_to_carry_pln": summary.loss_to_carry,
            "ledger_path": str(ledger_path.name),
            "summary_path": str(summary_path.name),
        }

    def run(self) -> None:
        results = []
        results.append(self.process_file("binance", BINANCE_CSV))
        results.append(self.process_file("bybit", BYBIT_CSV))

        summary_rows = [
            {
                "source": result["source"],
                "tax_year": result["tax_year"],
                "processed": result["transactions_processed"],
                "ignored": result["transactions_ignored"],
                "cost_pln": result["total_cost_pln"],
                "revenue_pln": result["total_revenue_pln"],
                "income_pln": result["income_pln"],
                "loss_to_carry_pln": result["loss_to_carry_pln"],
            }
            for result in results
        ]

        summary_csv = OUTPUT_DIR / "tax_unified_summary.csv"
        write_summary_csv(summary_rows, summary_csv)
        logging.info(f"Zapisano zbiorcze podsumowanie: {summary_csv.name}")

        zip_path = OUTPUT_DIR / "tax_unified_reports.zip"
        create_zip(
            [
                OUTPUT_DIR / "binance_tax_ledger.csv",
                OUTPUT_DIR / "binance_tax_summary.json",
                OUTPUT_DIR / "bybit_tax_ledger.csv",
                OUTPUT_DIR / "bybit_tax_summary.json",
                summary_csv,
            ],
            zip_path,
        )
        logging.info(f"Utworzono archiwum: {zip_path.name}")

        print("\n" + "=" * 60)
        print("📊 Unified tax report summary")
        for row in summary_rows:
            print(row)
        print("=" * 60)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runner = UnifiedTaxResource(CONFIG_PATH)
    runner.run()
