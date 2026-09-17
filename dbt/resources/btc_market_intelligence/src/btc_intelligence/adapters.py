from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_symbol(symbol: str) -> str:
    cleaned = str(symbol or "").strip().upper().replace("_", "").replace("-", "")
    if cleaned.endswith(".P"):
        return cleaned[:-2] + "P"
    if cleaned.startswith("BTC") and "USDT" in cleaned:
        return "BTCUSDT"
    if cleaned.endswith("USDT"):
        return cleaned[:-5] + "USDT"
    return cleaned


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            try:
                return datetime.fromtimestamp(float(cleaned) / 1000, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ExchangeMarketDataAdapter:
    exchange: str = "generic"
    source: str = "public_rest"
    timeout: float = 10.0
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5

    def canonicalize_symbol(self, symbol: str, market_type: str | None = None) -> str:
        return canonical_symbol(symbol)

    def validate_event(self, event: dict[str, Any]) -> dict[str, Any]:
        timestamp = event.get("timestamp") or event.get("event_timestamp") or event.get("source_timestamp_utc")
        price = _safe_float(event.get("price"))
        quantity = _safe_float(event.get("quantity"))
        open_interest = _safe_float(event.get("open_interest"))
        funding_rate = _safe_float(event.get("funding_rate"))
        reasons: list[str] = []

        if timestamp is None:
            reasons.append("missing timestamp")
        else:
            parsed = _to_utc(timestamp)
            if parsed is None:
                reasons.append("invalid timestamp")
            elif parsed > utc_now() + timedelta(hours=1):
                reasons.append("timestamp in future")

        if price is not None and price <= 0:
            reasons.append("invalid price")
        if quantity is not None and quantity < 0:
            reasons.append("negative quantity")
        if open_interest is not None and open_interest < 0:
            reasons.append("negative open interest")
        if funding_rate is not None and abs(funding_rate) > 1.0:
            reasons.append("funding rate out of range")

        status = "VALID"
        if reasons:
            status = "INVALID" if any(reason in {"missing timestamp", "invalid timestamp", "invalid price", "negative quantity"} for reason in reasons) else "SUSPECT"
        return {"status": status, "reasons": reasons}

    async def _get_json(self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("retCode") not in (None, 0):
            message = payload.get("retMsg") or payload.get("msg") or response.text
            raise RuntimeError(f"{self.exchange} API error: {message}")
        if isinstance(payload, dict) and payload.get("code") not in (None, "0", 0):
            message = payload.get("msg") or payload.get("message") or response.text
            raise RuntimeError(f"{self.exchange} API error: {message}")
        return payload

    async def _request_with_retry(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    return await self._get_json(client, url, params)
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(self.retry_backoff_seconds * (2**attempt))
        raise RuntimeError(f"{self.exchange} request failed after retries: {last_error}")

    async def get_trades(self, symbol: str = "BTCUSDT", market_type: str = "spot", limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_orderbook(self, symbol: str = "BTCUSDT", market_type: str = "spot", depth: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_open_interest(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_funding(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_liquidations(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        return [{"status": "NOT_AVAILABLE", "reason": f"{self.exchange} does not expose a supported public liquidation endpoint in this adapter."}]

    def normalize_trade(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_open_interest(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_funding(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_liquidation(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_orderbook(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        raise NotImplementedError


class BinanceMarketDataAdapter(ExchangeMarketDataAdapter):
    exchange = "binance"
    source = "binance_public_rest"

    def normalize_trade(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        price = _safe_float(payload.get("p") or payload.get("price"))
        quantity = _safe_float(payload.get("q") or payload.get("qty"))
        trade_id = payload.get("a") or payload.get("trade_id") or payload.get("id")
        if price is None or quantity is None:
            raise ValueError("Binance trade payload is missing price or quantity")
        aggressive_side = "sell" if payload.get("m", payload.get("isBuyerMaker")) is True else "buy" if payload.get("m", payload.get("isBuyerMaker")) is False else "unknown"
        event_ms = payload.get("T") or payload.get("E") or payload.get("time")
        event = {
            "event_timestamp": datetime.fromtimestamp(int(event_ms or 0) / 1000, tz=timezone.utc).isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "trade_id": str(trade_id),
            "price": price,
            "quantity": quantity,
            "quote_volume": price * quantity,
            "aggressor_side": aggressive_side,
            "source": self.source,
            "source_timestamp_utc": datetime.fromtimestamp(int(event_ms or 0) / 1000, tz=timezone.utc).isoformat(),
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }
        event["raw_payload"] = payload
        return event

    def normalize_open_interest(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("openInterest"))
        if value is None:
            raise ValueError("Binance OI payload missing openInterest")
        return {
            "event_timestamp": datetime.fromtimestamp(int(payload.get("time") or 0) / 1000, tz=timezone.utc).isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "open_interest": value,
            "open_interest_usd": None,
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_funding(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("fundingRate"))
        return {
            "event_timestamp": datetime.fromtimestamp(int(payload.get("fundingTime") or payload.get("time") or 0) / 1000, tz=timezone.utc).isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "funding_rate": value,
            "funding_rate_decimal": value,
            "funding_rate_percent": None if value is None else value * 100,
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_liquidation(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        qty = _safe_float(payload.get("q"))
        price = _safe_float(payload.get("p"))
        side = payload.get("S") or payload.get("side")
        if qty is None or price is None:
            raise ValueError("Binance liquidation payload missing q or p")
        return {
            "event_timestamp": datetime.fromtimestamp(int(payload.get("T") or 0) / 1000, tz=timezone.utc).isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "side": side,
            "price": price,
            "quantity": qty,
            "USD_value": price * qty,
            "liquidation_type": "LONG" if str(side).upper() == "BUY" else "SHORT" if str(side).upper() == "SELL" else "UNKNOWN",
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_orderbook(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        bid = payload.get("bids") or payload.get("best_bid")
        ask = payload.get("asks") or payload.get("best_ask")
        best_bid_price = _safe_float((bid[0][0] if isinstance(bid, list) and bid else None)) if bid else None
        best_ask_price = _safe_float((ask[0][0] if isinstance(ask, list) and ask else None)) if ask else None
        bid_quantity = _safe_float((bid[0][1] if isinstance(bid, list) and bid and len(bid[0]) > 1 else None)) if bid else None
        ask_quantity = _safe_float((ask[0][1] if isinstance(ask, list) and ask and len(ask[0]) > 1 else None)) if ask else None
        return {
            "timestamp": utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "best_bid": best_bid_price,
            "best_ask": best_ask_price,
            "bid_quantity": bid_quantity,
            "ask_quantity": ask_quantity,
            "spread": None if best_bid_price is None or best_ask_price is None else best_ask_price - best_bid_price,
            "raw_payload_hash": _payload_hash(payload),
        }

    async def get_trades(self, symbol: str = "BTCUSDT", market_type: str = "spot", limit: int = 20) -> list[dict[str, Any]]:
        endpoint = "https://fapi.binance.com/fapi/v1/trades" if market_type == "perpetual" else "https://api.binance.com/api/v3/trades"
        payload = await self._request_with_retry(endpoint, {"symbol": self.canonicalize_symbol(symbol), "limit": limit})
        return [self.normalize_trade(item, symbol, market_type) for item in payload[:limit]]

    async def get_orderbook(self, symbol: str = "BTCUSDT", market_type: str = "spot", depth: int = 20) -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://api.binance.com/api/v3/depth", {"symbol": self.canonicalize_symbol(symbol), "limit": min(depth, 100)})
        return [self.normalize_orderbook(payload, symbol, market_type)]

    async def get_open_interest(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": self.canonicalize_symbol(symbol)})
        return [self.normalize_open_interest(payload, symbol, market_type)]

    async def get_funding(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": self.canonicalize_symbol(symbol), "limit": 1})
        rows = payload if isinstance(payload, list) else [payload]
        return [self.normalize_funding(item, symbol, market_type) for item in rows[:1]]

    async def get_liquidations(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        return [{"status": "NOT_AVAILABLE", "reason": "Binance public REST does not provide unauthenticated historical force-order events; use the public forceOrder WebSocket stream."}]


class BybitMarketDataAdapter(ExchangeMarketDataAdapter):
    exchange = "bybit"
    source = "bybit_public_rest"

    def normalize_trade(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        price = _safe_float(payload.get("p") or payload.get("price"))
        quantity = _safe_float(payload.get("v") or payload.get("size"))
        trade_id = payload.get("i") or payload.get("execId") or payload.get("trade_id")
        if price is None or quantity is None:
            raise ValueError("Bybit trade payload missing price or quantity")
        side = str(payload.get("S") or payload.get("side") or "unknown").lower()
        aggressor_side = side if side in {"buy", "sell"} else "unknown"
        ts = payload.get("T") or payload.get("time") or payload.get("timestamp") or payload.get("ts")
        event = {
            "event_timestamp": _to_utc(ts).isoformat() if _to_utc(ts) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "trade_id": str(trade_id),
            "price": price,
            "quantity": quantity,
            "quote_volume": price * quantity,
            "aggressor_side": aggressor_side,
            "source": self.source,
            "source_timestamp_utc": _to_utc(ts).isoformat() if _to_utc(ts) else utc_now().isoformat(),
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }
        event["raw_payload"] = payload
        return event

    def normalize_open_interest(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("openInterest"))
        if value is None:
            raise ValueError("Bybit OI payload missing openInterest")
        timestamp = payload.get("timestamp") or payload.get("ts")
        return {
            "event_timestamp": _to_utc(timestamp).isoformat() if _to_utc(timestamp) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "open_interest": value,
            "open_interest_usd": None,
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_funding(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("fundingRate"))
        return {
            "event_timestamp": _to_utc(payload.get("fundingTime") or payload.get("timestamp") or payload.get("ts")).isoformat() if _to_utc(payload.get("fundingTime") or payload.get("timestamp") or payload.get("ts")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "funding_rate": value,
            "funding_rate_decimal": value,
            "funding_rate_percent": None if value is None else value * 100,
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_liquidation(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        qty = _safe_float(payload.get("qty") or payload.get("quantity"))
        price = _safe_float(payload.get("price") or payload.get("p"))
        side = payload.get("side") or payload.get("S")
        if qty is None or price is None:
            raise ValueError("Bybit liquidation payload missing quantity or price")
        return {
            "event_timestamp": _to_utc(payload.get("T") or payload.get("timestamp") or payload.get("ts")).isoformat() if _to_utc(payload.get("T") or payload.get("timestamp") or payload.get("ts")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "side": side,
            "price": price,
            "quantity": qty,
            "USD_value": price * qty,
            "liquidation_type": "LONG" if str(side).upper() == "BUY" else "SHORT" if str(side).upper() == "SELL" else "UNKNOWN",
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_orderbook(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        bid = payload.get("b") or payload.get("bid") or payload.get("bids")
        ask = payload.get("a") or payload.get("ask") or payload.get("asks")
        best_bid = bid[0] if isinstance(bid, list) and bid else None
        best_ask = ask[0] if isinstance(ask, list) and ask else None
        best_bid_price = _safe_float(best_bid[0] if isinstance(best_bid, list) and best_bid else None)
        best_ask_price = _safe_float(best_ask[0] if isinstance(best_ask, list) and best_ask else None)
        bid_quantity = _safe_float(best_bid[1] if isinstance(best_bid, list) and len(best_bid) > 1 else None)
        ask_quantity = _safe_float(best_ask[1] if isinstance(best_ask, list) and len(best_ask) > 1 else None)
        return {
            "timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "best_bid": best_bid_price,
            "best_ask": best_ask_price,
            "bid_quantity": bid_quantity,
            "ask_quantity": ask_quantity,
            "spread": None if best_bid_price is None or best_ask_price is None else best_ask_price - best_bid_price,
            "raw_payload_hash": _payload_hash(payload),
        }

    async def get_trades(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        category = "linear" if market_type == "perpetual" else "spot"
        payload = await self._request_with_retry("https://api.bybit.com/v5/market/recent-trade", {"category": category, "symbol": self.canonicalize_symbol(symbol), "limit": limit})
        rows = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        return [self.normalize_trade(item, symbol, market_type) for item in rows[:limit]]

    async def get_orderbook(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", depth: int = 20) -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://api.bybit.com/v5/market/orderbook", {"category": "linear", "symbol": self.canonicalize_symbol(symbol), "limit": min(depth, 200)})
        rows = payload.get("result", {}) if isinstance(payload, dict) else {}
        return [self.normalize_orderbook(rows, symbol, market_type)]

    async def get_open_interest(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://api.bybit.com/v5/market/open-interest", {"category": "linear", "symbol": self.canonicalize_symbol(symbol), "intervalTime": "5min", "limit": 1})
        rows = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        return [self.normalize_open_interest(item, symbol, market_type) for item in rows[:1]]

    async def get_funding(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://api.bybit.com/v5/market/funding/history", {"category": "linear", "symbol": self.canonicalize_symbol(symbol), "limit": 1})
        rows = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        return [self.normalize_funding(item, symbol, market_type) for item in rows[:1]]

    async def get_liquidations(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        return [{"status": "NOT_AVAILABLE", "reason": "Bybit public REST does not expose a supported liquidation-history endpoint; use the public allLiquidation WebSocket stream."}]


class OKXMarketDataAdapter(ExchangeMarketDataAdapter):
    exchange = "okx"
    source = "okx_public_rest"

    def normalize_trade(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        price = _safe_float(payload.get("px") or payload.get("price"))
        quantity = _safe_float(payload.get("sz") or payload.get("size") or payload.get("qty"))
        trade_id = payload.get("tradeId") or payload.get("id")
        if price is None or quantity is None:
            raise ValueError("OKX trade payload missing price or quantity")
        side = str(payload.get("side") or payload.get("direction") or "unknown").lower()
        aggressor_side = side if side in {"buy", "sell"} else "unknown"
        return {
            "event_timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "trade_id": str(trade_id),
            "price": price,
            "quantity": quantity,
            "quote_volume": price * quantity,
            "aggressor_side": aggressor_side,
            "source": self.source,
            "source_timestamp_utc": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_open_interest(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("oi"))
        if value is None:
            raise ValueError("OKX OI payload missing oi")
        return {
            "event_timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "open_interest": value,
            "open_interest_usd": None,
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_funding(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        value = _safe_float(payload.get("fundingRate"))
        funding_time = _to_utc(payload.get("fundingTime") or payload.get("ts") or payload.get("timestamp"))
        return {
            "event_timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "funding_rate": value,
            "funding_rate_decimal": value,
            "funding_rate_percent": None if value is None else value * 100,
            "source": self.source,
            "source_timestamp_utc": funding_time.isoformat() if funding_time else None,
            "metadata": {"funding_time": payload.get("fundingTime"), "next_funding_time": payload.get("nextFundingTime")},
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_liquidation(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        qty = _safe_float(payload.get("sz") or payload.get("qty") or payload.get("quantity"))
        price = _safe_float(payload.get("px") or payload.get("price"))
        side = payload.get("side")
        if qty is None or price is None:
            raise ValueError("OKX liquidation payload missing quantity or price")
        return {
            "event_timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "side": side,
            "price": price,
            "quantity": qty,
            "USD_value": price * qty,
            "liquidation_type": "LONG" if str(side).upper() == "BUY" else "SHORT" if str(side).upper() == "SELL" else "UNKNOWN",
            "source": self.source,
            "ingestion_timestamp_utc": utc_now().isoformat(),
            "raw_payload_hash": _payload_hash(payload),
        }

    def normalize_orderbook(self, payload: dict[str, Any], symbol: str, market_type: str) -> dict[str, Any]:
        bids = payload.get("bids") or payload.get("bid")
        asks = payload.get("asks") or payload.get("ask")
        best_bid = bids[0] if isinstance(bids, list) and bids else None
        best_ask = asks[0] if isinstance(asks, list) and asks else None
        best_bid_price = _safe_float(best_bid[0] if isinstance(best_bid, list) and best_bid else None)
        best_ask_price = _safe_float(best_ask[0] if isinstance(best_ask, list) and best_ask else None)
        bid_quantity = _safe_float(best_bid[1] if isinstance(best_bid, list) and len(best_bid) > 1 else None)
        ask_quantity = _safe_float(best_ask[1] if isinstance(best_ask, list) and len(best_ask) > 1 else None)
        return {
            "timestamp": _to_utc(payload.get("ts") or payload.get("timestamp")).isoformat() if _to_utc(payload.get("ts") or payload.get("timestamp")) else utc_now().isoformat(),
            "exchange": self.exchange,
            "symbol": self.canonicalize_symbol(symbol),
            "market_type": market_type,
            "best_bid": best_bid_price,
            "best_ask": best_ask_price,
            "bid_quantity": bid_quantity,
            "ask_quantity": ask_quantity,
            "spread": None if best_bid_price is None or best_ask_price is None else best_ask_price - best_bid_price,
            "raw_payload_hash": _payload_hash(payload),
        }

    async def get_trades(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://www.okx.com/api/v5/market/trades", {"instId": self._inst_id(symbol, market_type), "limit": limit})
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        return [self.normalize_trade(item, symbol, market_type) for item in rows[:limit]]

    async def get_orderbook(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", depth: int = 20) -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://www.okx.com/api/v5/market/books", {"instId": self._inst_id(symbol, market_type), "sz": min(depth, 25)})
        data = payload.get("data", [{}])[0]
        return [self.normalize_orderbook(data, symbol, market_type)]

    async def get_open_interest(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP", "instId": self._inst_id(symbol, market_type)})
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        return [self.normalize_open_interest(item, symbol, market_type) for item in rows[:1]]

    async def get_funding(self, symbol: str = "BTCUSDT", market_type: str = "perpetual") -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://www.okx.com/api/v5/public/funding-rate", {"instId": self._inst_id(symbol, market_type)})
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        return [self.normalize_funding(item, symbol, market_type) for item in rows[:1]]

    async def get_liquidations(self, symbol: str = "BTCUSDT", market_type: str = "perpetual", limit: int = 20) -> list[dict[str, Any]]:
        payload = await self._request_with_retry("https://www.okx.com/api/v5/public/liquidation-orders", {"instType": "SWAP", "instId": self._inst_id(symbol, market_type), "state": "filled", "uly": "BTC-USDT", "limit": limit})
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        if not rows:
            return [{"status": "NOT_AVAILABLE", "reason": "OKX liquidation endpoint returned no public rows."}]
        try:
            return [self.normalize_liquidation(item, symbol, market_type) for item in rows[:limit]]
        except ValueError:
            return [{"status": "NOT_AVAILABLE", "reason": "OKX liquidation response did not expose a normal price and quantity event shape."}]

    def _inst_id(self, symbol: str, market_type: str) -> str:
        normalized = self.canonicalize_symbol(symbol)
        if market_type == "perpetual":
            return f"{normalized[:-4]}-{normalized[-4:]}-SWAP" if normalized.endswith("USDT") else f"{normalized}-SWAP"
        return f"{normalized[:-4]}-{normalized[-4:]}"
