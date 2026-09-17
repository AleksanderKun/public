from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Observation:
    timestamp_utc: datetime
    source: str
    exchange: str
    market_type: str
    symbol: str
    metric: str
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)
    source_timestamp_utc: datetime | None = None

    @property
    def event_id(self) -> str:
        payload = {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "source": self.source,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "metric": self.metric,
            "value": self.value,
            "metadata": self.metadata,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class NormalizedTrade:
    timestamp_utc: datetime
    exchange: str
    market_type: str
    symbol: str
    trade_id: str
    price: float
    quantity: float
    quote_volume: float
    aggressor_side: str
    source: str
    source_timestamp_utc: datetime | None = None
    ingestion_timestamp_utc: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        payload = {
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "price": self.price,
            "quantity": self.quantity,
            "aggressor_side": self.aggressor_side,
            "source": self.source,
            "source_timestamp_utc": self.source_timestamp_utc.isoformat()
            if self.source_timestamp_utc
            else None,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _normalize_aggressor_side(exchange: str, metadata: dict[str, Any]) -> str:
    raw_side = (
        str(
            metadata.get("side")
            or metadata.get("raw_side")
            or metadata.get("trade_side")
            or ""
        )
        .strip()
        .lower()
    )
    if exchange == "binance":
        if metadata.get("is_buyer_maker") is True:
            return "sell"
        if metadata.get("is_buyer_maker") is False:
            return "buy"
        if raw_side in {"buy", "sell"}:
            return raw_side
        return "unknown"
    if raw_side in {"buy", "sell"}:
        return raw_side
    return "unknown"


def normalize_trade(
    *,
    exchange: str,
    market_type: str,
    symbol: str,
    trade_id: str,
    price: float | str,
    quantity: float | str,
    source: str,
    source_timestamp_utc: datetime | None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedTrade:
    metadata = dict(metadata or {})
    normalized_price = float(price)
    normalized_quantity = float(quantity)
    normalized_timestamp = source_timestamp_utc or utc_now()
    aggressor_side = _normalize_aggressor_side(exchange, metadata)
    metadata.setdefault(
        "aggressor_side_methodology",
        "Exchange-provided trade leg was mapped directly when unambiguous; otherwise side remains unknown to avoid fabrication.",
    )
    if aggressor_side == "unknown":
        metadata[
            "aggressor_side_methodology"
        ] = "No unambiguous aggressor side was provided by the exchange; side was left as unknown to avoid fabrication."
    return NormalizedTrade(
        timestamp_utc=normalized_timestamp,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        trade_id=str(trade_id),
        price=normalized_price,
        quantity=normalized_quantity,
        quote_volume=normalized_price * normalized_quantity,
        aggressor_side=aggressor_side,
        source=source,
        source_timestamp_utc=normalized_timestamp,
        ingestion_timestamp_utc=utc_now(),
        metadata=metadata,
    )


def timestamp_from_ms(value: int | str) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
