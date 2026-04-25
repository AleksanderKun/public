"""
Command-line interface for cryptocurrency tax calculation.

Provides commands for:
- Processing Binance CSV exports
- Validating data
- Generating reports
- Managing cache
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from processor import DataProcessor
from nbp_provider import NBPRateProvider
from normalizer import OperationClassifier
from reporter import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def load_config(config_path: Optional[Path]) -> dict:
    """Load YAML configuration file."""
    if not config_path or not config_path.exists():
        logger.warning("No config file found, using defaults")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        logger.info(f"Loaded config from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


@click.group()
@click.option(
    '--config',
    type=click.Path(exists=True),
    help='Path to YAML config file'
)
@click.pass_context
def cli(ctx, config: Optional[str]):
    """Cryptocurrency tax calculation tool for Polish tax law (PIT-38)."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = load_config(Path(config) if config else None)


@cli.command()
@click.argument('csv_file', type=click.Path(exists=True))
@click.option(
    '--output-dir',
    type=click.Path(),
    default='.',
    help='Output directory for reports'
)
@click.option(
    '--cache-file',
    type=click.Path(),
    help='NBP rate cache file'
)
@click.option(
    '--treat-airdrops',
    is_flag=True,
    help='Treat airdrops as taxable income'
)
@click.pass_context
def process(
    ctx,
    csv_file: str,
    output_dir: str,
    cache_file: Optional[str],
    treat_airdrops: bool,
):
    """
    Process Binance CSV export and calculate tax.
    
    CSV_FILE: Path to Binance export CSV
    """
    try:
        config = ctx.obj.get('config', {})
        
        # Setup output directory
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Setup NBP provider
        cache_path = None
        if cache_file:
            cache_path = Path(cache_file)
        elif 'nbp_cache_path' in config:
            cache_path = Path(config['nbp_cache_path'])
        else:
            cache_path = out_path / "nbp_cache.json"
        
        nbp_provider = NBPRateProvider(cache_path=cache_path)
        
        # Setup classifier
        treat_airdrops = treat_airdrops or config.get('treat_airdrops_as_income', False)
        classifier = OperationClassifier(treat_airdrops_as_income=treat_airdrops)
        
        # Create processor
        processor = DataProcessor(
            nbp_provider=nbp_provider,
            classifier=classifier,
            treat_airdrops_as_income=treat_airdrops,
        )
        
        # Process CSV
        click.echo(f"Processing {csv_file}...")
        report = processor.process(Path(csv_file))
        
        # Generate reports
        click.echo(f"Generating reports to {output_dir}...")
        reporter = ReportGenerator(output_dir=out_path)
        reporter.generate_all(report)
        reporter.print_summary(report)
        
        # Print validation errors if any
        errors = processor.get_validation_errors()
        if errors:
            click.echo(f"\n⚠️  {len(errors)} validation errors encountered:")
            for error in errors[:5]:  # Show first 5
                click.echo(f"  Row {error.row_index}: {error.error_type}")
            if len(errors) > 5:
                click.echo(f"  ... and {len(errors) - 5} more")
        
        click.echo("✅ Processing complete!")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Processing failed")
        sys.exit(1)


@cli.command()
@click.argument('csv_file', type=click.Path(exists=True))
@click.pass_context
def validate(ctx, csv_file: str):
    """
    Validate Binance CSV format without calculating tax.
    
    CSV_FILE: Path to Binance export CSV
    """
    try:
        classifier = OperationClassifier()
        
        processor = DataProcessor(classifier=classifier)
        
        click.echo(f"Validating {csv_file}...")
        processor.load_csv(Path(csv_file))
        success_count, error_count = processor.normalize_and_classify()
        
        click.echo(f"\n✅ Loaded {success_count} valid transactions")
        
        if error_count > 0:
            click.echo(f"\n⚠️  {error_count} validation errors:")
            for error in processor.get_validation_errors():
                click.echo(f"  Row {error.row_index}: {error.error_type} - {error.message}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Validation failed")
        sys.exit(1)


@cli.command()
@click.option(
    '--cache-file',
    type=click.Path(exists=True),
    help='NBP rate cache file to clear'
)
@click.confirmation_option(prompt='Are you sure you want to clear the cache?')
def clear_cache(cache_file: Optional[str]):
    """
    Clear NBP exchange rate cache.
    """
    try:
        if not cache_file:
            click.echo("❌ No cache file specified. Use --cache-file")
            sys.exit(1)
        
        cache_path = Path(cache_file)
        if cache_path.exists():
            cache_path.unlink()
            click.echo(f"✅ Cleared cache: {cache_file}")
        else:
            click.echo(f"ℹ️  Cache file not found: {cache_file}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--cache-file',
    type=click.Path(),
    help='NBP rate cache file'
)
def cache_info(cache_file: Optional[str]):
    """
    Display NBP cache statistics.
    """
    try:
        cache_path = Path(cache_file) if cache_file else None
        nbp_provider = NBPRateProvider(cache_path=cache_path)
        stats = nbp_provider.get_cache_stats()
        
        click.echo(f"Cache entries: {stats['entries']}")
        click.echo(f"Cache path: {stats['path']}")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def config_template():
    """
    Print configuration file template.
    """
    template = """
# Tax calculation configuration for Polish crypto tax law (PIT-38)

tax_year: 2026

# Fiat currencies recognized for tax calculations
fiat_currencies:
  - PLN
  - USD
  - EUR
  - GBP
  - CHF

# Stablecoin to fiat currency mapping
stablecoin_map:
  USDT: USD
  USDC: USD
  BUSD: USD
  TUSD: USD
  DAI: USD
  EURT: EUR
  EUROC: EUR

# NBP API settings
nbp_table: A                              # Table A = daily rates
nbp_base_url: https://api.nbp.pl/api/exchangerates/rates
nbp_cache_path: data/external/nbp_cache.json

# Treatment of special operations
treat_airdrops_as_income: false           # Conservative: ignore airdrops
treat_staking_as_income: false            # Conservative: ignore staking

# Operations to ignore (crypto-crypto, transfers)
ignore_operations:
  - Transaction Buy
  - Transaction Spend
  - Binance Convert
  - Deposit
  - Withdraw

# Optional operations (may require special handling)
optional_operations:
  - Airdrop
  - Reward
  - Staking
  - Earn
"""
    click.echo(template)


def main():
    """Entry point for CLI."""
    cli(obj={})


if __name__ == '__main__':
    main()
