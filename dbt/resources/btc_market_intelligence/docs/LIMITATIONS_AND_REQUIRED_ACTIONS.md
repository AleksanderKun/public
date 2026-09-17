# Limitations And Required Actions

This document is intentionally explicit. The current implementation is a working ingestion and analysis foundation, not a validated trading decision system.

## Not completed

- PostgreSQL runtime adapter from Python is active in Compose, with idempotent writes; the SQL migration is automatic for fresh volumes, while existing volumes require a one-time manual migration.
- Long-running websocket uptime verification beyond the current live runtime check and operational process supervision beyond Docker restart policy.
- Separate typed OHLCV, funding, open-interest and price tables; normalized observations are available.
- Advanced liquidation clustering, multi-timeframe indicators and full calibration of scenario probabilities.
- ETF importer accepts verified CSV input, but no automatic official ETF provider is configured.
- CME futures and delayed COT data.
- Alert delivery, dashboard, backtesting, lookahead/leakage validation and production monitoring.
- Automatic scheduled report delivery; the API report structure with FACT, MODEL_OUTPUT and HYPOTHESIS is available.
- Public live ingestion engine is implemented for Binance, Bybit and OKX at the adapter layer, but it is not yet persisted to a durable scheduled worker loop across all datasets. The adapter contract is verified; the long-running production scheduler remains a separate runtime concern.
- A clean bounded public REST smoke run has been persisted and queried successfully for all three exchanges. It proves the REST path and raw database writes, not long-running WebSocket uptime or historical completeness.
- The current order-book REST implementation stores the top bid and ask levels from each snapshot. Incremental local-book assembly, sequence-gap resynchronization and retention/compression are still pending.
- Liquidation history is not assumed available through the tested unauthenticated REST paths for Binance and Bybit; their public liquidation WebSocket streams remain the correct realtime path.
- WebSocket live test is currently `PARTIAL`: Bybit and OKX produced realtime trades/order-book updates; Binance produced realtime events but still had policy disconnects and 11 order-book resyncs during the 60-second run.
- Ingestion lag was elevated on parts of the run, so the reported lag percentiles are diagnostic only and must not be interpreted as exchange network latency.

## Required user action

- Docker Desktop is installed and the local Compose stack has been started; keep it running for API/worker operation.
- Keep the public API usage within exchange rate limits; no API keys are required for the current endpoints.
- Before using any model output operationally, allow sufficient historical data to accumulate and run the planned backtests.
- Provide `FRED_API_KEY` in `.env` to collect FRED macro series. Deribit public options collection needs no key.
- Provide a verified ETF CSV/provider source to enable automatic ETF flow collection; the importer does not invent missing values.

No trading execution is present or enabled.
