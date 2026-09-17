from typing import Any

import httpx

from .models import Observation, timestamp_from_ms, utc_now


class PublicMarketCollector:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def _get(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("retCode", 0) != 0:
            raise RuntimeError(
                f"Provider error: {payload.get('retCode')} {payload.get('retMsg')}"
            )
        return payload

    async def collect_binance(self) -> list[Observation]:
        now = utc_now()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            spot = await self._get(
                client,
                "https://api.binance.com/api/v3/ticker/price",
                {"symbol": "BTCUSDT"},
            )
            futures = await self._get(
                client,
                "https://fapi.binance.com/fapi/v1/premiumIndex",
                {"symbol": "BTCUSDT"},
            )
            oi = await self._get(
                client,
                "https://fapi.binance.com/fapi/v1/openInterest",
                {"symbol": "BTCUSDT"},
            )
            funding = await self._get(
                client,
                "https://fapi.binance.com/fapi/v1/fundingRate",
                {"symbol": "BTCUSDT", "limit": 1},
            )
        funding_row = funding[0]
        source_ts = timestamp_from_ms(funding_row["fundingTime"])
        common = {"source": "binance_public_rest", "symbol": "BTCUSDT"}
        return [
            Observation(
                now,
                common["source"],
                "binance",
                "spot",
                common["symbol"],
                "price",
                float(spot["price"]),
            ),
            Observation(
                now,
                common["source"],
                "binance",
                "perpetual",
                common["symbol"],
                "mark_price",
                float(futures["markPrice"]),
            ),
            Observation(
                now,
                common["source"],
                "binance",
                "perpetual",
                common["symbol"],
                "open_interest",
                float(oi["openInterest"]),
            ),
            Observation(
                now,
                common["source"],
                "binance",
                "perpetual",
                common["symbol"],
                "funding_rate",
                float(funding_row["fundingRate"]),
                source_timestamp_utc=source_ts,
            ),
        ]

    async def collect_binance_ohlcv(
        self, interval: str = "5m", limit: int = 500
    ) -> list[Observation]:
        now = utc_now()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            candles = await self._get(
                client,
                "https://api.binance.com/api/v3/klines",
                {"symbol": "BTCUSDT", "interval": interval, "limit": min(limit, 1000)},
            )
        observations = []
        for candle in candles:
            source_ts = timestamp_from_ms(candle[0])
            metadata = {
                "interval": interval,
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
                "close_time": candle[6],
            }
            observations.append(
                Observation(
                    now,
                    "binance_public_rest",
                    "binance",
                    "spot",
                    "BTCUSDT",
                    "ohlcv_close",
                    float(candle[4]),
                    metadata=metadata,
                    source_timestamp_utc=source_ts,
                )
            )
        return observations

    async def collect_bybit(self) -> list[Observation]:
        now = utc_now()
        base = "https://api.bybit.com/v5/market"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            ticker = await self._get(
                client, f"{base}/tickers", {"category": "linear", "symbol": "BTCUSDT"}
            )
            oi = await self._get(
                client,
                f"{base}/open-interest",
                {
                    "category": "linear",
                    "symbol": "BTCUSDT",
                    "intervalTime": "5min",
                    "limit": 1,
                },
            )
        row = ticker["result"]["list"][0]
        oi_row = oi["result"]["list"][0]
        source_ts = timestamp_from_ms(oi_row["timestamp"])
        source = "bybit_public_rest"
        return [
            Observation(
                now,
                source,
                "bybit",
                "perpetual",
                "BTCUSDT",
                "price",
                float(row["lastPrice"]),
            ),
            Observation(
                now,
                source,
                "bybit",
                "perpetual",
                "BTCUSDT",
                "open_interest",
                float(oi_row["openInterest"]),
                source_timestamp_utc=source_ts,
            ),
            Observation(
                now,
                source,
                "bybit",
                "perpetual",
                "BTCUSDT",
                "funding_rate",
                float(row["fundingRate"]),
                metadata={"next_funding_time": row.get("nextFundingTime")},
            ),
        ]

    async def collect_okx(self) -> list[Observation]:
        now = utc_now()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            ticker = await self._get(
                client,
                "https://www.okx.com/api/v5/market/ticker",
                {"instId": "BTC-USDT"},
            )
            swap = await self._get(
                client,
                "https://www.okx.com/api/v5/market/ticker",
                {"instId": "BTC-USDT-SWAP"},
            )
            funding = await self._get(
                client,
                "https://www.okx.com/api/v5/public/funding-rate",
                {"instId": "BTC-USDT-SWAP"},
            )
        spot_row = ticker["data"][0]
        swap_row = swap["data"][0]
        funding_row = funding["data"][0]
        return [
            Observation(
                now,
                "okx_public_rest",
                "okx",
                "spot",
                "BTC-USDT",
                "price",
                float(spot_row["last"]),
                source_timestamp_utc=timestamp_from_ms(spot_row["ts"]),
            ),
            Observation(
                now,
                "okx_public_rest",
                "okx",
                "perpetual",
                "BTC-USDT-SWAP",
                "price",
                float(swap_row["last"]),
                source_timestamp_utc=timestamp_from_ms(swap_row["ts"]),
            ),
            Observation(
                now,
                "okx_public_rest",
                "okx",
                "perpetual",
                "BTC-USDT-SWAP",
                "funding_rate",
                float(funding_row["fundingRate"]),
                source_timestamp_utc=timestamp_from_ms(funding_row["fundingTime"]),
            ),
        ]
