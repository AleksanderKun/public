from datetime import datetime, timezone

from btc_intelligence.analytics import classify_price_oi_funding
from btc_intelligence.analytics import (
    classify_market_regime,
    compute_cvd,
    explainable_score,
    market_report,
    market_structure,
    ohlcv_indicators,
    scenario_estimates,
)
from btc_intelligence.models import Observation
from btc_intelligence.storage import DuckDBStore


def test_regime_classification_is_probabilistic_and_explainable():
    result = classify_price_oi_funding(4.2, -8.7, 0.0001)
    assert result.primary_regime == "SHORT_SQUEEZE"
    assert 0 < result.confidence <= 1
    assert result.evidence == ["price increased", "open interest decreased"]
    assert result.timestamp.tzinfo == timezone.utc


def test_duckdb_storage_is_idempotent(tmp_path):
    store = DuckDBStore(tmp_path / "market.duckdb")
    observation = Observation(
        datetime(2026, 8, 22, tzinfo=timezone.utc),
        "fixture",
        "binance",
        "spot",
        "BTCUSDT",
        "price",
        100.0,
    )
    assert store.write([observation, observation]) == 1
    assert len(store.latest()) == 1
    store.close()


def test_cvd_and_score_are_explainable():
    cvd = compute_cvd([{"volume": "2", "side": "Buy"}, {"volume": "1", "side": "Sell"}])
    score = explainable_score({"spot_demand": 18, "funding": -7, "cvd": cvd["delta"]})
    assert cvd["delta"] == 1
    assert score["is_model_estimate"] is True
    assert score["total"] == 12


def test_structure_and_scenarios_refuse_short_history():
    assert market_structure([1, 2, 3])["status"] == "insufficient_data"
    scenarios = scenario_estimates("SHORT_SQUEEZE", 10)
    assert round(sum(item["probability"] for item in scenarios), 4) == 1
    assert all(item["is_model_estimate"] for item in scenarios)


def test_indicators_and_report_separate_facts_from_models():
    candles = [
        {"open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i}
        for i in range(16)
    ]
    indicators = ohlcv_indicators(candles)
    regime = classify_market_regime(
        {
            "price_change_pct": 2,
            "oi_change_pct": 0.5,
            "funding_rate": 0.0001,
            "spot_cvd_change": 2,
        }
    )
    report = market_report(
        ["provider observation exists"], regime, ["continuation remains possible"]
    )
    assert indicators["status"] == "ok"
    assert regime["primary_regime"] == "SPOT_LED_RALLY"
    assert set(report) >= {"FACT", "MODEL_OUTPUT", "HYPOTHESIS"}


def test_ohlcv_collection_is_normalized(monkeypatch):
    from btc_intelligence.collectors import PublicMarketCollector

    async def fake_get(self, client, url, params=None):
        return [[1700000000000, "100", "102", "99", "101", "4", 1700000300000]]

    monkeypatch.setattr(PublicMarketCollector, "_get", fake_get)
    import asyncio

    rows = asyncio.run(PublicMarketCollector().collect_binance_ohlcv())
    assert rows[0].metric == "ohlcv_close"
    assert rows[0].metadata["interval"] == "5m"


def test_fred_requires_explicit_credential(monkeypatch):
    from btc_intelligence.external_sources import ExternalSourceCollector

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    import asyncio

    try:
        asyncio.run(ExternalSourceCollector().collect_fred_series("DFF"))
    except RuntimeError as error:
        assert "FRED_API_KEY" in str(error)
    else:
        raise AssertionError("FRED collection must not run without a configured key")


def test_alerts_and_etf_import_preserve_provenance(tmp_path):
    from btc_intelligence.alerts import detect_alerts
    from btc_intelligence.etf import read_etf_flows

    path = tmp_path / "flows.csv"
    path.write_text("date,fund,net_flow_usd\n2026-08-22,ETF-A,1000\n", encoding="utf-8")
    rows = read_etf_flows(path)
    alerts = detect_alerts({"oi_change_pct": 8, "spot_cvd_change": 0})
    assert rows[0].market_type == "etf"
    assert rows[0].source_timestamp_utc.tzinfo == timezone.utc
    assert alerts[0]["type"] == "LEVERAGE_WITHOUT_SPOT_CONFIRMATION"


def test_raw_schema_and_trade_normalization_include_exchange_specific_metadata():
    from btc_intelligence.models import normalize_trade
    from btc_intelligence.storage import DuckDBStore

    binance = normalize_trade(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        trade_id="10",
        price="42300.5",
        quantity="0.75",
        source="binance_public_rest",
        source_timestamp_utc=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
        metadata={"is_buyer_maker": True, "raw_side": "sell"},
    )
    bybit = normalize_trade(
        exchange="bybit",
        market_type="perpetual",
        symbol="BTCUSDT",
        trade_id="1001",
        price="42301.0",
        quantity="1.2",
        source="bybit_public_rest",
        source_timestamp_utc=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
        metadata={"side": "Buy"},
    )
    assert binance.aggressor_side == "sell"
    assert bybit.aggressor_side == "buy"
    assert binance.quote_volume == 31725.375

    store = DuckDBStore("/tmp/test_btc_market_raw.duckdb")
    store.write_normalized_trades([binance, bybit])
    assert (
        store.connection.execute("SELECT COUNT(*) FROM raw_trades").fetchone()[0] == 2
    )
    assert (
        store.connection.execute("SELECT COUNT(*) FROM raw_orderbook").fetchone()[0]
        == 0
    )
    store.close()


def test_exchange_market_data_adapters_match_common_contract():
    from btc_intelligence.adapters import (
        BinanceMarketDataAdapter,
        BybitMarketDataAdapter,
        OKXMarketDataAdapter,
    )

    binance = BinanceMarketDataAdapter()
    bybit = BybitMarketDataAdapter()
    okx = OKXMarketDataAdapter()

    for adapter in (binance, bybit, okx):
        assert hasattr(adapter, "get_trades")
        assert hasattr(adapter, "get_orderbook")
        assert hasattr(adapter, "get_open_interest")
        assert hasattr(adapter, "get_funding")
        assert hasattr(adapter, "get_liquidations")

    binance_trade = binance.normalize_trade(
        {
            "a": 7,
            "p": "42100.5",
            "q": "0.8",
            "m": True,
            "T": 1700000000000,
        },
        symbol="BTCUSDT",
        market_type="spot",
    )
    assert binance_trade["trade_id"] == "7"
    assert binance_trade["aggressor_side"] == "sell"
    assert binance_trade["quote_volume"] == 33680.4

    bybit_trade = bybit.normalize_trade(
        {
            "i": "b-1001",
            "p": "42101.0",
            "v": "0.5",
            "S": "Buy",
            "T": 1700000001000,
        },
        symbol="BTCUSDT",
        market_type="perpetual",
    )
    assert bybit_trade["trade_id"] == "b-1001"
    assert bybit_trade["aggressor_side"] == "buy"

    okx_oi = okx.normalize_open_interest(
        {
            "instId": "BTC-USDT-SWAP",
            "oi": "1200.5",
            "ts": "1700000000000",
        },
        symbol="BTCUSDT",
        market_type="perpetual",
    )
    assert okx_oi["open_interest"] == 1200.5
    assert okx_oi["market_type"] == "perpetual"

    assert hasattr(binance, "validate_event")
    assert (
        binance.validate_event(
            {"timestamp": "2026-08-22T12:00:00Z", "price": 10, "quantity": 0.5}
        )["status"]
        == "VALID"
    )


def test_ingestion_service_persists_and_deduplicates_raw_events(tmp_path):
    import asyncio
    from btc_intelligence.adapters import BinanceMarketDataAdapter
    from btc_intelligence.ingestion import RawMarketIngestionService

    class FixtureAdapter(BinanceMarketDataAdapter):
        async def get_trades(self, symbol="BTCUSDT", market_type="spot", limit=20):
            return [
                self.normalize_trade(
                    {"a": 1, "p": "100", "q": "2", "m": False, "T": 1700000000000},
                    symbol,
                    market_type,
                )
            ] * 2

    store = DuckDBStore(tmp_path / "ingestion.duckdb")
    service = RawMarketIngestionService(store, {"binance": FixtureAdapter()})
    first = asyncio.run(service.ingest("binance", "trades", "BTCUSDT", "spot"))
    second = asyncio.run(service.ingest("binance", "trades", "BTCUSDT", "spot"))
    assert first.records_received == 2
    assert first.records_written == 1
    assert first.records_duplicate == 1
    assert second.records_written == 0
    assert second.records_duplicate == 2
    assert (
        store.connection.execute("SELECT COUNT(*) FROM raw_trades").fetchone()[0] == 1
    )
    store.close()


def test_ingestion_service_rejects_crossed_orderbook_and_keeps_diagnostic(tmp_path):
    import asyncio
    from btc_intelligence.adapters import BinanceMarketDataAdapter
    from btc_intelligence.ingestion import RawMarketIngestionService

    class FixtureAdapter(BinanceMarketDataAdapter):
        async def get_orderbook(
            self, symbol="BTCUSDT", market_type="perpetual", depth=20
        ):
            return [
                self.normalize_orderbook(
                    {"bids": [["101", "1"]], "asks": [["100", "1"]]},
                    symbol,
                    market_type,
                )
            ]

    store = DuckDBStore(tmp_path / "invalid.duckdb")
    service = RawMarketIngestionService(store, {"binance": FixtureAdapter()})
    result = asyncio.run(service.ingest("binance", "orderbook", "BTCUSDT", "perpetual"))
    assert result.records_invalid == 1
    assert result.records_written == 0
    assert (
        store.connection.execute("SELECT COUNT(*) FROM raw_orderbook").fetchone()[0]
        == 0
    )
    assert (
        store.connection.execute("SELECT COUNT(*) FROM rejected_raw_events").fetchone()[
            0
        ]
        == 1
    )
    store.close()
