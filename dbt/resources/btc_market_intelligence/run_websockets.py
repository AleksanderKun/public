import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from btc_intelligence.storage import DuckDBStore, PostgresStore
from btc_intelligence.websockets import consume_with_reconnect, parse_binance_message, parse_bybit_message


async def main() -> None:
    configured_database = os.getenv("BTC_MI_DATABASE_PATH")
    database = Path(configured_database) if configured_database else Path(__file__).parents[2] / "data" / "btc_market_intelligence" / "market.duckdb"
    store = PostgresStore(os.environ["DATABASE_URL"]) if os.getenv("DATABASE_URL") else DuckDBStore(database)
    async def sink(observations):
        store.write(observations)
    binance_spot = consume_with_reconnect(
        "wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/btcusdt@bookTicker",
        {}, parse_binance_message, sink,
    )
    binance_futures = consume_with_reconnect(
        "wss://fstream.binance.com/stream?streams=btcusdt@forceOrder",
        {}, parse_binance_message, sink,
    )
    bybit = consume_with_reconnect(
        "wss://stream.bybit.com/v5/public/linear",
        {"op": "subscribe", "args": ["publicTrade.BTCUSDT", "allLiquidation.BTCUSDT", "orderbook.1.BTCUSDT"]},
        parse_bybit_message, sink,
    )
    try:
        await asyncio.gather(binance_spot, binance_futures, bybit)
    finally:
        store.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass