"""
Command-line interface for the cryptocurrency tax calculator.

Provides a complete CLI for calculating tax obligations and exporting results.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import load_tax_config
from .processor import CryptoTaxCalculator
from .validation import TransactionValidator


# Configure logging
def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging for CLI."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Cryptocurrency tax calculator for Polish PIT-38 (2026)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic calculation
  python -m src.tax.cli --input transactions.csv

  # With validation and debug logging
  python -m src.tax.cli --input transactions.csv --validate --verbose

  # Export to multiple formats
  python -m src.tax.cli --input transactions.csv --ledger-csv ledger.csv --ledger-json ledger.json

  # Use custom config
  python -m src.tax.cli --input transactions.csv --config custom_config.yml

See README.md for detailed documentation.
        """,
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to Binance or Bybit CSV input file (required)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/tax_config.yml"),
        help="Path to tax configuration YAML (default: config/tax_config.yml)",
    )

    parser.add_argument(
        "--ledger-csv",
        type=Path,
        default=Path("tax_ledger.csv"),
        help="Output CSV path for detailed transaction ledger (default: tax_ledger.csv)",
    )

    parser.add_argument(
        "--ledger-json",
        type=Path,
        default=None,
        help="Output JSON path for detailed transaction ledger (optional)",
    )

    parser.add_argument(
        "--summary-json",
        type=Path,
        default=Path("tax_summary.json"),
        help="Output JSON path for tax summary (default: tax_summary.json)",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run data validation before tax calculation",
    )

    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Include optional operations (Airdrops, Rewards) as taxable income",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console output (errors only)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_arguments()

    # Configure logging
    if args.quiet:
        log_level = logging.ERROR
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    configure_logging(level=log_level)
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("Cryptocurrency Tax Calculator for Polish PIT-38 (2026)")
    logger.info("=" * 70)

    try:
        # Validate input file
        if not args.input.exists():
            logger.error("Input file not found: %s", args.input)
            return 1

        # Load configuration
        logger.info("Loading configuration from %s", args.config)
        config = load_tax_config(args.config)
        logger.info("Configuration loaded successfully (Tax Year: %d)", config.tax_year)

        # Validate data if requested
        if args.validate:
            logger.info("Running data validation...")
            validator = TransactionValidator()
            results = validator.validate_csv(args.input)
            validator.print_report()

            if not results["is_valid"]:
                logger.error(
                    "Validation failed with %d error(s)", results["error_count"]
                )
                return 1

            logger.info("Validation passed!")

        # Create calculator
        calculator = CryptoTaxCalculator(config)

        # Compute tax
        logger.info("Computing tax obligations...")
        summary, ledger = calculator.compute_tax(
            args.input,
            include_optional=args.include_optional,
        )

        # Export results
        logger.info("Exporting results...")
        calculator.export_ledger_csv(ledger, args.ledger_csv)

        if args.ledger_json:
            calculator.export_ledger_json(ledger, args.ledger_json)

        calculator.export_summary_json(summary, args.summary_json)

        # Print summary
        logger.info("=" * 70)
        logger.info("TAX CALCULATION SUMMARY")
        logger.info("=" * 70)
        logger.info("Tax Year: %d", summary.tax_year)
        logger.info("Transactions Processed: %d", summary.transactions_processed)
        logger.info("Transactions Ignored: %d", summary.transactions_ignored)
        logger.info("-" * 70)
        logger.info("Total Costs (PLN): %.2f", summary.total_cost_pln)
        logger.info("Total Revenue (PLN): %.2f", summary.total_revenue_pln)
        logger.info("-" * 70)
        logger.info("Taxable Income (PLN): %.2f", summary.income)
        if summary.loss_to_carry > 0:
            logger.info("Loss to Carry Forward (PLN): %.2f", summary.loss_to_carry)
        logger.info("=" * 70)

        # Output JSON to console
        if not args.quiet:
            print("\nResults (JSON format):")
            print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))

        logger.info("✓ All files exported successfully")
        logger.info("  Ledger CSV: %s", args.ledger_csv)
        if args.ledger_json:
            logger.info("  Ledger JSON: %s", args.ledger_json)
        logger.info("  Summary JSON: %s", args.summary_json)

        return 0

    except Exception as e:
        logger.exception("Fatal error during tax calculation: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
