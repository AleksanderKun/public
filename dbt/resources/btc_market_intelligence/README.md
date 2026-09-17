# BTC Market Intelligence Engine

This resource is a read-only market data and analysis MVP. It does not place orders and it never fabricates live data.

Current status: `PARTIAL`. The public REST layer is live-tested for Binance, Bybit and OKX. The WebSocket raw layer is implemented and tested, but Binance Futures order-book synchronization and repeated `1008 Invalid request` behavior still require definitive integrated validation. CVD and downstream analytics are intentionally blocked until that work is complete.

For the complete project history, verified artifacts, decisions, limitations, and next actions, read [PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## Documentation

- [PROJECT_STATUS.md](docs/PROJECT_STATUS.md): consolidated handoff and current blockers.
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): storage and realtime boundaries.
- [DATA_SOURCES.md](docs/DATA_SOURCES.md): verified public endpoints and WebSocket channels.
- [DATA_QUALITY.md](docs/DATA_QUALITY.md): validation, provenance, latency, and completeness rules.
- [IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md): chronological implementation evidence.
- [LIMITATIONS_AND_REQUIRED_ACTIONS.md](docs/LIMITATIONS_AND_REQUIRED_ACTIONS.md): explicit limitations and required work.

## Current scope

- Normalized observations with UTC timestamp, source, exchange, market type, symbol, metric, value and raw metadata.
- Durable DuckDB storage at `dbt/data/btc_market_intelligence/market.duckdb`.
- Public REST collection for Binance spot/futures and Bybit linear BTCUSDT ticker, open interest and funding.
- Deterministic price/OI/funding regime classification with explainable evidence.
- Focused tests using recorded-style API payloads, not synthetic live claims.

## Run a real collection

Install the project dependencies, then run from the repository root:

```text
python -m pip install -r dbt/resources/btc_market_intelligence/requirements.txt
python dbt/resources/btc_market_intelligence/collect.py --provider all
```

The runner is self-contained; no API key is required for these public endpoints.

Collect the 5-minute Binance OHLCV history:

```text
poetry run python dbt/resources/btc_market_intelligence/collect.py --provider binance_ohlcv
```

Start API and websocket worker with Docker Compose:

```text
docker compose -f dbt/resources/btc_market_intelligence/docker-compose.yml up -d --build
```

Run the long-lived public websocket collectors with Poetry from the repository root:

```text
poetry run python dbt/resources/btc_market_intelligence/run_websockets.py
```

The process reconnects with bounded exponential backoff. Stop it with `Ctrl+C`.

## Data contract

Every observation has `timestamp_utc`, `source`, `exchange`, `market_type`, `symbol`, `metric`, `value`, `metadata`, and a deterministic `event_id` used for idempotent writes.

## Explicit limitations

The first slice does not yet collect websocket trades/liquidations, order book snapshots, ETF, macro or options data. Those are listed in the implementation log and are not represented as available.
