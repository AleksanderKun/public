"""
NBP (National Bank of Poland) exchange rate service.

Handles fetching and caching PLN exchange rates from the NBP API.
Uses T-1 (day before transaction) rates as required by Polish tax law.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Dict

import requests

from .types import TaxConfig

logger = logging.getLogger(__name__)

# Predefined rates for common fiat pairs (as fallback for known missing dates)
KNOWN_RATES = {
    "PLN_USD": {
        "2024-01-01": 3.96,
        "2024-12-31": 4.01,
    }
}

MAX_RETRIES = 14  # ~2 weeks of lookback for missing rates


class NBPRateService:
    """Fetches and caches NBP exchange rates."""

    def __init__(self, config: TaxConfig) -> None:
        """
        Initialize the NBP rate service.

        Args:
            config: Tax configuration containing NBP API details.
        """
        self.config = config
        self.memory: Dict[str, float] = {}
        self.cache_path = config.nbp_cache_path
        self._load_cache()
        logger.debug("NBPRateService initialized with cache at %s", self.cache_path)

    def _load_cache(self) -> None:
        """Load cached rates from disk."""
        if self.cache_path.exists():
            try:
                with self.cache_path.open("r", encoding="utf-8") as fp:
                    self.memory = json.load(fp)
                logger.debug(
                    "Loaded %d cached rates from %s", len(self.memory), self.cache_path
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load cache from %s: %s", self.cache_path, e)
                self.memory = {}
        else:
            logger.debug("Cache file not found, starting with empty cache")
            self.memory = {}

    def _save_cache(self) -> None:
        """Save cached rates to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("w", encoding="utf-8") as fp:
                json.dump(self.memory, fp, indent=2, ensure_ascii=False)
            logger.debug(
                "Saved cache with %d rates to %s", len(self.memory), self.cache_path
            )
        except IOError as e:
            logger.error("Failed to save cache to %s: %s", self.cache_path, e)

    def resolve_currency(self, asset: str) -> str:
        """
        Resolve asset to its trading currency.

        Stablecoins are mapped to their underlying currency (USDT → USD).

        Args:
            asset: Asset symbol (e.g., "USDT", "BTC", "USD").

        Returns:
            The trading currency (e.g., "USD", "BTC").
        """
        upper = asset.upper().strip()
        resolved = self.config.stablecoin_map.get(upper, upper)
        return resolved

    def get_rate(self, asset: str, transaction_date: date) -> float:
        """
        Get exchange rate for an asset on a specific date.

        Uses T-1 (day before transaction) rate as per Polish tax law.
        If T-1 is not available, goes back up to 14 days.

        Args:
            asset: Asset symbol.
            transaction_date: Date of the transaction.

        Returns:
            Exchange rate to PLN.

        Raises:
            ValueError: If no rate can be found after exhausting retries.
        """
        currency = self.resolve_currency(asset)

        if currency == "PLN":
            return 1.0

        # Use T-1 (day before)
        lookup_date = transaction_date - timedelta(days=1)
        key = f"{currency}_{lookup_date.isoformat()}"

        if key in self.memory:
            logger.debug(
                "Using cached rate for %s on %s: %.4f",
                currency,
                lookup_date,
                self.memory[key],
            )
            return float(self.memory[key])

        rate = self._fetch_rate(currency, lookup_date)
        self.memory[key] = rate
        self._save_cache()
        logger.debug(
            "Fetched and cached rate for %s on %s: %.4f", currency, lookup_date, rate
        )
        return rate

    def _fetch_rate(self, currency: str, lookup_date: date) -> float:
        """
        Fetch rate from NBP API, going back if date is unavailable.

        Args:
            currency: Currency code (e.g., "USD", "EUR").
            lookup_date: Initial date to try.

        Returns:
            Exchange rate to PLN.

        Raises:
            ValueError: If no rate found within MAX_RETRIES days.
        """
        current_date = lookup_date

        for attempt in range(MAX_RETRIES):
            if current_date.year < 2002:
                msg = f"No NBP rates available for {currency} before 2002"
                logger.error(msg)
                raise ValueError(msg)

            # Build NBP API URL
            endpoint = (
                f"{self.config.nbp_base_url}/{self.config.nbp_table}/"
                f"{currency}/{current_date.isoformat()}/?format=json"
            )

            try:
                logger.debug("Fetching rate from NBP: %s", endpoint)
                response = requests.get(
                    endpoint,
                    headers={"Accept": "application/json"},
                    timeout=10,
                )

                if response.status_code == 200:
                    data = response.json()
                    rate = float(data["rates"][0]["mid"])
                    logger.info(
                        "Successfully fetched %s rate for %s: %.4f PLN",
                        currency,
                        current_date,
                        rate,
                    )
                    return rate

                if response.status_code == 404:
                    logger.debug(
                        "Rate not found for %s on %s, trying previous day",
                        currency,
                        current_date,
                    )
                    current_date -= timedelta(days=1)
                    continue

                # Retry on other errors
                logger.warning(
                    "NBP API error: status %d for %s on %s",
                    response.status_code,
                    currency,
                    current_date,
                )
                response.raise_for_status()

            except requests.RequestException as e:
                logger.warning("Network error fetching NBP rate: %s", e)
                current_date -= timedelta(days=1)
                continue

        msg = (
            f"Unable to find NBP rate for {currency} within {MAX_RETRIES} days "
            f"before {lookup_date}. Please check the transaction date or configure a manual rate."
        )
        logger.error(msg)
        raise ValueError(msg)

    def clear_cache(self) -> None:
        """Clear in-memory and on-disk cache."""
        self.memory.clear()
        if self.cache_path.exists():
            self.cache_path.unlink()
            logger.info("Cache cleared: %s", self.cache_path)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {"cached_rates": len(self.memory)}
