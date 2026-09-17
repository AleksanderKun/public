import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from btc_intelligence.collectors import PublicMarketCollector
from btc_intelligence.storage import DuckDBStore, PostgresStore


async def main(provider: str) -> None:
    configured_database = os.getenv("BTC_MI_DATABASE_PATH")
    database = Path(configured_database) if configured_database else Path(__file__).parents[2] / "data" / "btc_market_intelligence" / "market.duckdb"
    store = PostgresStore(os.environ["DATABASE_URL"]) if os.getenv("DATABASE_URL") else DuckDBStore(database)
    collector = PublicMarketCollector()
    jobs = {"binance": collector.collect_binance, "bybit": collector.collect_bybit, "okx": collector.collect_okx, "binance_ohlcv": collector.collect_binance_ohlcv}
    selected = jobs if provider == "all" else {provider: jobs[provider]}
    try:
        for name, job in selected.items():
            try:
                observations = await job()
                print(f"{name}: received={len(observations)} inserted={store.write(observations)}")
            except Exception as exc:
                print(f"{name}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        store.close()


if __name__ == "__main__":
    requested = sys.argv[sys.argv.index("--provider") + 1] if "--provider" in sys.argv else "all"
    if requested not in {"all", "binance", "bybit", "okx", "binance_ohlcv"}:
        raise SystemExit("--provider must be all, binance, bybit, okx or binance_ohlcv")
    asyncio.run(main(requested))