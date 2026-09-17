from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .adapters import ExchangeMarketDataAdapter, utc_now


DATASETS = ("trades", "open_interest", "funding", "orderbook", "liquidations")


@dataclass
class IngestionResult:
    exchange: str
    dataset: str
    started_at: str
    finished_at: str = ""
    duration_ms: int = 0
    records_received: int = 0
    records_valid: int = 0
    records_invalid: int = 0
    records_duplicate: int = 0
    records_written: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "DOWN"
    min_timestamp: str | None = None
    max_timestamp: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class RawMarketIngestionService:
    def __init__(
        self,
        store: Any,
        adapters: dict[str, ExchangeMarketDataAdapter],
        stale_after_seconds: int = 300,
    ):
        self.store = store
        self.adapters = adapters
        self.stale_after_seconds = stale_after_seconds

    async def ingest(
        self,
        exchange: str,
        dataset: str,
        symbol: str = "BTCUSDT",
        market_type: str | None = None,
        limit: int = 20,
        depth: int = 20,
    ) -> IngestionResult:
        if dataset not in DATASETS:
            raise ValueError(f"Unsupported dataset: {dataset}")
        adapter = self.adapters[exchange]
        market_type = market_type or (
            "spot" if dataset == "trades" and exchange == "binance" else "perpetual"
        )
        started = utc_now()
        result = IngestionResult(exchange, dataset, started.isoformat())
        try:
            getter = getattr(adapter, f"get_{dataset}")
            if dataset == "trades":
                events = await getter(symbol, market_type, limit)
            elif dataset == "orderbook":
                events = await getter(symbol, market_type, depth)
            else:
                events = await getter(symbol, market_type)
        except Exception as exc:
            result.errors.append(f"{type(exc).__name__}: {exc}")
            return self._finish(result, "DOWN")

        if len(events) == 1 and events[0].get("status") == "NOT_AVAILABLE":
            result.errors.append(events[0].get("reason", "dataset unavailable"))
            return self._finish(result, "NOT_AVAILABLE")

        seen: set[str] = set()
        for event in events:
            result.records_received += 1
            event_id = self._event_id(exchange, dataset, event)
            event["event_id"] = event_id
            if event_id in seen:
                result.records_duplicate += 1
                continue
            seen.add(event_id)
            validation = adapter.validate_event(event)
            if dataset == "orderbook":
                bid = event.get("best_bid")
                ask = event.get("best_ask")
                if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
                    validation["status"] = "INVALID"
                    validation["reasons"].append("crossed or incomplete order book")
                event["spread"] = (
                    ask - bid if bid is not None and ask is not None else None
                )
                event["spread_bps"] = (
                    event["spread"] / bid * 10000
                    if bid and event["spread"] is not None
                    else None
                )
            if validation["status"] == "INVALID":
                result.records_invalid += 1
                self.store.reject_raw_event(dataset, event, validation)
                continue
            result.records_valid += 1
            if self.store.write_raw_event(dataset, event, validation["status"]):
                result.records_written += 1
            else:
                result.records_duplicate += 1
            timestamp = event.get("event_timestamp") or event.get("timestamp")
            if timestamp:
                result.min_timestamp = (
                    min(result.min_timestamp, timestamp)
                    if result.min_timestamp
                    else timestamp
                )
                result.max_timestamp = (
                    max(result.max_timestamp, timestamp)
                    if result.max_timestamp
                    else timestamp
                )
        status = (
            "HEALTHY"
            if result.records_written or result.records_duplicate
            else "DEGRADED"
        )
        if result.records_invalid and not result.records_written:
            status = "DEGRADED"
        return self._finish(result, status)

    async def ingest_exchange(
        self, exchange: str, symbol: str = "BTCUSDT"
    ) -> list[IngestionResult]:
        results: list[IngestionResult] = []
        trade_markets = ("spot", "perpetual")
        for market_type in trade_markets:
            results.append(await self.ingest(exchange, "trades", symbol, market_type))
        for dataset in ("open_interest", "funding", "orderbook", "liquidations"):
            results.append(await self.ingest(exchange, dataset, symbol, "perpetual"))
        return results

    def _event_id(self, exchange: str, dataset: str, event: dict[str, Any]) -> str:
        natural_key = {
            "exchange": exchange,
            "dataset": dataset,
            "symbol": event.get("symbol"),
            "market_type": event.get("market_type"),
            "trade_id": event.get("trade_id"),
            "timestamp": event.get("event_timestamp") or event.get("timestamp"),
            "raw_payload_hash": event.get("raw_payload_hash"),
            "side": event.get("side"),
            "price": event.get("price"),
            "quantity": event.get("quantity"),
        }
        return hashlib.sha256(
            json.dumps(natural_key, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _finish(self, result: IngestionResult, status: str) -> IngestionResult:
        finished = utc_now()
        result.finished_at = finished.isoformat()
        result.duration_ms = round(
            (finished - datetime.fromisoformat(result.started_at)).total_seconds()
            * 1000
        )
        result.status = status
        return result


def database_counts(store: Any) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for table, dataset in (
        ("raw_trades", "trades"),
        ("raw_open_interest", "open_interest"),
        ("raw_funding", "funding"),
        ("raw_orderbook", "orderbook"),
        ("raw_liquidations", "liquidations"),
    ):
        rows.extend(
            store.connection.execute(
                f"SELECT exchange, COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc) FROM {table} GROUP BY exchange ORDER BY exchange"
            ).fetchall()
        )
    return rows
