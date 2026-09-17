# Data Quality

Raw events are normalized before storage and retain the exchange payload hash and ingestion timestamp.

- `VALID`: required timestamp and numeric values are present and basic sanity checks pass.
- `INVALID`: missing/invalid timestamp, non-positive price, negative quantity, or crossed/incomplete order book. The event is retained in `rejected_raw_events`.
- `SUSPECT`: a softer anomaly such as a future timestamp or out-of-range funding value.
- Duplicate identity is deterministic: exchange, dataset, symbol, market type, trade ID when available, timestamp, payload hash, side, price, and quantity.
- Provider timestamps are not replaced by local time. When an endpoint supplies only a scheduled funding time, the observation time is ingestion time and the scheduled source time remains in metadata.
- Order-book storage currently writes one bid and one ask level from each REST snapshot into `raw_orderbook`; it does not claim to be a full local incremental book.
- `best_bid < best_ask`, positive prices, nonnegative quantities, nonnegative OI, and funding rates within absolute decimal value `1.0` are required for a valid snapshot.
- REST retries are bounded to four attempts total with exponential backoff. HTTP errors are returned in the structured ingestion result.
- Public liquidation availability is exchange-specific. An unavailable endpoint is reported as `NOT_AVAILABLE`; no synthetic liquidation event is created.

The clean live smoke database is created by `scripts/live_market_data_smoke_test.py` and is independently queryable after the run.

## WebSocket evidence

The final 60-second public smoke run was persisted to `data/btc_market_intelligence/btc_ws_smoke_final4.duckdb` with metrics in `btc_ws_smoke_final4.json`:

- Binance: 50 trades written, 20 order-book updates processed, 11 sequence gaps and 11 resync attempts, 5 reconnects.
- Bybit: 87 trades and 407 order-book updates written, no sequence gaps, 1 reconnect.
- OKX: 217 trades and 242 order-book updates written, no sequence gaps, no reconnect.

This is a successful data-path proof for Bybit and OKX and a partial Binance proof. Binance trade/depth sockets were receiving data, but the run still experienced provider policy disconnects and required repeated book resynchronization. Reported lag is ingestion lag derived from event timestamp versus local receipt time; it is not network latency.

The hardened runner uses a bounded asynchronous writer queue. In the final measured run, maximum queue depth was `2` of `1000` and dropped events were `0`. Snapshot persistence was independently visible for Binance, Bybit, and OKX. Database write duration is measured per batch, but the current implementation still performs synchronous DuckDB work inside the writer task; the receive loop is decoupled, while full multi-process writer isolation remains future work.

The dedicated diagnostic run added stage timing. Typical database writes were approximately 47-79 ms, queue wait medians were approximately 93-344 ms, and local receive-to-commit medians were approximately 141-2,375 ms. Bybit and OKX exchange-event-to-receive medians were approximately 21.7-39.2 seconds, while Binance medians were approximately 13.7-17.6 seconds. Therefore the large observed age is already present at socket receive or in exchange timestamp semantics; it is not explained by DuckDB commit duration. The report names this `exchange_event_to_receive` lag and does not call it network latency.
