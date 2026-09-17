import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Awaitable, Callable

from .models import Observation, timestamp_from_ms, utc_now

logger = logging.getLogger(__name__)
ObservationSink = Callable[[list[Observation]], Awaitable[None]]


def _observation(exchange: str, market_type: str, symbol: str, metric: str, value: float, source_ts: int | str, metadata: dict[str, Any]) -> Observation:
    return Observation(
        timestamp_utc=utc_now(),
        source=f"{exchange}_public_websocket",
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        metric=metric,
        value=value,
        source_timestamp_utc=timestamp_from_ms(source_ts),
        metadata=metadata,
    )


def parse_binance_message(payload: dict[str, Any]) -> list[Observation]:
    if "data" in payload and isinstance(payload["data"], dict):
        payload = payload["data"]
    event_type = payload.get("e")
    event_time = payload.get("E")
    if event_type == "aggTrade":
        symbol = payload["s"]
        return [
            _observation("binance", "spot", symbol, "trade_price", float(payload["p"]), event_time, {"trade_id": payload["a"], "is_buyer_maker": payload["m"]}),
            _observation("binance", "spot", symbol, "trade_volume", float(payload["q"]), event_time, {"trade_id": payload["a"], "is_buyer_maker": payload["m"]}),
        ]
    if event_type == "forceOrder":
        order = payload["o"]
        symbol = order["s"]
        return [
            _observation("binance", "perpetual", symbol, "liquidation_price", float(order["ap"]), event_time, {"side": order["S"], "quantity": order["q"], "order_status": order["X"]}),
            _observation("binance", "perpetual", symbol, "liquidation_size", float(order["z"]), event_time, {"side": order["S"], "price": order["ap"], "order_status": order["X"]}),
        ]
    if event_type == "bookTicker":
        symbol = payload["s"]
        return [
            _observation("binance", "spot", symbol, "best_bid_price", float(payload["b"]), event_time, {"bid_quantity": payload["B"]}),
            _observation("binance", "spot", symbol, "best_ask_price", float(payload["a"]), event_time, {"ask_quantity": payload["A"]}),
        ]
    return []


def parse_bybit_message(payload: dict[str, Any]) -> list[Observation]:
    topic = payload.get("topic", "")
    event_time = payload.get("ts")
    data = payload.get("data", [])
    if topic.startswith("publicTrade."):
        observations = []
        for trade in data:
            observations.extend([
                _observation("bybit", "perpetual", trade["s"], "trade_price", float(trade["p"]), trade["T"], {"trade_id": trade["i"], "side": trade["S"]}),
                _observation("bybit", "perpetual", trade["s"], "trade_volume", float(trade["v"]), trade["T"], {"trade_id": trade["i"], "side": trade["S"]}),
            ])
        return observations
    if topic.startswith("allLiquidation."):
        rows = data if isinstance(data, list) else [data]
        observations = []
        for row in rows:
            symbol = row.get("symbol", row.get("s", topic.rsplit(".", 1)[-1]))
            quantity = row.get("qty", row.get("v"))
            timestamp = row.get("T", event_time)
            if quantity is None or timestamp is None:
                continue
            observations.append(_observation("bybit", "perpetual", symbol, "liquidation_size", float(quantity), timestamp, {"side": row.get("side", row.get("S")), "price": row.get("price", row.get("p"))}))
        return observations
    if topic.startswith("orderbook."):
        symbol = data["s"]
        observations = []
        if data.get("b"):
            observations.append(_observation("bybit", "perpetual", symbol, "best_bid_price", float(data["b"][0][0]), event_time, {"quantity": data["b"][0][1], "update_id": data.get("u")}))
        if data.get("a"):
            observations.append(_observation("bybit", "perpetual", symbol, "best_ask_price", float(data["a"][0][0]), event_time, {"quantity": data["a"][0][1], "update_id": data.get("u")}))
        return observations
    return []


async def consume_with_reconnect(uri: str, subscribe: dict[str, Any], parser: Callable[[dict[str, Any]], list[Observation]], sink: ObservationSink, reconnect_delay: float = 1.0, max_reconnect_delay: float = 60.0) -> None:
    """Consume a public stream forever; backoff protects providers during outages."""
    import websockets

    delay = reconnect_delay
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as connection:
                await connection.send(json.dumps(subscribe))
                delay = reconnect_delay
                async for raw_message in connection:
                    observations = parser(json.loads(raw_message))
                    if observations:
                        await sink(observations)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("websocket disconnected; retrying in %.1fs", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_reconnect_delay)