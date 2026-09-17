# Data Sources

Status reflects the adapter implementation and the clean live smoke run on 2026-08-22.

| Exchange | Dataset | Public API | Realtime | Historical | Auth | Status |
|---|---|---|---|---|---|---|
| Binance | Spot trades | `/api/v3/trades` | REST bounded snapshot | recent only | no | LIVE-TESTED |
| Binance | Perpetual trades | `/fapi/v1/trades` | REST bounded snapshot | recent only | no | LIVE-TESTED |
| Binance | Open interest | `/fapi/v1/openInterest` | REST snapshot | current | no | LIVE-TESTED |
| Binance | Funding | `/fapi/v1/fundingRate` | REST snapshot | recent funding row | no | LIVE-TESTED |
| Binance | Order book | `/api/v3/depth` | REST snapshot; public WebSocket exists | current | no | LIVE-TESTED |
| Binance | Liquidations | public `forceOrder` WebSocket | WebSocket | no REST history used | no | NOT_AVAILABLE in REST smoke |
| Bybit | Spot/perpetual trades | `/v5/market/recent-trade` | REST bounded snapshot | recent only | no | LIVE-TESTED |
| Bybit | Open interest | `/v5/market/open-interest` | REST snapshot | recent interval | no | LIVE-TESTED |
| Bybit | Funding | `/v5/market/funding/history` | REST snapshot | recent row | no | LIVE-TESTED |
| Bybit | Order book | `/v5/market/orderbook` | REST snapshot; public WebSocket exists | current | no | LIVE-TESTED |
| Bybit | Liquidations | public `allLiquidation` WebSocket | WebSocket | no REST history used | no | NOT_AVAILABLE in REST smoke |
| OKX | Spot/perpetual trades | `/api/v5/market/trades` | REST bounded snapshot | recent only | no | LIVE-TESTED |
| OKX | Open interest | `/api/v5/public/open-interest` | REST snapshot | current | no | LIVE-TESTED |
| OKX | Funding | `/api/v5/public/funding-rate` | REST snapshot | current/scheduled | no | LIVE-TESTED |
| OKX | Order book | `/api/v5/market/books` | REST snapshot; public WebSocket exists | current | no | LIVE-TESTED |
| OKX | Liquidations | `/api/v5/public/liquidation-orders` | REST endpoint | provider-dependent | no | NOT_AVAILABLE if endpoint returns no rows |

The smoke test uses only public endpoints and writes normalized output to the existing DuckDB raw tables. REST requests are bounded and use retry with exponential backoff.

## WebSocket channels

| Exchange | Dataset | Public WebSocket | Subscription/channel | Sequence model | Live status |
|---|---|---|---|---|---|
| Binance | trades | `wss://fstream.binance.com/ws` | `BTCUSDT@trade` | trade ID | PARTIAL: live events, policy reconnects |
| Binance | order book | `wss://fstream.binance.com/ws` | `BTCUSDT@depth@100ms` | `U/u` bridge | PARTIAL: live updates, resyncs observed |
| Bybit | trades | `wss://stream.bybit.com/v5/public/linear` | `publicTrade.BTCUSDT` | exchange trade ID | LIVE-TESTED |
| Bybit | order book | same | `orderbook.50.BTCUSDT` | monotonic `u` | LIVE-TESTED |
| OKX | trades | `wss://ws.okx.com:8443/ws/v5/public` | `trades`, `BTC-USDT-SWAP` | trade ID | LIVE-TESTED |
| OKX | order book | same | `books5`, `BTC-USDT-SWAP` | `prevSeqId/seqId` | LIVE-TESTED |

The WebSocket smoke run does not claim liquidation events because no liquidation channel was included in the tested OKX subscription and Binance/Bybit liquidation availability remains represented by their existing public stream parsers. No fake liquidation events are written.
