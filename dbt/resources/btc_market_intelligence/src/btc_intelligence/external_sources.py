import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .models import Observation, timestamp_from_ms, utc_now


class ExternalSourceCollector:
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def collect_deribit_options(self) -> list[Observation]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get("https://www.deribit.com/api/v2/public/get_book_summary_by_currency", params={"currency": "BTC", "kind": "option"})
            response.raise_for_status()
            payload = response.json()
        if payload.get("jsonrpc") != "2.0" or "result" not in payload:
            raise RuntimeError("Deribit returned an invalid public options response")
        now = utc_now()
        observations = []
        for item in payload["result"]:
            instrument = item["instrument_name"]
            metadata = {"instrument_name": instrument, "expiration": item.get("expiration_timestamp"), "strike": item.get("strike"), "option_type": item.get("option_type"), "underlying_price": item.get("underlying_price")}
            source_ts = timestamp_from_ms(item["creation_timestamp"]) if item.get("creation_timestamp") else None
            for metric, field in (("options_open_interest", "open_interest"), ("options_volume", "volume"), ("options_iv", "mark_iv")):
                if item.get(field) is not None:
                    observations.append(Observation(now, "deribit_public_rest", "deribit", "option", instrument, metric, float(item[field]), metadata=metadata, source_timestamp_utc=source_ts))
        return observations

    async def collect_fred_series(self, series_id: str) -> list[Observation]:
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            raise RuntimeError("FRED_API_KEY is required for FRED data and was not configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get("https://api.stlouisfed.org/fred/series/observations", params={"series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "desc", "limit": 100})
            response.raise_for_status()
            payload = response.json()
        now = utc_now()
        observations = []
        for item in payload.get("observations", []):
            if item.get("value") in (None, "."):
                continue
            timestamp = datetime.strptime(item["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            observations.append(Observation(now, "fred_public_api", "fred", "macro", series_id, "macro_value", float(item["value"]), metadata={"observation_date": item["date"], "series_id": series_id}, source_timestamp_utc=timestamp))
        return observations