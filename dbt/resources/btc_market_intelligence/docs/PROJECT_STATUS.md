# BTC Market Intelligence: Project Status and Handoff

Last verified: 2026-09-03

Latest prompt status: diagnostic verification is focused exclusively on the integrated Binance Futures depth lifecycle. CVD and all downstream work remain blocked.

Autonomy note: continuation may proceed without additional approval prompts. Each phase must still be completed only with executable test evidence, durable artifacts, and explicit reporting. The project must not advance to CVD or downstream analytics while the documented raw-realtime acceptance criteria remain incomplete.

## 2026-09-03 Resume Verification

The project was resumed and checked without modifying downstream analytics or the storage architecture.

- BTC market-intelligence tests: `22 passed in 3.75s`.
- BTC source and scripts compiled successfully with `compileall`.
- Fresh isolated Binance Futures depth probe completed: `16.187 seconds`, `148` messages, zero reconnects, no close code, no close reason.
- Probe artifact: `data/binance_ws_minimal_probe_current.json`.
- Fresh REST smoke wrote `4` Binance observations and `3` Bybit observations to `data/rest_validation_current.duckdb`; the runner did not print an OKX success line, so OKX REST current status is not claimed from this run.
- Separate current OKX REST smoke completed successfully with `3` observations written to `data/okx_validation_current.duckdb`.
- The current repository is testable and smoke-testable through scripts, but it is not yet a fully supervised unattended production system: no scheduler/monitoring contract guarantees continuous recovery, and integrated Binance WebSocket synchronization remains `PARTIAL`.
- Current integrated Binance depth-only resume test: `15 seconds`, artifact `data/binance_depth_resume_20260903.json`; `6` depth messages received, `0` written, `0` snapshots, `0` gaps, `2` reconnects, no reported errors. The run did not prove `SYNCHRONIZED`, so unsynchronized book data was correctly not persisted as valid.
- Binance integrated depth validation after the confirmed lifecycle fixes succeeded for `60 seconds`: artifact `data/binance_depth_verified_20260903.json`; `187` messages received, `181` updates, `1` bridge, `0` bridge failures, `0` gaps, `0` resyncs, `0` reconnects, synchronizer state `SYNCHRONIZED`, `201` writes including `18` reconstructed snapshots, queue max `2`, and dropped events `0`.
- Binance depth-plus-trades validation also succeeded for `60 seconds`: artifact `data/binance_depth_trades_verified_20260903.json`; `199` trades written and `169` depth messages with `151` continuations, `2` bridges, `0` bridge failures, `0` gaps, `0` resyncs, `0` reconnects, synchronizer state `SYNCHRONIZED`, `15` reconstructed snapshots, queue max `2`, and zero write errors.
- All-exchange 60-second WebSocket validation succeeded: artifact `data/all_exchanges_verified_20260903.json`; Binance `116` trades and `117` depth events, Bybit `106` trades and `84` depth events, OKX `54` trades and `58` depth events. All reported `0` gaps, `0` resyncs, `0` reconnects, `0` dropped events, and no errors; Binance state was `SYNCHRONIZED`. Queue maxima were `1` for Binance trades, `2` for Binance order book, `28` for Bybit streams, and `2` for OKX streams.
- Root cause confirmed: the direct Binance `/ws/<stream>` endpoint was receiving an invalid empty `{}` subscription from the integrated runner; the isolated probe sent no subscription. A second issue was applying the same depth event through both the synchronizer and generic local-book path. Both were corrected and the live result now shows continuous `pu`-based continuation.
- Full repository suite was rerun; the existing seven tax-calculator failures remain outside this resource. They were not modified.
- The all-exchange 60-second WebSocket milestone is confirmed by `data/all_exchanges_verified_20260903.json`: Binance `116` trades and `117` depth events, Bybit `106` trades and `84` depth events, OKX `54` trades and `58` depth events; all reported zero gaps, resyncs, reconnects, dropped events, and errors, with Binance `SYNCHRONIZED`.
- The requested five-minute stability attempt created `data/all_exchanges_stability_20260903.duckdb` but did not produce a final JSON report. The partial database contains `1938` raw trades, `845` raw order-book updates, and `166` raw order-book level rows through approximately `21:08:44 +02:00`; this is not accepted as a five-minute stability result.

This is an automated verification baseline, not a claim that the whole project is production-ready. The documented project status remains `PARTIAL` because integrated Binance synchronization, the five-minute stability test, and downstream CVD prerequisites are not complete.

## Mission

This project is not a BTC price dashboard. Its purpose is to build a provenance-first market-analysis system that can distinguish observed market facts from model estimates and later answer questions such as:

- Is a BTC move driven by real spot demand, leverage in perpetuals, short covering, or deleveraging?
- Does price agree with spot/perpetual flow, open interest, funding, liquidations, and available liquidity?

The system must never create a convincing narrative from missing or fabricated data. Public market data is collected first; derived analytics come only after the raw layer is trustworthy.

## Scope Order

The agreed implementation order is:

```text
Binance + Bybit + OKX
  -> raw trades
  -> open interest
  -> funding
  -> liquidations where public
  -> order-book snapshots and updates
  -> normalized database
  -> validation and tests
  -> CVD
  -> market structure and liquidity
  -> regime and scenario engines
  -> backtesting
```

CVD, spot CVD, liquidity scoring, regimes, scenarios, AI analysis, dashboards, and trading execution are explicitly deferred until the realtime raw layer is complete.

## Existing Architecture

The implementation lives under `dbt/resources/btc_market_intelligence`.

```text
public REST / WebSocket APIs
        |
        v
exchange-specific adapters
        |
        v
normalization and validation
        |
        +--> bounded WebSocket queue --> batch writer
        |                                  |
        |                                  v
        |                             DuckDB raw tables
        |
        +--> REST bootstrap and recovery
        |
        v
raw observations and raw order-book updates
```

There is one storage system and one canonical normalized trade model. Do not create a second database, storage abstraction, or normalization model.

## Storage Contract

Existing raw tables include:

- `raw_trades`
- `raw_open_interest`
- `raw_funding`
- `raw_liquidations`
- `raw_orderbook`
- `raw_orderbook_updates`
- `rejected_raw_events`

`raw_orderbook_updates` is the forensic delta/update ledger. `raw_orderbook` contains controlled reconstructed snapshots. Their identities must remain independent: replaying a delta must be a duplicate, while an equivalent reconstructed snapshot must still be writable.

All raw events preserve exchange identity, canonical symbol, market type, source timestamp where available, ingestion timestamp, payload hash, and validation status.

## REST Validation Milestone

A clean public REST run proved the Binance, Bybit, and OKX adapters can retrieve and persist bounded data without private API keys.

Measured clean REST evidence included:

- Binance: trades, OI, funding, order book
- Bybit: trades, OI, funding, order book
- OKX: trades, OI, funding, order book

Liquidations are not fabricated. A dataset is reported as unavailable when the tested public endpoint does not provide a valid event shape.

## WebSocket Components

### Adapters

- `realtime.py`: WebSocket event contract, exchange parsers, local order book, Binance synchronizer
- `realtime_writer.py`: bounded asynchronous batch writer
- `live_market_data_ws_smoke_test.py`: bounded live test and JSON metrics
- `binance_ws_minimal_probe.py`: isolated Binance endpoint probe

### Exchange Channels

- Binance Futures trades: `wss://fstream.binance.com/ws/btcusdt@trade`
- Binance Futures depth: `wss://fstream.binance.com/ws/btcusdt@depth@100ms`
- Bybit linear trades: `publicTrade.BTCUSDT`
- Bybit linear order book: `orderbook.50.BTCUSDT`
- OKX swap trades: `trades`, `BTC-USDT-SWAP`
- OKX swap order book: `books5`, `BTC-USDT-SWAP`

### Sequence Rules

- Binance initial bridge uses `U <= lastUpdateId + 1 <= u`.
- Binance Futures messages also provide `pu`; after the bridge, continuity must use `pu == previous_u`.
- Bybit uses monotonic `u` updates.
- OKX uses `prevSeqId == previous seqId` and increasing `seqId`.

## Minimal Binance Probe

Artifact:

- `data/binance_ws_minimal_probe.json`

Result:

- one direct connection
- endpoint remained open for `61.094 seconds`
- `587` raw depth messages received
- reconnects: `0`
- close code: none
- close reason: none

Conclusion: the public Binance Futures depth endpoint works in the environment. Therefore the earlier integrated `1008 Invalid request` behavior is not proven to be an endpoint outage.

Latest isolated probe artifact:

- `data/binance_ws_minimal_probe.json`
- endpoint: `wss://fstream.binance.com/ws/btcusdt@depth@100ms`
- one connection, `61.094 seconds`, `587` messages
- reconnects: `0`
- close code/reason: none
- no DuckDB, writer, synchronizer, REST snapshot, or local order book

The probe is conclusive for endpoint availability. It does not prove the integrated runner lifecycle.

## Diagnostic WebSocket Run

Artifact:

- `data/btc_ws_diagnostic.json`
- `data/btc_ws_diagnostic.duckdb`

The diagnostic run showed:

- database writes were generally approximately `47-79 ms`
- queue wait medians were approximately `93-344 ms`
- queue maximum was `2 / 1000`
- dropped events were `0`
- the large observed age was already present at exchange-event-to-receive time

Approximate exchange-event-to-receive medians:

- Binance: `13.7-17.6 seconds`
- Bybit: `21.7-27.5 seconds`
- OKX: `25.6-39.2 seconds`

These values are not called network latency. They may reflect exchange timestamp semantics, feed publication age, provider buffering, or environment/network behavior.

## Latest Integrated Binance Depth Result

Artifact:

- `data/binance_depth_validation3.json`
- `data/binance_depth_validation3.duckdb`

Result before the final `pu` integration fix:

- messages received: `18`
- messages persisted: `0`
- bridges found: `0`
- reconnects: `7`
- synchronized state: not achieved
- valid `raw_orderbook` rows: `0`

The runner now invokes `BinanceOrderBookSynchronizer`, but a clean post-`pu` integrated live result has not yet proven `SYNCHRONIZED`.

### Current path trace

Before the latest diagnostic work, the integrated runner path was:

```text
create LocalOrderBook/synchronizer
        -> open Binance WebSocket
        -> start REST snapshot task
        -> parse depth message
        -> buffer raw message while not synchronized
        -> synchronize when snapshot task is complete
        -> enqueue only after synchronized
        -> batch writer -> raw_orderbook_updates/raw_orderbook
```

The current runner invokes the existing `BinanceOrderBookSynchronizer`; the remaining diagnostic question is whether the snapshot task completes while the socket remains alive and whether its buffered events contain a bridge. A failed bridge starts a new bounded resync cycle. The runner must always preserve that result in JSON rather than ending without an artifact.

### Binance Futures payload semantics

The minimal probe confirmed that depth messages include `E`, `T`, `U`, `u`, `pu`, `b`, and `a`. Initial synchronization uses `U/u` with `U <= lastUpdateId + 1 <= u`. After the bridge, `pu == previous_u` is the continuity rule. Source payloads are preserved; timestamps are not shifted.

## Realtime Hardened Run

Artifact:

- `data/btc_ws_smoke_hardened.json`
- `data/btc_ws_smoke_hardened.duckdb`

Measured run:

| Exchange | Dataset | Received | Written | Gaps | Resyncs | Reconnects |
|---|---:|---:|---:|---:|---:|---:|
| Binance | trades | 19 | 19 | 0 | 0 | 4 |
| Binance | order book | 13 | 14 | 7 | 7 | 2 |
| Bybit | trades | 2 | 2 | 0 | 0 | 1 |
| Bybit | order book | 161 | 177 | 0 | 0 | 1 |
| OKX | trades | 74 | 74 | 0 | 0 | 0 |
| OKX | order book | 91 | 100 | 0 | 0 | 0 |

Queue:

- maximum observed depth: `2 / 1000`
- dropped events: `0`

Snapshots persisted in that run:

- Binance: `2` level rows
- Bybit: `32` level rows
- OKX: `18` level rows

The additional written rows are controlled reconstructed snapshots and must not be confused with received WebSocket updates.

## Binance 1008 Status

Integrated runner reports:

```text
close_code = 1008
close_reason = Invalid request
```

The minimal direct depth probe did not reproduce this. The exact cause is therefore unresolved. Do not attribute it to IP, rate limiting, TLS, Binance policy, or stream syntax without new evidence.

Use the status:

```text
BINANCE_PUBLIC_WS_ISSUE_UNRESOLVED
```

until a connection-level diagnostic proves the trigger.

## Tests

BTC market-intelligence package:

```text
22 passed
```

Full repository:

```text
32 passed, 7 failed
```

The seven failures are existing tax-calculator assertions outside this resource. They must not be fixed by weakening or changing the BTC market-data tests.

## Current Status

```text
PARTIAL
```

The raw realtime layer is not complete because:

1. post-`pu` Binance synchronization has not been proven in a clean integrated live run
2. Binance reconnects and `1008 Invalid request` remain unexplained
3. a complete 60-second Binance depth-only result after the latest integration changes is still required
4. the requested Binance depth-plus-trades run is still pending
5. a five-minute stability run has not been executed
6. receive-time capture is recorded after `recv()`/JSON parsing, not at the earliest library socket boundary

The minimal endpoint probe is now complete and successful. The integrated Binance depth test after the `pu` and lifecycle changes remains unproven because the latest clean run has not yet produced a valid final report with `SYNCHRONIZED`.

## Exact Next Work

Do only the following next:

1. Keep the successful isolated probe as the endpoint baseline; do not change its URL without protocol evidence.
2. Preserve full Binance connection diagnostics: connection ID, URL, stream, open/close time, close code/reason, last message, message count, reconnect delay, and connection age.
3. Finalize the integrated synchronizer report so every task failure and failed bridge is emitted to JSON.
4. Run a clean 15-20 second Binance depth-only test and require a valid artifact.
5. Verify `bridge_found >= 1`, `SYNCHRONIZED`, valid snapshots, valid bid/ask, and no silent drops.
6. Run a clean Binance depth-only test for 60 seconds, then Binance depth plus trades for 60 seconds.
7. Only after those pass, run all three exchanges and then the five-minute stability test.

Do not begin CVD or downstream analytics until this checklist is complete.
