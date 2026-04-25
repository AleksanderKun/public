"""Configuration settings for the data project."""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"

# dbt paths
DBT_DIR = PROJECT_ROOT / "dbt"
DBT_MODELS_DIR = DBT_DIR / "models"

# Database settings (for DuckDB)
DATABASE_PATH = PROJECT_ROOT / "data" / "warehouse.db"

# Other configs
LOG_LEVEL = "INFO"
