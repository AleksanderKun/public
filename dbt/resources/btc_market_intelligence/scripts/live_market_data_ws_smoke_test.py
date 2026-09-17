from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import replace
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx
import websockets

from btc_intelligence.realtime import (
    BinanceOrderBookSynchronizer,
    BinanceWebSocketAdapter,
    BybitWebSocketAdapter,
    LocalOrderBook,
    OKXWebSocketAdapter,
    WebSocketEvent,
)
from btc_intelligence.realtime_writer import BoundedBatchWriter
from btc_intelligence.storage import DuckDBStore


@dataclass
class StreamMetrics:
    exchange: str
    dataset: str
    connection_time: str | None = None
    first_event_time: str | None = None
    last_event_time: str | None = None
    events_received: int = 0
    events_written: int = 0
    duplicates: int = 0
    invalid: int = 0
    sequence_gaps: int = 0
    reconnects: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    snapshots: int = 0
    updates: int = 0
    book_resyncs: int = 0
    errors: list[str] = field(default_factory=list)
    exchange_event_to_receive_ms: list[float] = field(default_factory=list)
    queue_wait_ms: list[float] = field(default_factory=list)
    database_write_ms: list[float] = field(default_factory=list)
    total_local_processing_ms: list[float] = field(default_factory=list)
    event_to_db_commit_ms: list[float] = field(default_factory=list)
    received_updates: int = 0
    written_updates: int = 0
    generated_snapshots: int = 0
    written_snapshots: int = 0
    write_errors: int = 0

    def report(self) -> dict[str, Any]:
        def stats(values: list[float]) -> dict[str, float | None]:
            ordered = sorted(values)
            if not ordered:
                return {
                    "mean": None,
                    "median": None,
                    "p95": None,
                    "p99": None,
                    "max": None,
                }
            pick = lambda ratio: ordered[
                min(len(ordered) - 1, int(len(ordered) * ratio))
            ]
            return {
                "mean": round(sum(ordered) / len(ordered), 2),
                "median": round(pick(0.5), 2),
                "p95": round(pick(0.95), 2),
                "p99": round(pick(0.99), 2),
                "max": round(ordered[-1], 2),
            }

        return {
            **self.__dict__,
            "latencies_ms": None,
            "exchange_event_to_receive": stats(self.exchange_event_to_receive_ms),
            "queue_wait": stats(self.queue_wait_ms),
            "database_write": stats(self.database_write_ms),
            "total_local_processing": stats(self.total_local_processing_ms),
            "event_to_db_commit": stats(self.event_to_db_commit_ms),
            "exchange_event_to_receive_ms": None,
            "queue_wait_ms": None,
            "database_write_ms": None,
            "total_local_processing_ms": None,
            "event_to_db_commit_ms": None,
        }


async def bootstrap(
    exchange: str, symbol: str, market_type: str, depth: int
) -> tuple[list[list[str]], list[list[str]], int | None]:
    async with httpx.AsyncClient(timeout=10) as client:
        if exchange == "binance":
            base = (
                "https://fapi.binance.com/fapi/v1/depth"
                if market_type == "perpetual"
                else "https://api.binance.com/api/v3/depth"
            )
            response = await client.get(
                base, params={"symbol": symbol, "limit": min(depth, 100)}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("bids", []), data.get("asks", []), data.get("lastUpdateId")
        if exchange == "bybit":
            response = await client.get(
                "https://api.bybit.com/v5/market/orderbook",
                params={
                    "category": "linear",
                    "symbol": symbol,
                    "limit": min(depth, 200),
                },
            )
            data = response.json()["result"]
            return (
                data.get("b", []),
                data.get("a", []),
                int(data["u"]) if data.get("u") is not None else None,
            )
        inst_id = (
            f"{symbol[:-4]}-{symbol[-4:]}-SWAP"
            if market_type == "perpetual"
            else f"{symbol[:-4]}-{symbol[-4:]}"
        )
        response = await client.get(
            "https://www.okx.com/api/v5/market/books",
            params={"instId": inst_id, "sz": min(depth, 25)},
        )
        data = response.json()["data"][0]
        return (
            data.get("bids", []),
            data.get("asks", []),
            int(data["seqId"]) if data.get("seqId") is not None else None,
        )


async def run_stream(
    exchange: str, adapter: Any, store: DuckDBStore, duration: float, depth: int
) -> list[StreamMetrics]:
    metrics = {
        dataset: StreamMetrics(exchange, dataset)
        for dataset in ("trades", "orderbook", "liquidations")
    }
    book = LocalOrderBook(
        depth=depth, sequence_mode="binance" if exchange == "binance" else "monotonic"
    )
    synchronizer = (
        BinanceOrderBookSynchronizer(
            depth=depth, max_buffer_events=1000, max_buffer_age_seconds=30
        )
        if exchange == "binance"
        else None
    )
    bridge_found = 0
    bridge_failures = 0
    if synchronizer:
        book = synchronizer.book
    buffered_events: list[WebSocketEvent] = []

    async def write_batch(items):
        for event, persist_snapshot in items:
            metric = metrics[event.dataset]
            writer_started = time.monotonic()
            event = replace(
                event,
                writer_start_timestamp=datetime.now(timezone.utc),
                writer_start_monotonic=writer_started,
            )
            try:
                written = store.write_websocket_event(
                    event, persist_snapshot=persist_snapshot
                )
            except Exception as exc:
                metric.write_errors += 1
                metric.errors.append(f"database write: {type(exc).__name__}: {exc}")
                continue
            committed = time.monotonic()
            metric.queue_wait_ms.append(
                (writer_started - (event.queue_enter_monotonic or writer_started))
                * 1000
            )
            metric.database_write_ms.append((committed - writer_started) * 1000)
            if event.local_receive_monotonic is not None:
                metric.total_local_processing_ms.append(
                    (committed - event.local_receive_monotonic) * 1000
                )
            metric.event_to_db_commit_ms.append(
                (datetime.now(timezone.utc) - event.event_timestamp).total_seconds()
                * 1000
            )
            if written:
                metric.events_written += 1
                if event.dataset == "orderbook":
                    if persist_snapshot:
                        metric.written_snapshots += 1
                    else:
                        metric.written_updates += 1
            else:
                metric.duplicates += 1

    writer = BoundedBatchWriter(
        write_batch, max_queue_size=1000, batch_size=100, flush_interval_ms=250
    )
    await writer.start()
    try:
        if exchange == "binance":
            snapshot_data = None
        else:
            snapshot_data = await bootstrap(
                exchange, adapter.symbol, adapter.market_type, depth
            )
        if snapshot_data:
            bids, asks, sequence = snapshot_data
            book.apply_snapshot(bids, asks, sequence)
            metrics["orderbook"].snapshots += 1
    except Exception as exc:
        metrics["orderbook"].errors.append(f"bootstrap: {type(exc).__name__}: {exc}")
    deadline = time.monotonic() + duration
    delay = 1.0
    while time.monotonic() < deadline:
        try:
            metrics["trades"].connection_time = (
                metrics["trades"].connection_time
                or datetime.now(timezone.utc).isoformat()
            )
            if synchronizer:
                synchronizer._set_state("CONNECTING", "websocket connection opened")
            async with websockets.connect(
                adapter.uri,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as connection:
                subscription = adapter.subscribe_message()
                if subscription:
                    await connection.send(json.dumps(subscription))
                snapshot_task = None
                if synchronizer:
                    synchronizer._set_state(
                        "BUFFERING", "depth buffering started before REST snapshot"
                    )
                    synchronizer._set_state("SNAPSHOT_REQUEST", "initial_sync")
                    snapshot_task = asyncio.create_task(
                        bootstrap(exchange, adapter.symbol, adapter.market_type, depth)
                    )
                delay = 1.0
                while time.monotonic() < deadline:
                    try:
                        raw = await asyncio.wait_for(connection.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        await connection.send("ping")
                        continue
                    except websockets.exceptions.ConnectionClosed as exc:
                        metrics["trades"].errors.append(
                            f"socket closed: code={exc.code} reason={exc.reason}"
                        )
                        break
                    if isinstance(raw, bytes):
                        raw = raw.decode()
                    if raw == "ping":
                        await connection.send("pong")
                        continue
                    try:
                        events = adapter.parse_message(json.loads(raw))
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        metrics["trades"].invalid += 1
                        metrics["trades"].errors.append(
                            f"malformed message: {type(exc).__name__}: {exc}"
                        )
                        continue
                    for event in events:
                        metric = metrics[event.dataset]
                        metric.events_received += 1
                        now = datetime.now(timezone.utc)
                        received_monotonic = time.monotonic()
                        event = replace(
                            event,
                            local_receive_timestamp=now,
                            normalized_timestamp=now,
                            local_receive_monotonic=received_monotonic,
                        )
                        metric.first_event_time = (
                            metric.first_event_time or now.isoformat()
                        )
                        metric.last_event_time = now.isoformat()
                        exchange_lag_ms = (
                            now - event.event_timestamp
                        ).total_seconds() * 1000
                        metric.latencies_ms.append(exchange_lag_ms)
                        metric.exchange_event_to_receive_ms.append(exchange_lag_ms)
                        if event.dataset == "orderbook":
                            if synchronizer and synchronizer.state != "SYNCHRONIZED":
                                buffered_events.append(event)
                                synchronizer.buffer_update(event.raw_payload)
                                if snapshot_task and snapshot_task.done():
                                    try:
                                        (
                                            fresh_bids,
                                            fresh_asks,
                                            fresh_sequence,
                                        ) = snapshot_task.result()
                                        synchronized = synchronizer.synchronize(
                                            fresh_bids, fresh_asks, fresh_sequence
                                        )
                                        if synchronized:
                                            metrics["orderbook"].snapshots += 1
                                        if (
                                            synchronized
                                            and synchronizer.state == "SYNCHRONIZED"
                                        ):
                                            bridge_found += 1
                                            for buffered_event in buffered_events:
                                                if (
                                                    fresh_sequence is not None
                                                    and int(
                                                        buffered_event.raw_payload.get(
                                                            "u", -1
                                                        )
                                                    )
                                                    > fresh_sequence
                                                ):
                                                    await writer.put(
                                                        (buffered_event, False)
                                                    )
                                            buffered_events.clear()
                                        elif not synchronized:
                                            max_buffered_u = synchronizer.last_buffer_diagnostics.get(
                                                "max_u"
                                            )
                                            if (
                                                max_buffered_u is not None
                                                and fresh_sequence is not None
                                                and max_buffered_u <= fresh_sequence
                                            ):
                                                synchronizer._set_state(
                                                    "BUFFERING",
                                                    "all buffered updates stale; waiting for post-snapshot bridge",
                                                )
                                            else:
                                                bridge_failures += 1
                                                metrics["orderbook"].errors.append(
                                                    "bridge failure: post-snapshot updates did not contain a valid Binance bridge"
                                                )
                                                synchronizer.buffer.clear()
                                                buffered_events.clear()
                                                synchronizer._set_state(
                                                    "RESYNCING", "bridge_failure"
                                                )
                                                snapshot_task = asyncio.create_task(
                                                    bootstrap(
                                                        exchange,
                                                        adapter.symbol,
                                                        adapter.market_type,
                                                        depth,
                                                    )
                                                )
                                    except Exception as exc:
                                        synchronizer._set_state(
                                            "FAILED",
                                            f"snapshot failure: {type(exc).__name__}",
                                        )
                                        metric.errors.append(
                                            f"snapshot: {type(exc).__name__}: {exc}"
                                        )
                                continue
                            if synchronizer:
                                previous_u = synchronizer.book.last_sequence
                                if not synchronizer.apply_update(event.raw_payload):
                                    metric.sequence_gaps += 1
                                    synchronizer._set_state("RESYNCING", "sequence_gap")
                                    buffered_events.clear()
                                    snapshot_task = asyncio.create_task(
                                        bootstrap(
                                            exchange,
                                            adapter.symbol,
                                            adapter.market_type,
                                            depth,
                                        )
                                    )
                                    synchronizer.buffer_update(event.raw_payload)
                                    continue
                                if (
                                    previous_u is not None
                                    and int(event.raw_payload.get("u", -1))
                                    <= previous_u
                                ):
                                    metric.duplicates += 1
                                    continue
                                metric.updates += 1
                                metric.received_updates += 1
                                if book.is_valid:
                                    event = replace(
                                        event,
                                        queue_enter_timestamp=datetime.now(
                                            timezone.utc
                                        ),
                                        queue_enter_monotonic=time.monotonic(),
                                    )
                                    await writer.put((event, False))
                                if book.is_valid and metric.updates % 10 == 0:
                                    snapshot = WebSocketEvent(
                                        exchange,
                                        "orderbook",
                                        event.symbol,
                                        event.market_type,
                                        event.event_timestamp,
                                        bids=tuple(book.bids.items()),
                                        asks=tuple(book.asks.items()),
                                        sequence_id=book.last_sequence,
                                        update_type="snapshot",
                                        raw_payload=event.raw_payload,
                                    )
                                    metric.generated_snapshots += 1
                                    snapshot = replace(
                                        snapshot,
                                        local_receive_timestamp=event.local_receive_timestamp,
                                        local_receive_monotonic=event.local_receive_monotonic,
                                        queue_enter_timestamp=datetime.now(
                                            timezone.utc
                                        ),
                                        queue_enter_monotonic=time.monotonic(),
                                    )
                                    await writer.put((snapshot, True))
                                continue
                            if event.update_type == "snapshot":
                                book.apply_snapshot(
                                    [[str(p), str(q)] for p, q in event.bids],
                                    [[str(p), str(q)] for p, q in event.asks],
                                    event.sequence_id,
                                )
                                metric.snapshots += 1
                            elif not book.apply_delta(
                                [[str(p), str(q)] for p, q in event.bids],
                                [[str(p), str(q)] for p, q in event.asks],
                                event.sequence_id,
                                event.previous_sequence_id,
                                event.first_sequence_id,
                            ):
                                metric.sequence_gaps += 1
                                try:
                                    (
                                        fresh_bids,
                                        fresh_asks,
                                        fresh_sequence,
                                    ) = await bootstrap(
                                        exchange,
                                        adapter.symbol,
                                        adapter.market_type,
                                        depth,
                                    )
                                    book.resync(fresh_bids, fresh_asks, fresh_sequence)
                                    metric.book_resyncs += 1
                                except Exception as exc:
                                    metric.errors.append(
                                        f"resync: {type(exc).__name__}: {exc}"
                                    )
                                    continue
                            metric.updates += 1
                            metric.received_updates += 1
                            if book.is_valid:
                                event = replace(
                                    event,
                                    queue_enter_timestamp=datetime.now(timezone.utc),
                                    queue_enter_monotonic=time.monotonic(),
                                )
                                await writer.put((event, False))
                            if book.is_valid and metric.updates % 10 == 0:
                                snapshot = WebSocketEvent(
                                    exchange,
                                    "orderbook",
                                    event.symbol,
                                    event.market_type,
                                    event.event_timestamp,
                                    bids=tuple(book.bids.items()),
                                    asks=tuple(book.asks.items()),
                                    sequence_id=book.last_sequence,
                                    update_type="snapshot",
                                    raw_payload=event.raw_payload,
                                )
                                metric.generated_snapshots += 1
                                snapshot = replace(
                                    snapshot,
                                    local_receive_timestamp=event.local_receive_timestamp,
                                    local_receive_monotonic=event.local_receive_monotonic,
                                    queue_enter_timestamp=datetime.now(timezone.utc),
                                    queue_enter_monotonic=time.monotonic(),
                                )
                                await writer.put((snapshot, True))
                        elif event.dataset == "liquidations" and event.price is None:
                            metric.invalid += 1
                        else:
                            event = replace(
                                event,
                                queue_enter_timestamp=datetime.now(timezone.utc),
                                queue_enter_monotonic=time.monotonic(),
                            )
                            await writer.put((event, True))
            if synchronizer and snapshot_task and not snapshot_task.done():
                try:
                    await asyncio.wait_for(snapshot_task, timeout=5)
                except Exception as exc:
                    metrics["orderbook"].errors.append(
                        f"snapshot completion: {type(exc).__name__}: {exc}"
                    )
            if (
                synchronizer
                and snapshot_task
                and snapshot_task.done()
                and buffered_events
                and synchronizer.state != "SYNCHRONIZED"
            ):
                try:
                    fresh_bids, fresh_asks, fresh_sequence = snapshot_task.result()
                    if synchronizer.synchronize(fresh_bids, fresh_asks, fresh_sequence):
                        metrics["orderbook"].snapshots += 1
                        bridge_found += 1
                        for buffered_event in buffered_events:
                            if (
                                fresh_sequence is not None
                                and int(buffered_event.raw_payload.get("u", -1))
                                > fresh_sequence
                            ):
                                await writer.put((buffered_event, False))
                        buffered_events.clear()
                except Exception as exc:
                    metrics["orderbook"].errors.append(
                        f"final bridge: {type(exc).__name__}: {exc}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for metric in metrics.values():
                metric.reconnects += 1
            metrics["trades"].errors.append(f"connection: {type(exc).__name__}: {exc}")
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(delay * 2, 30.0)
    if "snapshot_task" in locals() and snapshot_task and not snapshot_task.done():
        snapshot_task.cancel()
        await asyncio.gather(snapshot_task, return_exceptions=True)
    elif (
        "snapshot_task" in locals()
        and snapshot_task
        and snapshot_task.done()
        and not snapshot_task.cancelled()
    ):
        try:
            snapshot_task.exception()
        except Exception as exc:
            metrics["orderbook"].errors.append(
                f"snapshot task: {type(exc).__name__}: {exc}"
            )
    await writer.stop()
    for metric in metrics.values():
        metric.queue_max_seen = writer.max_queue_seen
        metric.dropped_events = writer.dropped_events
        metric.database_write_batches = writer.batches_written
    if synchronizer:
        metrics["orderbook"].bridge_found = bridge_found
        metrics["orderbook"].bridge_failures = bridge_failures
        metrics["orderbook"].synchronizer_state = synchronizer.state
        metrics["orderbook"].synchronizer_classifications = synchronizer.classifications
        metrics["orderbook"].state_transitions = synchronizer.state_transitions
        metrics["orderbook"].gap_diagnostics = synchronizer.gap_diagnostics
        metrics[
            "orderbook"
        ].snapshot_last_update_id = synchronizer.snapshot_last_update_id
        metrics[
            "orderbook"
        ].last_buffer_diagnostics = synchronizer.last_buffer_diagnostics
    return list(metrics.values())


async def main() -> int:
    duration = float(os.getenv("BTC_MI_WS_SMOKE_SECONDS", "60"))
    database = Path(
        os.getenv(
            "BTC_MI_DATABASE_PATH",
            str(ROOT / "data" / "btc_market_intelligence" / "ws_smoke.duckdb"),
        )
    )
    report_path = Path(
        os.getenv("BTC_MI_WS_REPORT_PATH", str(database.with_suffix(".json")))
    )
    store = DuckDBStore(database)
    mode = os.getenv("BTC_MI_WS_MODE", "all")
    adapters = (
        [
            (
                "binance",
                BinanceWebSocketAdapter("BTCUSDT", "perpetual", channel="orderbook"),
            )
        ]
        if mode == "binance_depth"
        else [
            (
                "binance",
                BinanceWebSocketAdapter("BTCUSDT", "perpetual", channel="trades"),
            ),
            (
                "binance",
                BinanceWebSocketAdapter("BTCUSDT", "perpetual", channel="orderbook"),
            ),
        ]
        if mode == "binance_all"
        else [
            (
                "binance",
                BinanceWebSocketAdapter("BTCUSDT", "perpetual", channel="trades"),
            ),
            (
                "binance",
                BinanceWebSocketAdapter("BTCUSDT", "perpetual", channel="orderbook"),
            ),
            ("bybit", BybitWebSocketAdapter("BTCUSDT", "perpetual")),
            ("okx", OKXWebSocketAdapter("BTCUSDT", "perpetual")),
        ]
    )
    try:
        try:
            groups = await asyncio.gather(
                *(
                    run_stream(exchange, adapter, store, duration, 20)
                    for exchange, adapter in adapters
                )
            )
        except Exception as exc:
            report_path.write_text(
                json.dumps(
                    {
                        "status": "ERROR",
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise
        reports = [
            metric.report()
            for (exchange, adapter), group in zip(adapters, groups)
            for metric in group
            if getattr(adapter, "channel", "both") == "both"
            or metric.dataset == getattr(adapter, "channel", metric.dataset)
        ]
        report_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(
            "EXCHANGE | DATASET | RECEIVED | WRITTEN | DUPLICATES | INVALID | GAPS | RECONNECTS | AVG_LAG_MS | P95_LAG_MS | RESYNCS"
        )
        for item in reports:
            lag = item["exchange_event_to_receive"]
            print(
                f"{item['exchange'].upper()} | {item['dataset']} | {item['events_received']} | {item['events_written']} | {item['duplicates']} | {item['invalid']} | {item['sequence_gaps']} | {item['reconnects']} | {lag['mean']} | {lag['p95']} | {item['book_resyncs']}"
            )
        critical = [
            item
            for item in reports
            if item["dataset"] in {"trades", "orderbook"}
            and item["events_received"] == 0
        ]
        return (
            1
            if len(critical)
            == len(
                [item for item in reports if item["dataset"] in {"trades", "orderbook"}]
            )
            else 0
        )
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
