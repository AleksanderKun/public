"""
NBP (National Bank of Poland) exchange rate provider.

Implements caching, T-1 date rule, and fallback logic per Polish crypto tax requirements.
Uses the official NBP API (https://api.nbp.pl/).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)


class NBPRateProvider:
    """
    Provides exchange rates from NBP with caching and T-1 rule.

    Polish tax law requires using the exchange rate from the day BEFORE (T-1)
    the transaction date. If that date has no rate (weekend/holiday), we search
    backwards until we find a valid rate.

    Attributes:
        cache_path: Path to JSON cache file
        base_url: NBP API base URL
        table: NBP table code (typically 'A' for major currencies)
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        base_url: str = "https://api.nbp.pl/api/exchangerates/rates",
        table: str = "A",
        timeout: int = 5,
    ):
        """
        Initialize NBP rate provider.

        Args:
            cache_path: Path to cache file. If None, in-memory caching only.
            base_url: NBP API base URL
            table: NBP table ('A' for daily rates)
            timeout: Request timeout in seconds
        """
        self.cache_path = cache_path
        self.base_url = base_url
        self.table = table
        self.timeout = timeout
        self.cache: dict[str, Decimal] = {"PLN": Decimal("1.0")}
        self._load_cache()

        # Hardcoded mappings for stablecoins
        self.stablecoin_map = {
            "USDT": "USD",
            "USDC": "USD",
            "BUSD": "USD",
            "TUSD": "USD",
            "DAI": "USD",
            "EURT": "EUR",
            "EUROC": "EUR",
        }

    def _load_cache(self) -> None:
        """Load cache from file if it exists."""
        if self.cache_path and self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    # Convert string values to Decimal
                    self.cache.update({k: Decimal(str(v)) for k, v in cached.items()})
                logger.debug(
                    f"Loaded cache from {self.cache_path} ({len(self.cache)} entries)"
                )
            except Exception as e:
                logger.warning(f"Failed to load cache from {self.cache_path}: {e}")

    def _save_cache(self) -> None:
        """Save cache to file."""
        if not self.cache_path:
            return

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_serializable = {k: str(v) for k, v in self.cache.items()}
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_serializable, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved cache to {self.cache_path}")
        except Exception as e:
            logger.error(f"Failed to save cache to {self.cache_path}: {e}")

    def _normalize_currency(self, currency: str) -> str:
        """
        Normalize currency code.

        Stablecoins are mapped to their underlying fiat currency.
        PLN is always normalized to PLN.

        Args:
            currency: Original currency code

        Returns:
            Normalized currency code
        """
        if currency == "PLN":
            return "PLN"

        normalized = self.stablecoin_map.get(currency, currency).upper()
        return normalized

    def _fetch_rate_for_date(
        self,
        currency: str,
        date: datetime,
    ) -> Optional[Decimal]:
        """
        Fetch exchange rate from NBP for a specific date.

        Args:
            currency: Currency code (already normalized)
            date: Target date

        Returns:
            Exchange rate or None if not available
        """
        date_str = date.strftime("%Y-%m-%d")
        url = f"{self.base_url}/{self.table}/{currency}/{date_str}/"

        try:
            response = requests.get(
                url, timeout=self.timeout, params={"format": "json"}
            )

            if response.status_code == 200:
                data = response.json()
                rate = Decimal(str(data["rates"][0]["mid"]))
                logger.debug(f"Fetched rate for {currency} on {date_str}: {rate}")
                return rate
            elif response.status_code == 404:
                logger.debug(f"No rate available for {currency} on {date_str}")
                return None
            else:
                logger.warning(
                    f"NBP API returned status {response.status_code} "
                    f"for {currency} on {date_str}"
                )
                return None

        except requests.Timeout:
            logger.warning(f"Timeout fetching rate for {currency} on {date_str}")
            return None
        except requests.RequestException as e:
            logger.warning(f"Request failed for {currency} on {date_str}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.warning(
                f"Failed to parse rate data for {currency} on {date_str}: {e}"
            )
            return None

    def get_rate(
        self,
        currency: str,
        transaction_date: datetime,
        max_lookback_days: int = 10,
    ) -> tuple[Decimal, Optional[datetime]]:
        """
        Get exchange rate for currency on T-1 (day before transaction).

        Per Polish tax law, use rate from the day BEFORE the transaction date.
        If no rate on T-1, search backwards up to max_lookback_days.

        This method implements the following fallback logic:
        1. Check cache first
        2. Try T-1 (transaction_date - 1 day)
        3. Search backwards up to max_lookback_days
        4. Return 1.0 as last resort (with warning)

        Args:
            currency: Currency code (e.g., 'USD', 'EUR', 'BTC')
            transaction_date: Date of transaction
            max_lookback_days: Maximum days to search backwards

        Returns:
            Tuple of (exchange_rate, rate_date)
            - rate_date is the actual date for which rate was found, or None
        """
        normalized = self._normalize_currency(currency)

        if normalized == "PLN":
            return Decimal("1.0"), transaction_date

        # Construct cache key with transaction date (not T-1, for consistency)
        cache_key = f"{normalized}_{transaction_date.strftime('%Y-%m-%d')}"

        if cache_key in self.cache:
            logger.debug(f"Found {normalized} in cache for {transaction_date.date()}")
            return self.cache[cache_key], transaction_date

        # Try T-1 and fallback
        t_minus_1 = transaction_date - timedelta(days=1)

        for days_back in range(max_lookback_days):
            search_date = t_minus_1 - timedelta(days=days_back)
            rate = self._fetch_rate_for_date(normalized, search_date)

            if rate:
                # Cache with original transaction date as key
                self.cache[cache_key] = rate
                self._save_cache()

                logger.info(
                    f"Rate for {normalized}: {rate} "
                    f"(from {search_date.date()}, T-{1+days_back})"
                )
                return rate, search_date

        # Fallback: log warning and return 1.0
        logger.error(
            f"No exchange rate found for {normalized} "
            f"within {max_lookback_days} days before {transaction_date.date()}. "
            f"Using fallback rate of 1.0 (THIS IS AN ERROR CONDITION)"
        )
        return Decimal("1.0"), None

    def get_rate_simple(self, currency: str, transaction_date: datetime) -> Decimal:
        """
        Convenience method: get rate without the tuple return.

        Returns only the exchange rate, not the actual date used.
        """
        rate, _ = self.get_rate(currency, transaction_date)
        return rate

    def clear_cache(self) -> None:
        """Clear in-memory cache."""
        self.cache = {"PLN": Decimal("1.0")}
        logger.info("Cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "entries": len(self.cache),
            "path": str(self.cache_path) if self.cache_path else "in-memory only",
        }
