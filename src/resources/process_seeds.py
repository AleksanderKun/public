"""Resource script for processing seed data."""

import csv
from pathlib import Path
from typing import Dict, List

# Assuming seed data is in dbt/seeds
SEED_DIR = Path(__file__).parent.parent.parent / "dbt" / "seeds"


def load_csv_seed(filename: str) -> List[Dict[str, str]]:
    """Load a generic CSV seed from the dbt seeds directory."""
    csv_path = SEED_DIR / filename
    if not csv_path.exists():
        raise FileNotFoundError(f"Seed file not found: {csv_path}")

    with csv_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def load_sample_data() -> List[Dict[str, str]]:
    """Load the sample_data seed."""
    return load_csv_seed('sample_data.csv')


def load_binance_data() -> List[Dict[str, str]]:
    """Load the Binance seed data."""
    return load_csv_seed('Binance_sample_UTC+2_KG.csv')


def process_sample_data(data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Process the simple sample data seed."""
    for row in data:
        row['enhanced_value'] = float(row['value']) * 1.1
    return data


def process_binance_data(data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Process the Binance seed data and normalize numeric fields."""
    for row in data:
        raw_value = row.get('Zmien', '')
        row['Zmien'] = raw_value.replace(',', '') if isinstance(raw_value, str) else raw_value
        try:
            row['Zmien'] = float(row['Zmien'])
        except (ValueError, TypeError):
            row['Zmien'] = None
        row['symbol'] = row.get('Moneta', '').strip()
    return data


if __name__ == "__main__":
    sample_path = SEED_DIR / 'sample_data.csv'
    if sample_path.exists():
        print('Sample data preview:')
        sample = load_sample_data()
        sample_processed = process_sample_data(sample)
        for row in sample_processed[:3]:
            print(row)
    else:
        print('sample_data.csv not found, skipping sample preview.')

    print('\nBinance data preview:')
    binance = load_binance_data()
    binance_processed = process_binance_data(binance)
    for row in binance_processed[:3]:
        print(row)
