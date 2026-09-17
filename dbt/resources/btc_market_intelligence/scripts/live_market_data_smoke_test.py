from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btc_intelligence.adapters import BinanceMarketDataAdapter, BybitMarketDataAdapter, OKXMarketDataAdapter
from btc_intelligence.ingestion import RawMarketIngestionService
from btc_intelligence.storage import DuckDBStore


async def main() -> int:
    database_path = Path(os.getenv("BTC_MI_DATABASE_PATH", str(ROOT / "data" / "btc_market_intelligence" / "live_smoke.duckdb")))
    report_path = Path(os.getenv("BTC_MI_SMOKE_REPORT_PATH", str(database_path.with_suffix(".json"))))
    store = DuckDBStore(database_path)
    service = RawMarketIngestionService(store, {
        "binance": BinanceMarketDataAdapter(),
        "bybit": BybitMarketDataAdapter(),
        "okx": OKXMarketDataAdapter(),
    })
    results = []
    try:
        for exchange in ("binance", "bybit", "okx"):
            results.extend(await service.ingest_exchange(exchange, "BTCUSDT"))
        print("LIVE INGESTION RESULTS")
        print("EXCHANGE | DATASET | STATUS | RECEIVED | VALID | DUPLICATE | WRITTEN | MIN_TS | MAX_TS | ERROR")
        for result in results:
            print(f"{result.exchange.upper()} | {result.dataset} | {result.status} | {result.records_received} | {result.records_valid} | {result.records_duplicate} | {result.records_written} | {result.min_timestamp or '-'} | {result.max_timestamp or '-'} | {'; '.join(result.errors) or 'none'}")
        report_path.write_text(json.dumps([result.as_dict() for result in results], indent=2), encoding="utf-8")
        print("\nDATABASE VERIFICATION")
        for table, dataset in (("raw_trades", "trades"), ("raw_open_interest", "open_interest"), ("raw_funding", "funding"), ("raw_orderbook", "orderbook"), ("raw_liquidations", "liquidations")):
            query = f"SELECT exchange, COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc) FROM {table} GROUP BY exchange ORDER BY exchange"
            for exchange, count, min_ts, max_ts in store.connection.execute(query).fetchall():
                extra = ""
                if dataset == "trades":
                    extra = str(store.connection.execute("SELECT MIN(price), MAX(price), SUM(quantity), SUM(quote_volume) FROM raw_trades WHERE exchange = ?", [exchange]).fetchone())
                elif dataset == "open_interest":
                    extra = str(store.connection.execute("SELECT MIN(open_interest), MAX(open_interest) FROM raw_open_interest WHERE exchange = ?", [exchange]).fetchone())
                elif dataset == "funding":
                    extra = str(store.connection.execute("SELECT MIN(funding_rate), MAX(funding_rate) FROM raw_funding WHERE exchange = ?", [exchange]).fetchone())
                elif dataset == "orderbook":
                    extra = str(store.connection.execute("SELECT COUNT(*), MIN(price), MAX(price) FROM raw_orderbook WHERE exchange = ?", [exchange]).fetchone())
                print(f"{dataset}: {exchange} rows={count} min_timestamp={min_ts} max_timestamp={max_ts} metrics={extra}")
        critical = [item for item in results if item.dataset in {"trades", "open_interest", "funding", "orderbook"} and item.status == "DOWN"]
        return 1 if critical else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
