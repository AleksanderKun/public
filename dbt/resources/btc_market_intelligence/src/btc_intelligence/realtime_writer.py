from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any


class BoundedBatchWriter:
    def __init__(self, write_batch: Callable[[list[Any]], Awaitable[None]], max_queue_size: int = 1000, batch_size: int = 100, flush_interval_ms: int = 250):
        self.write_batch = write_batch
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        self.batch_size = batch_size
        self.flush_interval = flush_interval_ms / 1000
        self.max_queue_seen = 0
        self.dropped_events = 0
        self.batches_written = 0
        self.write_durations_ms: list[float] = []
        self.write_errors: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def put(self, event: Any) -> None:
        await self.queue.put(event)
        self.max_queue_seen = max(self.max_queue_seen, self.queue.qsize())

    async def stop(self) -> None:
        self._stopping = True
        await self.queue.join()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stopping or not self.queue.empty():
            batch: list[Any] = []
            try:
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval))
            except asyncio.TimeoutError:
                continue
            while len(batch) < self.batch_size and not self.queue.empty():
                batch.append(self.queue.get_nowait())
            started = perf_counter()
            try:
                await self.write_batch(batch)
                self.batches_written += 1
            except Exception as exc:
                self.write_errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                self.write_durations_ms.append((perf_counter() - started) * 1000)
                for _ in batch:
                    self.queue.task_done()