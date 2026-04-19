# Data Analytics Project

A production-grade data analytics and machine learning repository built with modern data stack.

## Project Purpose

This project provides a scalable, maintainable framework for data ingestion, processing, transformation, and analytics using dbt, Python, and SQL.

## Architecture

```
project-root/
├── data/                 # Data storage
│   ├── raw/             # Raw ingested data
│   ├── processed/       # Cleaned/processed data
│   └── external/        # External datasets
├── notebooks/           # Exploratory analysis
├── src/                 # Python source code
│   ├── config/          # Configuration files
│   ├── ingestion/       # Data ingestion scripts
│   ├── processing/      # Data processing logic
│   ├── features/        # Feature engineering
│   ├── models/          # ML models
│   └── utils/           # Utility functions
├── dbt/                 # dbt transformations
│   ├── models/
│   │   ├── staging/     # Source-aligned models
│   │   ├── intermediate/ # Business logic
│   │   └── marts/       # Final BI/ML models
│   ├── seeds/           # Static data
│   ├── snapshots/       # Slowly changing dimensions
│   ├── tests/           # Custom tests
│   └── macros/          # Reusable SQL macros
├── tests/               # Python tests
└── scripts/             # Utility scripts
```

## Tech Stack

- **Python 3.11+**: Core language
- **dbt**: Data transformations
- **DuckDB**: Default database (can be changed)
- **Polars/Pandas**: Data processing
- **scikit-learn/XGBoost**: ML
- **Poetry**: Dependency management

## Data Sources

- [Add your data sources here]

## Automated Activity

This repository includes automated workflows that simulate realistic development activity:
- Random commits with varied messages
- Updates to documentation, scripts, and models
- Activity occurs ~30% of days to appear natural

See [activity_log.md](activity_log.md) for details.

## How to Run

### Setup

1. Install Poetry: `pip install poetry`
2. Install dependencies: `poetry install`
3. Activate environment: `poetry shell`

### dbt

1. Navigate to dbt folder: `cd dbt`
2. Run models: `dbt run`
3. Test: `dbt test`

### Python Scripts

Run from project root:

```bash
python src/ingestion/main.py
```

## Development

- Use `poetry add` to add dependencies
- Run tests: `pytest`
- Lint: `ruff check` and `black .`

## Contributing

[Add contribution guidelines]