"""
Configuration loading and validation for the tax calculator.

Handles loading configuration from YAML files with sensible defaults and validation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .types import TaxConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "tax_year": 2026,
    "fiat_currencies": ["PLN", "USD", "EUR", "GBP"],
    "stablecoin_map": {
        "USDT": "USD",
        "USDC": "USD",
        "BUSD": "USD",
        "TUSD": "USD",
        "EURT": "EUR",
        "EUROC": "EUR",
    },
    "nbp_table": "A",
    "nbp_base_url": "https://api.nbp.pl/api/exchangerates/rates",
    "nbp_cache_path": "data/external/nbp_rate_cache.json",
    "ignore_operations": [
        "Transaction Buy",
        "Transaction Spend",
        "Binance Convert",
        "Deposit",
        "Withdraw",
    ],
    "optional_operations": ["Airdrop", "Reward", "Staking", "Earn"],
}


def load_tax_config(path: Path | str = "config/tax_config.yml") -> TaxConfig:
    """
    Load tax configuration from YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        TaxConfig instance with merged defaults and file values.

    Raises:
        ValueError: If critical configuration is invalid.
    """
    config_path = Path(path)
    
    if config_path.exists():
        logger.info("Loading configuration from %s", config_path)
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        logger.warning("Config file not found at %s, using defaults", config_path)
        raw = {}

    # Merge with defaults, file values override defaults
    merged = {**DEFAULT_CONFIG, **raw}
    
    # Validate required fields
    if not merged.get("fiat_currencies"):
        raise ValueError("fiat_currencies must be configured")
    
    if not merged.get("nbp_base_url"):
        raise ValueError("nbp_base_url must be configured")

    # Create cache directory if needed
    cache_path = Path(merged["nbp_cache_path"])
    if not cache_path.parent.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Created cache directory: %s", cache_path.parent)

    config = TaxConfig(
        tax_year=int(merged.get("tax_year", 2026)),
        fiat_currencies=[str(x).upper().strip() for x in merged["fiat_currencies"]],
        stablecoin_map={
            str(k).upper().strip(): str(v).upper().strip()
            for k, v in merged.get("stablecoin_map", {}).items()
        },
        nbp_table=str(merged["nbp_table"]).upper().strip(),
        nbp_base_url=str(merged["nbp_base_url"]).strip(),
        nbp_cache_path=cache_path,
        ignore_operations=[str(x).strip() for x in merged.get("ignore_operations", [])],
        optional_operations=[str(x).strip() for x in merged.get("optional_operations", [])],
    )
    
    logger.debug("Configuration loaded successfully")
    return config

