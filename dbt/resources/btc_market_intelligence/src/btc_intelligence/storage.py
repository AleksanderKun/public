from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Any
import duckdb

from .models import NormalizedTrade, Observation


SCHEMA = """
CREATE TABLE IF NOT EXISTS market_observations (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    source VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    metadata JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_observations_metric_time
    ON market_observations (metric, timestamp_utc);

CREATE TABLE IF NOT EXISTS raw_trades (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    source VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    trade_id VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    quantity DOUBLE NOT NULL,
    quote_volume DOUBLE NOT NULL,
    aggressor_side VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE INDEX IF NOT EXISTS idx_raw_trades_exchange_symbol_time
    ON raw_trades (exchange, symbol, timestamp_utc DESC);

CREATE TABLE IF NOT EXISTS raw_orderbook (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    source VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    quantity DOUBLE NOT NULL,
    metadata JSON NOT NULL,
    sequence_id VARCHAR,
    update_type VARCHAR,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE TABLE IF NOT EXISTS raw_orderbook_updates (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    bids JSON NOT NULL,
    asks JSON NOT NULL,
    sequence_id VARCHAR,
    previous_sequence_id VARCHAR,
    update_type VARCHAR NOT NULL,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE TABLE IF NOT EXISTS raw_funding (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    funding_rate DOUBLE NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    source VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    next_funding_time TIMESTAMPTZ,
    mark_price DOUBLE,
    index_price DOUBLE,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE TABLE IF NOT EXISTS raw_open_interest (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    open_interest DOUBLE NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    source VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    open_interest_usd DOUBLE,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE TABLE IF NOT EXISTS raw_liquidations (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    quantity DOUBLE NOT NULL,
    usd_value DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    metadata JSON NOT NULL,
    liquidation_type VARCHAR,
    ingestion_timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload_hash VARCHAR NOT NULL DEFAULT '',
    validation_status VARCHAR NOT NULL DEFAULT 'VALID'
);
CREATE TABLE IF NOT EXISTS rejected_raw_events (
    event_id VARCHAR PRIMARY KEY,
    exchange VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL,
    validation_status VARCHAR NOT NULL,
    reasons JSON NOT NULL,
    event JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_options (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    instrument_name VARCHAR NOT NULL,
    option_type VARCHAR NOT NULL,
    strike DOUBLE NOT NULL,
    expiry TIMESTAMPTZ,
    open_interest DOUBLE,
    volume DOUBLE,
    iv DOUBLE,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_macro (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    source VARCHAR NOT NULL,
    series_id VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    observation_date TIMESTAMPTZ,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_etf_flows (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    fund VARCHAR NOT NULL,
    ticker VARCHAR NOT NULL,
    net_flow DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    metadata JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_metrics AS
    SELECT * FROM market_observations WHERE 1 = 0;
CREATE TABLE IF NOT EXISTS trades AS
    SELECT * FROM market_observations WHERE 1 = 0;
CREATE TABLE IF NOT EXISTS liquidation_events AS
    SELECT * FROM market_observations WHERE 1 = 0;
CREATE TABLE IF NOT EXISTS orderbook_snapshots AS
    SELECT * FROM market_observations WHERE 1 = 0;
CREATE TABLE IF NOT EXISTS derived_cvd (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    exchange VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    buy_volume DOUBLE NOT NULL,
    sell_volume DOUBLE NOT NULL,
    delta DOUBLE NOT NULL,
    cvd DOUBLE NOT NULL,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS derived_market_structure (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    market_type VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    swing_high DOUBLE,
    swing_low DOUBLE,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS derived_liquidity (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    upper_liquidity_score DOUBLE,
    lower_liquidity_score DOUBLE,
    liquidity_asymmetry DOUBLE,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS derived_regime (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    primary_regime VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    evidence JSON NOT NULL,
    counter_evidence JSON NOT NULL,
    is_model_estimate BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS derived_scenarios (
    event_id VARCHAR PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    scenario VARCHAR NOT NULL,
    probability DOUBLE NOT NULL,
    confidence DOUBLE NOT NULL,
    metadata JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS market_regimes (
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol VARCHAR NOT NULL,
    primary_regime VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    evidence JSON NOT NULL,
    counter_evidence JSON NOT NULL
);
"""


class DuckDBStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(self.path))
        self.connection.execute(SCHEMA)

    def write(self, observations: list[Observation]) -> int:
        inserted = 0
        for observation in observations:
            already_stored = self.connection.execute(
                "SELECT 1 FROM market_observations WHERE event_id = ?",
                [observation.event_id],
            ).fetchone()
            if already_stored:
                continue
            result = self.connection.execute(
                """INSERT INTO market_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (event_id) DO NOTHING""",
                [
                    observation.event_id,
                    observation.timestamp_utc,
                    observation.source_timestamp_utc,
                    observation.source,
                    observation.exchange,
                    observation.market_type,
                    observation.symbol,
                    observation.metric,
                    observation.value,
                    json.dumps(observation.metadata, sort_keys=True),
                ],
            )
            target_table = (
                "trades"
                if observation.metric.startswith("trade_")
                else "liquidation_events"
                if observation.metric.startswith("liquidation_")
                else "orderbook_snapshots"
                if observation.metric.startswith("best_")
                else None
            )
            if target_table:
                self.connection.execute(
                    f"INSERT INTO {target_table} SELECT * FROM market_observations WHERE event_id = ?",
                    [observation.event_id],
                )
            inserted += 1
        self.connection.commit()
        return inserted

    def write_normalized_trades(self, trades: list[NormalizedTrade]) -> int:
        inserted = 0
        for trade in trades:
            payload = {
                "event_id": trade.event_id,
                "timestamp_utc": trade.timestamp_utc,
                "source_timestamp_utc": trade.source_timestamp_utc,
                "source": trade.source,
                "exchange": trade.exchange,
                "market_type": trade.market_type,
                "symbol": trade.symbol,
                "trade_id": trade.trade_id,
                "price": trade.price,
                "quantity": trade.quantity,
                "quote_volume": trade.quote_volume,
                "aggressor_side": trade.aggressor_side,
                "metadata": json.dumps(trade.metadata, sort_keys=True),
            }
            self.connection.execute(
                """INSERT INTO raw_trades (event_id, timestamp_utc, source_timestamp_utc, source, exchange, market_type, symbol, trade_id, price, quantity, quote_volume, aggressor_side, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (event_id) DO NOTHING""",
                [
                    payload["event_id"],
                    payload["timestamp_utc"],
                    payload["source_timestamp_utc"],
                    payload["source"],
                    payload["exchange"],
                    payload["market_type"],
                    payload["symbol"],
                    payload["trade_id"],
                    payload["price"],
                    payload["quantity"],
                    payload["quote_volume"],
                    payload["aggressor_side"],
                    payload["metadata"],
                ],
            )
            inserted += 1
        self.connection.commit()
        return inserted

    def write_raw_event(
        self, dataset: str, event: dict, validation_status: str = "VALID"
    ) -> bool:
        table = {
            "trades": "raw_trades",
            "orderbook": "raw_orderbook",
            "funding": "raw_funding",
            "open_interest": "raw_open_interest",
            "liquidations": "raw_liquidations",
        }.get(dataset)
        if table is None:
            raise ValueError(f"Unsupported raw dataset: {dataset}")
        event_id = event.get("event_id") or event.get("raw_payload_hash")
        if not event_id:
            raise ValueError("Raw event requires event_id or raw_payload_hash")
        if self.connection.execute(
            f"SELECT 1 FROM {table} WHERE event_id = ?", [event_id]
        ).fetchone():
            return False
        timestamp = event.get("event_timestamp") or event.get("timestamp")
        ingestion_timestamp = event.get("ingestion_timestamp_utc") or datetime.now(
            timezone.utc
        )
        common = {
            "event_id": event_id,
            "timestamp": timestamp,
            "source_timestamp": event.get("source_timestamp_utc") or timestamp,
            "source": event.get("source", "unknown"),
            "exchange": event.get("exchange"),
            "market_type": event.get("market_type"),
            "symbol": event.get("symbol"),
            "metadata": json.dumps(
                event.get("raw_payload", event.get("metadata", {})), sort_keys=True
            ),
            "ingestion": ingestion_timestamp,
            "hash": event.get("raw_payload_hash", ""),
            "status": validation_status,
        }
        if dataset == "trades":
            values = [
                event_id,
                common["timestamp"],
                common["source_timestamp"],
                common["source"],
                common["exchange"],
                common["market_type"],
                common["symbol"],
                str(event["trade_id"]),
                event["price"],
                event["quantity"],
                event["quote_volume"],
                event.get("aggressor_side", "unknown"),
                common["metadata"],
                common["ingestion"],
                common["hash"],
                common["status"],
            ]
            columns = "event_id, timestamp_utc, source_timestamp_utc, source, exchange, market_type, symbol, trade_id, price, quantity, quote_volume, aggressor_side, metadata, ingestion_timestamp_utc, raw_payload_hash, validation_status"
        elif dataset == "orderbook":
            levels = event.get("levels", [])
            rows = levels or [
                {
                    "side": "bid",
                    "price": event.get("best_bid"),
                    "quantity": event.get("bid_quantity", 0),
                },
                {
                    "side": "ask",
                    "price": event.get("best_ask"),
                    "quantity": event.get("ask_quantity", 0),
                },
            ]
            inserted = False
            for level in rows:
                if level.get("price") is None:
                    continue
                values = [
                    event_id + ":" + str(level.get("side")),
                    common["timestamp"],
                    common["source"],
                    common["exchange"],
                    common["market_type"],
                    common["symbol"],
                    level.get("side"),
                    level.get("price"),
                    level.get("quantity", 0),
                    common["metadata"],
                    event.get("sequence_id"),
                    event.get("update_type", "snapshot"),
                    common["ingestion"],
                    common["hash"],
                    common["status"],
                ]
                self.connection.execute(
                    "INSERT INTO raw_orderbook (event_id, timestamp_utc, source, exchange, market_type, symbol, side, price, quantity, metadata, sequence_id, update_type, ingestion_timestamp_utc, raw_payload_hash, validation_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (event_id) DO NOTHING",
                    values,
                )
                inserted = True
            self.connection.commit()
            return inserted
        elif dataset == "funding":
            values = [
                event_id,
                common["timestamp"],
                common["exchange"],
                common["market_type"],
                common["symbol"],
                event.get("funding_rate"),
                common["source_timestamp"],
                common["source"],
                common["metadata"],
                event.get("next_funding_time"),
                event.get("mark_price"),
                event.get("index_price"),
                common["ingestion"],
                common["hash"],
                common["status"],
            ]
            columns = "event_id, timestamp_utc, exchange, market_type, symbol, funding_rate, source_timestamp_utc, source, metadata, next_funding_time, mark_price, index_price, ingestion_timestamp_utc, raw_payload_hash, validation_status"
        elif dataset == "open_interest":
            values = [
                event_id,
                common["timestamp"],
                common["exchange"],
                common["market_type"],
                common["symbol"],
                event.get("open_interest"),
                common["source_timestamp"],
                common["source"],
                common["metadata"],
                event.get("open_interest_usd"),
                common["ingestion"],
                common["hash"],
                common["status"],
            ]
            columns = "event_id, timestamp_utc, exchange, market_type, symbol, open_interest, source_timestamp_utc, source, metadata, open_interest_usd, ingestion_timestamp_utc, raw_payload_hash, validation_status"
        else:
            values = [
                event_id,
                common["timestamp"],
                common["exchange"],
                common["market_type"],
                common["symbol"],
                event.get("side", "unknown"),
                event.get("price"),
                event.get("quantity"),
                event.get("USD_value", 0),
                common["source"],
                common["metadata"],
                event.get("liquidation_type"),
                common["ingestion"],
                common["hash"],
                common["status"],
            ]
            columns = "event_id, timestamp_utc, exchange, market_type, symbol, side, price, quantity, usd_value, source, metadata, liquidation_type, ingestion_timestamp_utc, raw_payload_hash, validation_status"
        self.connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({', '.join('?' for _ in values)})",
            values,
        )
        self.connection.commit()
        return True

    def reject_raw_event(self, dataset: str, event: dict, validation: dict) -> None:
        event_id = (
            event.get("event_id")
            or event.get("raw_payload_hash")
            or str(hash(json.dumps(event, sort_keys=True)))
        )
        self.connection.execute(
            "INSERT INTO rejected_raw_events VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?) ON CONFLICT (event_id) DO NOTHING",
            [
                event_id,
                event.get("exchange", "unknown"),
                dataset,
                validation.get("status", "INVALID"),
                json.dumps(validation.get("reasons", [])),
                json.dumps(event, sort_keys=True),
            ],
        )
        self.connection.commit()

    def write_websocket_event(
        self,
        event: Any,
        validation_status: str = "VALID",
        persist_snapshot: bool = True,
    ) -> bool:
        ingestion = datetime.now(timezone.utc)
        common = {
            "event_timestamp": event.event_timestamp,
            "source_timestamp_utc": event.event_timestamp,
            "ingestion_timestamp_utc": ingestion,
            "exchange": event.exchange,
            "market_type": event.market_type,
            "symbol": event.symbol,
            "source": f"{event.exchange}_public_websocket",
            "raw_payload": event.raw_payload,
            "raw_payload_hash": event.raw_payload_hash,
        }
        if event.dataset == "orderbook":
            if persist_snapshot:
                snapshot = {
                    **common,
                    "event_id": event.event_id + ":snapshot",
                    "timestamp": event.event_timestamp,
                    "levels": [
                        {"side": "bid", "price": price, "quantity": quantity}
                        for price, quantity in event.bids
                    ]
                    + [
                        {"side": "ask", "price": price, "quantity": quantity}
                        for price, quantity in event.asks
                    ],
                    "sequence_id": event.sequence_id,
                    "update_type": "snapshot",
                }
                self.write_raw_event("orderbook", snapshot, validation_status)
                return True
            update_id = event.event_id
            if self.connection.execute(
                "SELECT 1 FROM raw_orderbook_updates WHERE event_id = ?", [update_id]
            ).fetchone():
                return False
            self.connection.execute(
                "INSERT INTO raw_orderbook_updates (event_id, timestamp_utc, exchange, market_type, symbol, bids, asks, sequence_id, previous_sequence_id, update_type, ingestion_timestamp_utc, raw_payload_hash, validation_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (event_id) DO NOTHING",
                [
                    update_id,
                    event.event_timestamp,
                    event.exchange,
                    event.market_type,
                    event.symbol,
                    json.dumps(event.bids),
                    json.dumps(event.asks),
                    event.sequence_id,
                    event.previous_sequence_id,
                    event.update_type or "delta",
                    ingestion,
                    event.raw_payload_hash,
                    validation_status,
                ],
            )
            return True
        if event.dataset == "trades":
            payload = {
                **common,
                "event_id": event.event_id,
                "trade_id": event.trade_id,
                "price": event.price,
                "quantity": event.quantity,
                "quote_volume": (event.price or 0) * (event.quantity or 0),
                "aggressor_side": event.aggressor_side,
            }
        else:
            payload = {
                **common,
                "event_id": event.event_id,
                "price": event.price,
                "quantity": event.quantity,
                "USD_value": (event.price or 0) * (event.quantity or 0),
                "side": "unknown",
                "liquidation_type": "UNKNOWN",
            }
        return self.write_raw_event(event.dataset, payload, validation_status)

    def latest(self, symbol: str = "BTCUSDT") -> list[tuple]:
        return self.connection.execute(
            """SELECT timestamp_utc, exchange, market_type, metric, value, metadata
               FROM market_observations WHERE symbol = ?
               QUALIFY ROW_NUMBER() OVER (PARTITION BY exchange, market_type, metric ORDER BY timestamp_utc DESC) = 1
               ORDER BY exchange, market_type, metric""",
            [symbol],
        ).fetchall()

    def close(self) -> None:
        self.connection.close()

    def observations(
        self, symbol: str, metric: str | None, limit: int, offset: int
    ) -> list[tuple]:
        filters = ["symbol = ?"]
        params: list = [symbol]
        if metric:
            filters.append("metric = ?")
            params.append(metric)
        return self.connection.execute(
            f"SELECT timestamp_utc, source, exchange, market_type, symbol, metric, value, metadata FROM market_observations WHERE {' AND '.join(filters)} ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()


class PostgresStore:
    def __init__(self, dsn: str):
        import psycopg

        self.connection = psycopg.connect(dsn, autocommit=True)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS market_observations (
            event_id TEXT PRIMARY KEY, timestamp_utc TIMESTAMPTZ NOT NULL, source_timestamp_utc TIMESTAMPTZ,
            source TEXT NOT NULL, exchange TEXT NOT NULL, market_type TEXT NOT NULL, symbol TEXT NOT NULL,
            metric TEXT NOT NULL, value DOUBLE PRECISION NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )"""
        )

    def write(self, observations: list[Observation]) -> int:
        inserted = 0
        for observation in observations:
            result = self.connection.execute(
                """INSERT INTO market_observations (event_id, timestamp_utc, source_timestamp_utc, source, exchange, market_type, symbol, metric, value, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING""",
                (
                    observation.event_id,
                    observation.timestamp_utc,
                    observation.source_timestamp_utc,
                    observation.source,
                    observation.exchange,
                    observation.market_type,
                    observation.symbol,
                    observation.metric,
                    observation.value,
                    json.dumps(observation.metadata, sort_keys=True),
                ),
            )
            inserted += result.rowcount
        return inserted

    def observations(
        self, symbol: str, metric: str | None, limit: int, offset: int
    ) -> list[tuple]:
        filters = ["symbol = %s"]
        params: list = [symbol]
        if metric:
            filters.append("metric = %s")
            params.append(metric)
        return self.connection.execute(
            f"SELECT timestamp_utc, source, exchange, market_type, symbol, metric, value, metadata FROM market_observations WHERE {' AND '.join(filters)} ORDER BY timestamp_utc DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()

    def latest(self, symbol: str = "BTCUSDT") -> list[tuple]:
        return self.connection.execute(
            """SELECT timestamp_utc, exchange, market_type, metric, value, metadata FROM (
               SELECT timestamp_utc, exchange, market_type, metric, value, metadata,
               ROW_NUMBER() OVER (PARTITION BY exchange, market_type, metric ORDER BY timestamp_utc DESC) AS row_number
               FROM market_observations WHERE symbol = %s) latest WHERE row_number = 1 ORDER BY exchange, market_type, metric""",
            (symbol,),
        ).fetchall()

    def close(self) -> None:
        self.connection.close()
