from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import websockets

URL = os.getenv(
    "BINANCE_WS_PROBE_URL", "wss://fstream.binance.com/ws/btcusdt@depth@100ms"
)
DURATION_SECONDS = float(os.getenv("BINANCE_WS_PROBE_SECONDS", "60"))
REPORT_PATH = Path(
    os.getenv(
        "BINANCE_WS_PROBE_REPORT",
        "dbt/resources/btc_market_intelligence/data/binance_ws_minimal_probe.json",
    )
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def main() -> int:
    started_wall = utc_now()
    started_mono = time.monotonic()
    messages: list[dict[str, object]] = []
    first_raw: str | None = None
    close_code: int | None = None
    close_reason: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    message_sizes: list[int] = []
    try:
        async with websockets.connect(
            URL, open_timeout=10, ping_interval=20, ping_timeout=20, close_timeout=5
        ) as connection:
            connected_wall = utc_now()
            deadline = time.monotonic() + DURATION_SECONDS
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        connection.recv(),
                        timeout=min(30, max(0.1, deadline - time.monotonic())),
                    )
                except asyncio.TimeoutError:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                received_wall = utc_now()
                received_mono = time.monotonic()
                message_sizes.append(len(raw))
                if first_raw is None:
                    first_raw = raw
                if len(messages) < 10:
                    messages.append(
                        {
                            "received_utc": received_wall,
                            "monotonic_ns": time.monotonic_ns(),
                            "size_bytes": len(raw),
                            "raw": raw,
                        }
                    )
            connection_age_seconds = time.monotonic() - started_mono
            report = {
                "status": "COMPLETED_DURATION",
                "endpoint": URL,
                "stream": "btcusdt@depth@100ms",
                "connection_started_utc": started_wall,
                "connected_utc": connected_wall,
                "connection_age_seconds": round(connection_age_seconds, 3),
                "messages_received": len(message_sizes),
                "message_size_bytes": {
                    "min": min(message_sizes) if message_sizes else None,
                    "max": max(message_sizes) if message_sizes else None,
                    "mean": round(sum(message_sizes) / len(message_sizes), 2)
                    if message_sizes
                    else None,
                },
                "first_message_received_utc": messages[0]["received_utc"]
                if messages
                else None,
                "first_raw_message": first_raw,
                "representative_messages": messages,
                "close_code": close_code,
                "close_reason": close_reason,
                "exception_type": exception_type,
                "exception_message": exception_message,
                "reconnect_count": 0,
                "websockets_version": getattr(websockets, "__version__", "unknown"),
                "python_version": sys.version,
                "platform": platform.platform(),
            }
    except websockets.exceptions.ConnectionClosed as exc:
        close_code = exc.code
        close_reason = exc.reason
        report = {
            "status": "CLOSED_BEFORE_DURATION",
            "endpoint": URL,
            "stream": "btcusdt@depth@100ms",
            "connection_started_utc": started_wall,
            "connection_age_seconds": round(time.monotonic() - started_mono, 3),
            "messages_received": len(message_sizes),
            "message_size_bytes": {
                "min": min(message_sizes) if message_sizes else None,
                "max": max(message_sizes) if message_sizes else None,
                "mean": round(sum(message_sizes) / len(message_sizes), 2)
                if message_sizes
                else None,
            },
            "first_message_received_utc": messages[0]["received_utc"]
            if messages
            else None,
            "first_raw_message": first_raw,
            "representative_messages": messages,
            "close_code": close_code,
            "close_reason": close_reason,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "reconnect_count": 0,
            "websockets_version": getattr(websockets, "__version__", "unknown"),
            "python_version": sys.version,
            "platform": platform.platform(),
        }
    except Exception as exc:
        exception_type = type(exc).__name__
        exception_message = str(exc)
        report = {
            "status": "ERROR",
            "endpoint": URL,
            "stream": "btcusdt@depth@100ms",
            "connection_started_utc": started_wall,
            "connection_age_seconds": round(time.monotonic() - started_mono, 3),
            "messages_received": len(message_sizes),
            "message_size_bytes": {
                "min": min(message_sizes) if message_sizes else None,
                "max": max(message_sizes) if message_sizes else None,
                "mean": round(sum(message_sizes) / len(message_sizes), 2)
                if message_sizes
                else None,
            },
            "first_message_received_utc": messages[0]["received_utc"]
            if messages
            else None,
            "first_raw_message": first_raw,
            "representative_messages": messages,
            "close_code": close_code,
            "close_reason": close_reason,
            "exception_type": exception_type,
            "exception_message": exception_message,
            "reconnect_count": 0,
            "websockets_version": getattr(websockets, "__version__", "unknown"),
            "python_version": sys.version,
            "platform": platform.platform(),
        }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "endpoint",
                    "connection_age_seconds",
                    "messages_received",
                    "close_code",
                    "close_reason",
                    "exception_type",
                    "exception_message",
                    "reconnect_count",
                )
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "COMPLETED_DURATION" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
