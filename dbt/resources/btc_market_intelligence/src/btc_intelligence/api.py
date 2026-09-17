from pathlib import Path
import os
from typing import Any

from fastapi import FastAPI, Query

from .analytics import market_report
from .storage import DuckDBStore, PostgresStore


configured_database = os.getenv("BTC_MI_DATABASE_PATH")
DEFAULT_DB = (
    Path(configured_database)
    if configured_database
    else Path(__file__).resolve().parents[4]
    / "data"
    / "btc_market_intelligence"
    / "market.duckdb"
)
app = FastAPI(
    title="BTC Market Intelligence API",
    version="0.1.0",
    description="Read-only market observations and transparent model outputs.",
)


def _store() -> DuckDBStore | PostgresStore:
    return (
        PostgresStore(os.environ["DATABASE_URL"])
        if os.getenv("DATABASE_URL")
        else DuckDBStore(DEFAULT_DB)
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data_store": os.getenv("DATABASE_URL", str(DEFAULT_DB))}


@app.get("/data/observations")
def observations(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=30),
    metric: str | None = Query(None, max_length=50),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    store = _store()
    try:
        filters = ["symbol = ?"]
        params: list[Any] = [symbol]
        if metric:
            filters.append("metric = ?")
            params.append(metric)
        where = " AND ".join(filters)
        rows = store.observations(symbol, metric, limit, offset)
        return {
            "items": [
                dict(
                    zip(
                        [
                            "timestamp_utc",
                            "source",
                            "exchange",
                            "market_type",
                            "symbol",
                            "metric",
                            "value",
                            "metadata",
                        ],
                        row,
                    )
                )
                for row in rows
            ],
            "limit": limit,
            "offset": offset,
        }
    finally:
        store.close()


@app.get("/market/current")
def current(
    symbol: str = Query("BTCUSDT", min_length=3, max_length=30)
) -> dict[str, Any]:
    store = _store()
    try:
        return {
            "symbol": symbol,
            "observations": [
                dict(
                    zip(
                        [
                            "timestamp_utc",
                            "exchange",
                            "market_type",
                            "metric",
                            "value",
                            "metadata",
                        ],
                        row,
                    )
                )
                for row in store.latest(symbol)
            ],
        }
    finally:
        store.close()


def _metric_data(metric: str, symbol: str, limit: int, offset: int) -> dict[str, Any]:
    return observations(symbol=symbol, metric=metric, limit=limit, offset=offset)


@app.get("/data/price")
def price(
    symbol: str = "BTCUSDT",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _metric_data("price", symbol, limit, offset)


@app.get("/data/oi")
def open_interest(
    symbol: str = "BTCUSDT",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _metric_data("open_interest", symbol, limit, offset)


@app.get("/data/funding")
def funding(
    symbol: str = "BTCUSDT",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _metric_data("funding_rate", symbol, limit, offset)


@app.get("/data/options")
def options(
    symbol: str = "BTC",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _metric_data("options_open_interest", symbol, limit, offset)


@app.get("/data/macro")
def macro(
    series_id: str = Query("DFF", min_length=2, max_length=30),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _metric_data("macro_value", series_id, limit, offset)


@app.get("/market/regime")
def regime() -> dict[str, Any]:
    return {
        "status": "insufficient_data",
        "message": "At least two comparable observations per metric are required; no model output is fabricated.",
    }


@app.get("/market/scenarios")
def scenarios() -> dict[str, Any]:
    return {"status": "insufficient_data", "scenarios": [], "is_model_estimate": True}


@app.get("/market/score")
def score() -> dict[str, Any]:
    return {"status": "insufficient_data", "components": {}, "is_model_estimate": True}


@app.get("/market/liquidity")
def liquidity() -> dict[str, Any]:
    return {
        "status": "insufficient_data",
        "zones": [],
        "message": "Liquidity zones require historical highs/lows or order-book/liquidation observations.",
    }


@app.get("/market/report")
def report() -> dict[str, Any]:
    return market_report(
        ["The API is online and the current datastore is queryable."],
        {"status": "insufficient_data", "is_model_estimate": True},
        ["No market hypothesis is issued until sufficient comparable history exists."],
    )
