from btc_intelligence.websockets import parse_binance_message, parse_bybit_message


def test_binance_aggregate_trade_has_provenance_and_two_metrics():
    observations = parse_binance_message(
        {
            "e": "aggTrade",
            "E": 1700000000000,
            "s": "BTCUSDT",
            "a": 7,
            "p": "42000.1",
            "q": "0.25",
            "m": True,
        }
    )
    assert [item.metric for item in observations] == ["trade_price", "trade_volume"]
    assert observations[0].exchange == "binance"
    assert observations[0].source_timestamp_utc is not None
    assert observations[0].metadata["is_buyer_maker"] is True


def test_binance_combined_stream_is_unwrapped():
    observations = parse_binance_message(
        {
            "stream": "btcusdt@bookTicker",
            "data": {
                "e": "bookTicker",
                "E": 1700000000000,
                "s": "BTCUSDT",
                "b": "42000",
                "B": "1",
                "a": "42001",
                "A": "2",
            },
        }
    )
    assert [item.metric for item in observations] == [
        "best_bid_price",
        "best_ask_price",
    ]


def test_bybit_liquidation_is_not_claimed_as_private_liquidation_price():
    observations = parse_bybit_message(
        {
            "topic": "allLiquidation.BTCUSDT",
            "ts": 1700000000000,
            "data": [
                {
                    "s": "BTCUSDT",
                    "S": "Sell",
                    "p": "42000",
                    "v": "0.5",
                    "T": 1700000000000,
                }
            ],
        }
    )
    assert len(observations) == 1
    assert observations[0].metric == "liquidation_size"
    assert observations[0].metadata == {"side": "Sell", "price": "42000"}


def test_local_order_book_applies_snapshot_and_delta():
    from btc_intelligence.realtime import LocalOrderBook

    book = LocalOrderBook(depth=20, sequence_mode="contiguous")
    book.apply_snapshot([["100", "2"], ["99", "1"]], [["101", "3"]], sequence=10)
    assert book.best_bid == 100
    assert book.best_ask == 101
    assert book.spread == 1
    book.apply_delta([["100", "4"], ["98", "1"]], [["101", "0"]], sequence=11)
    assert book.bids[100] == 4
    assert 101 not in book.asks


def test_local_order_book_marks_sequence_gap_and_requires_resync():
    from btc_intelligence.realtime import LocalOrderBook

    book = LocalOrderBook(sequence_mode="contiguous")
    book.apply_snapshot([["100", "1"]], [["101", "1"]], sequence=10)
    assert book.apply_delta([["100", "2"]], [], sequence=12) is False
    assert book.is_valid is False
    assert book.sequence_gaps == 1


def test_okx_trade_and_delta_parsers_preserve_exchange_fields():
    from btc_intelligence.realtime import OKXWebSocketAdapter

    adapter = OKXWebSocketAdapter()
    trade = adapter.parse_message(
        {
            "arg": {"channel": "trades"},
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": "9",
                    "px": "42000",
                    "sz": "2",
                    "side": "buy",
                    "ts": "1700000000000",
                }
            ],
        }
    )[0]
    delta = adapter.parse_message(
        {
            "arg": {"channel": "books5"},
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "bids": [["42000", "2", "0", "1"]],
                    "asks": [["42001", "3", "0", "1"]],
                    "seqId": 11,
                    "prevSeqId": 10,
                    "ts": "1700000000000",
                }
            ],
        }
    )[0]
    assert trade.trade_id == "9"
    assert trade.aggressor_side == "buy"
    assert delta.sequence_id == 11
    assert delta.previous_sequence_id == 10


def test_binance_synchronizer_discards_stale_and_bridges_buffered_updates():
    from btc_intelligence.realtime import BinanceOrderBookSynchronizer

    synchronizer = BinanceOrderBookSynchronizer(max_buffer_events=10)
    synchronizer.buffer_update(
        {"U": 95, "u": 99, "b": [["100", "2"]], "a": [["101", "2"]]}
    )
    synchronizer.buffer_update({"U": 100, "u": 101, "b": [["100", "3"]], "a": []})
    synchronizer.buffer_update({"U": 102, "u": 103, "b": [], "a": [["101", "1"]]})
    assert (
        synchronizer.synchronize([["100", "1"]], [["101", "1"]], last_update_id=99)
        is True
    )
    assert synchronizer.state == "SYNCHRONIZED"
    assert synchronizer.book.last_sequence == 103
    assert synchronizer.book.bids[100] == 3


def test_binance_synchronizer_records_real_gap_not_overlap():
    from btc_intelligence.realtime import BinanceOrderBookSynchronizer

    synchronizer = BinanceOrderBookSynchronizer()
    synchronizer.synchronize([["100", "1"]], [["101", "1"]], last_update_id=100)
    assert synchronizer.apply_update({"U": 101, "u": 102, "b": [], "a": []}) is True
    assert synchronizer.apply_update({"U": 104, "u": 105, "b": [], "a": []}) is False
    assert synchronizer.state == "DESYNCHRONIZED"
    assert synchronizer.gap_diagnostics[-1]["expected"] == 103


def test_binance_futures_requires_pu_to_match_previous_u():
    from btc_intelligence.realtime import BinanceOrderBookSynchronizer

    synchronizer = BinanceOrderBookSynchronizer()
    synchronizer.synchronize([["100", "1"]], [["101", "1"]], last_update_id=100)
    assert (
        synchronizer.apply_update({"U": 101, "u": 102, "pu": 999, "b": [], "a": []})
        is False
    )
    assert synchronizer.state == "GAP"
    assert synchronizer.gap_diagnostics[-1]["received_pu"] == 999


def test_binance_futures_accepts_update_range_when_pu_matches_previous_u():
    from btc_intelligence.realtime import BinanceOrderBookSynchronizer

    synchronizer = BinanceOrderBookSynchronizer()
    synchronizer.synchronize([["100", "1"]], [["101", "1"]], last_update_id=100)
    assert (
        synchronizer.apply_update({"U": 150, "u": 160, "pu": 100, "b": [], "a": []})
        is True
    )
    assert synchronizer.book.last_sequence == 160
    assert synchronizer.classifications["gap"] == 0


def test_bounded_batch_writer_applies_backpressure_and_flushes():
    import asyncio
    from datetime import datetime, timezone
    from btc_intelligence.realtime import WebSocketEvent
    from btc_intelligence.realtime_writer import BoundedBatchWriter

    written = []

    async def write_batch(events):
        written.extend(events)

    async def exercise():
        writer = BoundedBatchWriter(
            write_batch, max_queue_size=2, batch_size=2, flush_interval_ms=10
        )
        await writer.start()
        event = WebSocketEvent(
            "okx",
            "trades",
            "BTCUSDT",
            "perpetual",
            datetime.now(timezone.utc),
            trade_id="1",
            price=100,
            quantity=1,
        )
        await writer.put(event)
        await writer.put(event)
        await writer.stop()
        return writer

    writer = asyncio.run(exercise())
    assert len(written) == 2
    assert writer.max_queue_seen <= 2
    assert writer.dropped_events == 0


def test_bounded_batch_writer_does_not_deadlock_after_batch_error():
    import asyncio
    from btc_intelligence.realtime import WebSocketEvent
    from btc_intelligence.realtime_writer import BoundedBatchWriter
    from datetime import datetime, timezone

    async def failing_batch(events):
        raise RuntimeError("fixture write failure")

    async def exercise():
        writer = BoundedBatchWriter(
            failing_batch, max_queue_size=2, batch_size=2, flush_interval_ms=10
        )
        await writer.start()
        event = WebSocketEvent(
            "binance",
            "trades",
            "BTCUSDT",
            "perpetual",
            datetime.now(timezone.utc),
            trade_id="1",
            price=100,
            quantity=1,
        )
        await writer.put(event)
        await writer.stop()
        return writer

    writer = asyncio.run(exercise())
    assert writer.batches_written == 0
    assert writer.write_errors == ["RuntimeError: fixture write failure"]


def test_websocket_delta_and_snapshot_storage_are_separate(tmp_path):
    from datetime import datetime, timezone
    from btc_intelligence.realtime import WebSocketEvent
    from btc_intelligence.storage import DuckDBStore

    store = DuckDBStore(tmp_path / "websocket.duckdb")
    event = WebSocketEvent(
        "okx",
        "orderbook",
        "BTCUSDT",
        "perpetual",
        datetime.now(timezone.utc),
        bids=((100.0, 2.0),),
        asks=((101.0, 3.0),),
        sequence_id=11,
        update_type="delta",
        raw_payload={"seqId": 11},
    )
    snapshot = WebSocketEvent(
        "okx",
        "orderbook",
        "BTCUSDT",
        "perpetual",
        event.event_timestamp,
        bids=((100.0, 2.0),),
        asks=((101.0, 3.0),),
        sequence_id=11,
        update_type="snapshot",
        raw_payload={"seqId": 11},
    )
    assert store.write_websocket_event(event, persist_snapshot=False) is True
    assert store.write_websocket_event(event, persist_snapshot=False) is False
    assert store.write_websocket_event(snapshot) is True
    assert (
        store.connection.execute(
            "SELECT COUNT(*) FROM raw_orderbook_updates"
        ).fetchone()[0]
        == 1
    )
    assert (
        store.connection.execute("SELECT COUNT(*) FROM raw_orderbook").fetchone()[0]
        == 2
    )
    store.close()
