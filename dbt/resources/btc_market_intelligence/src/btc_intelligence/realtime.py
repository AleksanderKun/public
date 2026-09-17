from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic as time_monotonic
from typing import Any

from .adapters import canonical_symbol, utc_now


@dataclass(frozen=True)
class WebSocketEvent:
    exchange: str
    dataset: str
    symbol: str
    market_type: str
    event_timestamp: datetime
    trade_id: str | None = None
    price: float | None = None
    quantity: float | None = None
    aggressor_side: str = "unknown"
    bids: tuple[tuple[float, float], ...] = ()
    asks: tuple[tuple[float, float], ...] = ()
    sequence_id: int | None = None
    first_sequence_id: int | None = None
    previous_sequence_id: int | None = None
    update_type: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    local_receive_timestamp: datetime | None = None
    normalized_timestamp: datetime | None = None
    queue_enter_timestamp: datetime | None = None
    writer_start_timestamp: datetime | None = None
    db_commit_timestamp: datetime | None = None
    local_receive_monotonic: float | None = None
    queue_enter_monotonic: float | None = None
    writer_start_monotonic: float | None = None
    db_commit_monotonic: float | None = None

    @property
    def raw_payload_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.raw_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def event_id(self) -> str:
        identity = {
            "exchange": self.exchange,
            "dataset": self.dataset,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "trade_id": self.trade_id,
            "event_timestamp": self.event_timestamp.isoformat(),
            "sequence_id": self.sequence_id,
            "raw_payload_hash": self.raw_payload_hash,
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class LocalOrderBook:
    def __init__(self, depth: int = 20, sequence_mode: str = "monotonic"):
        self.depth = depth
        self.sequence_mode = sequence_mode
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.last_sequence: int | None = None
        self.is_valid = False
        self.sequence_gaps = 0
        self.resyncs = 0

    @property
    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def spread_bps(self) -> float | None:
        if self.spread is None or not self.best_bid:
            return None
        return self.spread / self.best_bid * 10000

    def apply_snapshot(self, bids: list[list[str | float]], asks: list[list[str | float]], sequence: int | None = None) -> None:
        self.bids = self._levels(bids)
        self.asks = self._levels(asks)
        self.last_sequence = sequence
        self.is_valid = self._is_sane()
        self._trim()

    def apply_delta(self, bids: list[list[str | float]], asks: list[list[str | float]], sequence: int | None = None, previous_sequence: int | None = None, first_sequence: int | None = None) -> bool:
        if not self.is_valid:
            return False
        if not self._sequence_is_valid(sequence, previous_sequence, first_sequence):
            self.is_valid = False
            self.sequence_gaps += 1
            return False
        self._apply_levels(self.bids, bids)
        self._apply_levels(self.asks, asks)
        self.last_sequence = sequence if sequence is not None else self.last_sequence
        self._trim()
        self.is_valid = self._is_sane()
        return self.is_valid

    def resync(self, bids: list[list[str | float]], asks: list[list[str | float]], sequence: int | None = None) -> None:
        self.resyncs += 1
        self.apply_snapshot(bids, asks, sequence)

    def _sequence_is_valid(self, sequence: int | None, previous_sequence: int | None, first_sequence: int | None) -> bool:
        if sequence is None or self.last_sequence is None:
            return True
        if previous_sequence is not None:
            return previous_sequence == self.last_sequence and sequence > previous_sequence
        if self.sequence_mode == "binance":
            if sequence <= self.last_sequence:
                return True
            return first_sequence is not None and first_sequence <= self.last_sequence + 1 <= sequence
        if self.sequence_mode == "contiguous":
            return sequence == self.last_sequence + 1
        return sequence > self.last_sequence

    def _is_sane(self) -> bool:
        return bool(self.bids and self.asks and self.best_bid and self.best_ask and self.best_bid < self.best_ask and all(value >= 0 for value in self.bids.values()) and all(value >= 0 for value in self.asks.values()))

    def _levels(self, levels: list[list[str | float]]) -> dict[float, float]:
        result: dict[float, float] = {}
        self._apply_levels(result, levels)
        return result

    def _apply_levels(self, target: dict[float, float], levels: list[list[str | float]]) -> None:
        for level in levels:
            if len(level) < 2:
                continue
            price = float(level[0])
            quantity = float(level[1])
            if price <= 0 or quantity < 0:
                self.is_valid = False
                continue
            if quantity == 0:
                target.pop(price, None)
            else:
                target[price] = quantity

    def _trim(self) -> None:
        self.bids = dict(sorted(self.bids.items(), reverse=True)[: self.depth])
        self.asks = dict(sorted(self.asks.items())[: self.depth])


class BinanceOrderBookSynchronizer:
    def __init__(self, depth: int = 20, max_buffer_events: int = 1000, max_buffer_age_seconds: float = 30.0):
        self.book = LocalOrderBook(depth=depth, sequence_mode="binance")
        self.max_buffer_events = max_buffer_events
        self.max_buffer_age_seconds = max_buffer_age_seconds
        self.buffer: list[tuple[float, dict[str, Any]]] = []
        self.state = "DISCONNECTED"
        self.gap_diagnostics: list[dict[str, Any]] = []
        self.classifications: dict[str, int] = {"stale": 0, "duplicate": 0, "overlap": 0, "continuation": 0, "gap": 0}
        self.state_transitions: list[dict[str, Any]] = []
        self.snapshot_last_update_id: int | None = None
        self.last_buffer_diagnostics: dict[str, Any] = {}

    def _set_state(self, state: str, reason: str) -> None:
        old_state = self.state
        self.state = state
        self.state_transitions.append({"timestamp": utc_now().isoformat(), "old_state": old_state, "new_state": state, "reason": reason})

    def buffer_update(self, update: dict[str, Any]) -> bool:
        if len(self.buffer) >= self.max_buffer_events:
            self._set_state("DESYNCHRONIZED", "buffer overflow")
            return False
        self._set_state("BUFFERING", "depth update received")
        self.buffer.append((time_monotonic(), update))
        self._discard_old_buffer()
        return len(self.buffer) <= self.max_buffer_events

    def synchronize(self, bids: list[list[str | float]], asks: list[list[str | float]], last_update_id: int) -> bool:
        self.snapshot_last_update_id = last_update_id
        self.last_buffer_diagnostics = {
            "buffered_count": len(self.buffer),
            "min_U": min((int(update.get("U", -1)) for _, update in self.buffer), default=None),
            "max_u": max((int(update.get("u", -1)) for _, update in self.buffer), default=None),
            "lastUpdateId": last_update_id,
        }
        self._set_state("SNAPSHOT_LOADING", "REST snapshot received")
        self.book.apply_snapshot(bids, asks, last_update_id)
        self._set_state("SYNCHRONIZING", "searching for bridge update")
        buffered = [update for _, update in self.buffer if int(update.get("u", -1)) > last_update_id]
        buffered.sort(key=lambda update: int(update.get("U", update.get("u", -1))))
        bridge_index = next((index for index, update in enumerate(buffered) if int(update.get("U", -1)) <= last_update_id + 1 <= int(update.get("u", -1))), None)
        if bridge_index is None:
            self._set_state("DESYNCHRONIZED", "no bridge update in bounded buffer")
            return False
        bridge = buffered[bridge_index]
        if not self.book.apply_delta(bridge.get("b", []), bridge.get("a", []), int(bridge["u"]), first_sequence=int(bridge["U"])):
            self._set_state("DESYNCHRONIZED", "invalid bridge book")
            return False
        for update in buffered[bridge_index + 1:]:
            if not self.apply_update(update):
                self._set_state("DESYNCHRONIZED", "sequence gap while applying buffer")
                return False
        self.buffer.clear()
        self._set_state("SYNCHRONIZED", "bridge and buffered continuation applied")
        return True

    def apply_update(self, update: dict[str, Any]) -> bool:
        first = int(update.get("U", -1))
        final = int(update.get("u", -1))
        previous = self.book.last_sequence
        if previous is None:
            self.classifications["gap"] += 1
            self._set_state("DESYNCHRONIZED", "update received before snapshot")
            return False
        if final <= previous:
            self.classifications["duplicate" if final == previous else "stale"] += 1
            return True
        previous_update = update.get("pu")
        if previous_update is not None:
            if int(previous_update) == previous:
                self.classifications["continuation"] += 1
                return self.book.apply_delta(update.get("b", []), update.get("a", []), final, previous_sequence=previous, first_sequence=first)
            self.classifications["gap"] += 1
            self._set_state("GAP", "Binance pu does not match previous u")
            self.gap_diagnostics.append({"exchange": "binance", "symbol": update.get("s"), "previous_u": previous, "current_U": first, "current_u": final, "expected": previous, "received_pu": int(previous_update), "event_timestamp": update.get("E"), "ingestion_timestamp": utc_now().isoformat()})
            return False
        if first <= previous + 1 <= final:
            if first <= previous:
                self.classifications["overlap"] += 1
            else:
                self.classifications["continuation"] += 1
            return self.book.apply_delta(update.get("b", []), update.get("a", []), final, previous_sequence=previous, first_sequence=first)
        self.classifications["gap"] += 1
        self._set_state("DESYNCHRONIZED", "genuine sequence gap")
        self.gap_diagnostics.append({"exchange": "binance", "symbol": update.get("s"), "previous_u": previous, "current_U": first, "current_u": final, "expected": previous + 1, "event_timestamp": update.get("E"), "ingestion_timestamp": utc_now().isoformat()})
        return False

    def _discard_old_buffer(self) -> None:
        cutoff = time_monotonic() - self.max_buffer_age_seconds
        self.buffer = [(received, update) for received, update in self.buffer if received >= cutoff]


class WebSocketMarketDataAdapter:
    exchange = "generic"
    uri = ""

    def __init__(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", depth: int = 20):
        self.symbol = symbol
        self.market_type = market_type
        self.depth = depth

    def subscribe_message(self) -> dict[str, Any]:
        raise NotImplementedError

    def parse_message(self, payload: dict[str, Any]) -> list[WebSocketEvent]:
        raise NotImplementedError


class BinanceWebSocketAdapter(WebSocketMarketDataAdapter):
    exchange = "binance"

    def __init__(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", depth: int = 20, channel: str = "both"):
        super().__init__(symbol, market_type, depth)
        self.channel = channel

    @property
    def uri(self) -> str:
        base = "wss://fstream.binance.com/ws" if self.market_type == "perpetual" else "wss://stream.binance.com:9443/ws"
        stream = f"{self.symbol.lower()}@trade" if self.channel == "trades" else f"{self.symbol.lower()}@depth@100ms" if self.market_type == "perpetual" else f"{self.symbol.lower()}@depth20@100ms"
        return f"{base}/{stream}"

    def subscribe_message(self) -> dict[str, Any]:
        return {}

    def parse_message(self, payload: dict[str, Any]) -> list[WebSocketEvent]:
        message = payload.get("data", payload)
        event_type = message.get("e")
        event_ts = _timestamp(message.get("E"))
        symbol = canonical_symbol(message.get("s", self.symbol))
        if event_type in {"aggTrade", "trade"}:
            maker = message.get("m")
            return [WebSocketEvent(self.exchange, "trades", symbol, self.market_type, _timestamp(message.get("T") or message.get("E")), str(message.get("a") or message.get("t")), float(message["p"]), float(message["q"]), "sell" if maker is True else "buy" if maker is False else "unknown", raw_payload=message)]
        if event_type in {"depthUpdate", "bookTicker"}:
            if event_type == "bookTicker":
                bids = ((float(message["b"]), float(message["B"])),)
                asks = ((float(message["a"]), float(message["A"])),)
                sequence = None
            else:
                bids = tuple((float(row[0]), float(row[1])) for row in message.get("b", []))
                asks = tuple((float(row[0]), float(row[1])) for row in message.get("a", []))
                sequence = message.get("u")
            return [WebSocketEvent(self.exchange, "orderbook", symbol, self.market_type, event_ts, bids=bids, asks=asks, sequence_id=sequence, first_sequence_id=message.get("U"), previous_sequence_id=message.get("pu"), update_type="delta", raw_payload=message)]
        if event_type == "forceOrder":
            order = message.get("o", {})
            price = float(order.get("ap") or order.get("p"))
            quantity = float(order.get("z") or order.get("q"))
            return [WebSocketEvent(self.exchange, "liquidations", canonical_symbol(order.get("s", self.symbol)), "perpetual", event_ts, price=price, quantity=quantity, raw_payload=message)]
        return []


class BybitWebSocketAdapter(WebSocketMarketDataAdapter):
    exchange = "bybit"
    uri = "wss://stream.bybit.com/v5/public/linear"

    def subscribe_message(self) -> dict[str, Any]:
        return {"op": "subscribe", "args": [f"publicTrade.{self.symbol}", f"orderbook.50.{self.symbol}", f"allLiquidation.{self.symbol}"]}

    def parse_message(self, payload: dict[str, Any]) -> list[WebSocketEvent]:
        topic = payload.get("topic", "")
        data = payload.get("data", [])
        event_ts = _timestamp(payload.get("ts"))
        if topic.startswith("publicTrade."):
            return [WebSocketEvent(self.exchange, "trades", canonical_symbol(row["s"]), self.market_type, _timestamp(row.get("T")), str(row["i"]), float(row["p"]), float(row["v"]), str(row.get("S", "unknown")).lower(), raw_payload=row) for row in data]
        if topic.startswith("orderbook."):
            return [WebSocketEvent(self.exchange, "orderbook", canonical_symbol(data["s"]), self.market_type, event_ts, bids=tuple((float(row[0]), float(row[1])) for row in data.get("b", [])), asks=tuple((float(row[0]), float(row[1])) for row in data.get("a", [])), sequence_id=data.get("u"), update_type=payload.get("type", "delta"), raw_payload=payload)]
        if topic.startswith("allLiquidation."):
            rows = data if isinstance(data, list) else [data]
            return [WebSocketEvent(self.exchange, "liquidations", canonical_symbol(row.get("symbol", self.symbol)), "perpetual", _timestamp(row.get("T") or payload.get("ts")), price=float(row["price"]) if row.get("price") else None, quantity=float(row["qty"]) if row.get("qty") else None, raw_payload=row) for row in rows if row.get("qty")]
        return []


class OKXWebSocketAdapter(WebSocketMarketDataAdapter):
    exchange = "okx"
    uri = "wss://ws.okx.com:8443/ws/v5/public"

    def subscribe_message(self) -> dict[str, Any]:
        inst = self._inst_id()
        return {"op": "subscribe", "args": [{"channel": "trades", "instId": inst}, {"channel": "books5", "instId": inst}]}

    def parse_message(self, payload: dict[str, Any]) -> list[WebSocketEvent]:
        arg = payload.get("arg", {})
        channel = arg.get("channel")
        rows = payload.get("data", [])
        if channel == "trades":
            return [WebSocketEvent(self.exchange, "trades", canonical_symbol(row["instId"]), self.market_type, _timestamp(row.get("ts")), str(row["tradeId"]), float(row["px"]), float(row["sz"]), str(row.get("side", "unknown")).lower(), raw_payload=row) for row in rows]
        if channel in {"books", "books5", "bbo-tbt"}:
            return [WebSocketEvent(self.exchange, "orderbook", canonical_symbol(row["instId"]), self.market_type, _timestamp(row.get("ts")), bids=tuple((float(level[0]), float(level[1])) for level in row.get("bids", [])), asks=tuple((float(level[0]), float(level[1])) for level in row.get("asks", [])), sequence_id=int(row["seqId"]) if row.get("seqId") is not None else None, previous_sequence_id=int(row["prevSeqId"]) if row.get("prevSeqId") is not None else None, update_type="snapshot" if channel == "books5" else "delta", raw_payload=row) for row in rows]
        return []

    def _inst_id(self) -> str:
        normalized = canonical_symbol(self.symbol)
        return f"{normalized[:-4]}-{normalized[-4:]}-SWAP" if self.market_type == "perpetual" else f"{normalized[:-4]}-{normalized[-4:]}"


def _timestamp(value: Any) -> datetime:
    if value is None:
        return utc_now()
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
