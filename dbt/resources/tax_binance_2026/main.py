"""
Main script for cryptocurrency tax calculation - Polish Tax Law (PIT-38).

This is a production-grade tax calculation engine for cryptocurrency transactions
exported from Binance, following Polish tax law requirements as of 2026.

USAGE:
    python main.py [command] [options]

For CLI help:
    python main.py --help

KEY FEATURES:
- Global cost pooling (not FIFO) per Polish law
- Multi-year tax calculation with loss carry-forward
- NBP exchange rate integration with T-1 rule
- Comprehensive data validation
- Multiple report formats (CSV, JSON, text)
"""

import logging
import sys
from pathlib import Path

from processor import DataProcessor
from nbp_provider import NBPRateProvider
from normalizer import OperationClassifier
from reporter import ReportGenerator
from cli import cli

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main_simple(csv_path: str, output_dir: str = ".", cache_file: str = None):
    """
    Simple entry point for direct script execution.

    Args:
        csv_path: Path to Binance CSV export
        output_dir: Output directory for reports
        cache_file: Optional NBP cache file path
    """
    try:
        csv_path = Path(csv_path)
        output_dir = Path(output_dir)

        # Setup providers
        cache_path = Path(cache_file) if cache_file else output_dir / "nbp_cache.json"
        nbp_provider = NBPRateProvider(cache_path=cache_path)
        classifier = OperationClassifier(treat_airdrops_as_income=False)

        # Create processor
        processor = DataProcessor(
            nbp_provider=nbp_provider,
            classifier=classifier,
            treat_airdrops_as_income=False,
        )

        # Process
        logger.info(f"Processing {csv_path}...")
        report = processor.process(csv_path)

        # Generate reports
        logger.info(f"Generating reports to {output_dir}...")
        output_dir.mkdir(parents=True, exist_ok=True)
        reporter = ReportGenerator(output_dir=output_dir)
        reporter.generate_all(report)
        reporter.print_summary(report)

        # Show errors
        errors = processor.get_validation_errors()
        if errors:
            logger.warning(f"{len(errors)} validation errors encountered")
            for error in errors[:5]:
                logger.warning(f"  Row {error.row_index}: {error.error_type}")

        logger.info("✅ Processing complete!")
        return 0

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    # If run with command line arguments, use CLI
    if len(sys.argv) > 1:
        cli()
    else:
        # Otherwise, use default simple mode
        # Adjust these paths as needed:
        CURRENT_DIR = Path(__file__).resolve().parent
        DBT_ROOT = CURRENT_DIR.parent.parent

        CSV_PATH = (
            DBT_ROOT / "seeds" / "Binance_2026_KG" / "Binance_sample_UTC+2_KG.csv"
        )
        OUTPUT_DIR = CURRENT_DIR

        if CSV_PATH.exists():
            exit_code = main_simple(
                str(CSV_PATH),
                str(OUTPUT_DIR),
                str(OUTPUT_DIR / "nbp_cache.json"),
            )
            sys.exit(exit_code)
        else:
            logger.error(f"CSV file not found at {CSV_PATH}")
            logger.info("Usage: python main.py --help")
            sys.exit(1)
