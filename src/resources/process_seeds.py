"""Resource script for processing seed data."""

import pandas as pd
from pathlib import Path

# Assuming seed data is in dbt/seeds
SEED_DIR = Path(__file__).parent.parent.parent / "dbt" / "seeds"

def load_sample_data() -> pd.DataFrame:
    """Load sample data from CSV seed."""
    csv_path = SEED_DIR / "sample_data.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(f"Seed file not found: {csv_path}")

def process_sample_data(df: pd.DataFrame) -> pd.DataFrame:
    """Process the sample data."""
    # Example processing: add enhanced value
    df['enhanced_value'] = df['value'] * 1.1
    return df

if __name__ == "__main__":
    df = load_sample_data()
    processed_df = process_sample_data(df)
    print(processed_df.head())