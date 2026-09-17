# Architecture

## Boundaries

```text
public exchange REST APIs
        |
        v
collectors.py  -->  Observation contract  -->  DuckDBStore
websocket adapters --> LocalOrderBook --> raw_orderbook_updates/raw_orderbook
                                                |
                                                +--> FastAPI read-only API
                                                +--> analytics.py model output
```

The implementation lives under `dbt/resources/btc_market_intelligence`. Durable local data lives under `dbt/data/btc_market_intelligence`; this keeps the market resource separate from the tax project database while respecting the repository layout.

## Provenance contract

Each observation records its collection timestamp, optional provider timestamp, source, exchange, market type, symbol, metric, numeric value and raw provider metadata. `event_id` is a SHA-256 hash of the observation content and is the idempotency key.

Provider timestamps are never replaced with local timestamps. `timestamp_utc` means when the collector received the observation; `source_timestamp_utc` means when the provider says the underlying measurement was produced.

## Realtime raw layer

`realtime.py` contains exchange-specific WebSocket adapters for Binance, Bybit and OKX. Trades are normalized directly from exchange IDs and sides. Order books use a REST bootstrap followed by WebSocket updates:

- Binance uses `U/u` update ranges and requires `U <= lastUpdateId + 1 <= u`; stale updates are discarded and gaps trigger a REST resync.
- Bybit uses the `u` monotonic update ID from `orderbook.50`; updates are applied only when newer than the local state.
- OKX uses `seqId` and `prevSeqId`; an update is accepted only when `prevSeqId` equals the local sequence.

Every update is retained in `raw_orderbook_updates`. Reconstructed levels are written to `raw_orderbook` at a controlled interval, rather than writing every dictionary mutation as a snapshot. The 60-second live test uses the public channels `trade`, `depth@100ms`, `publicTrade`, `orderbook.50`, `trades`, and `books5`.

## Storage evolution

DuckDB is the verified local adapter for this repository. The schema starts with a normalized observation ledger and empty derived-output tables. The Compose file provides a PostgreSQL/TimescaleDB deployment target, but no claim is made that the PostgreSQL adapter is implemented yet.

## Analysis principles

The current classifier is a transparent heuristic over price change, open-interest change and funding. It emits a regime, bounded confidence and evidence/counter-evidence. It is not a trading signal, forecast or execution component.
