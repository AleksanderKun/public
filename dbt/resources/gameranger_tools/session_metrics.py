#!/usr/bin/env python3
"""
Session Metrics Collector (Telemetry & Diagnostics)
Zbiera metryki warstwy aplikacji do badania wydajności i anomalii.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionMetrics:
    """Metryki jednej sesji."""

    session_id: str
    client_addr: tuple
    created_at: float

    # Liczniki
    packets_sent: int = 0
    packets_received: int = 0
    packets_lost: int = 0
    errors: int = 0

    # Opóźnienia
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    last_rtt: float = None

    # Sekwencje
    last_seq_sent: int = 0
    last_seq_received: int = 0
    seq_gaps: list[tuple[int, int]] = field(default_factory=list)

    # Stany
    last_packet_time: float = field(default_factory=time.monotonic)
    total_data_bytes: int = 0

    def duration(self) -> float:
        """Czas trwania sesji."""
        return time.monotonic() - self.created_at

    def packet_loss_rate(self) -> float:
        """Procent utraconego ruchu."""
        total = self.packets_sent + self.packets_lost
        return (self.packets_lost / total * 100) if total > 0 else 0.0

    def avg_latency(self) -> float:
        """Średnia latencja."""
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def jitter(self) -> float:
        """Zmienność latencji (odchylenie standardowe)."""
        if len(self.latencies) < 2:
            return 0.0
        avg = self.avg_latency()
        variance = sum((x - avg) ** 2 for x in self.latencies) / len(self.latencies)
        return variance**0.5

    def throughput_mbps(self) -> float:
        """Przepustowość w Mbps."""
        duration = self.duration()
        if duration < 0.001:
            return 0.0
        return (self.total_data_bytes * 8) / (duration * 1_000_000)

    def pps(self) -> float:
        """Pakiety na sekundę."""
        duration = self.duration()
        total_packets = self.packets_sent + self.packets_received
        return total_packets / duration if duration > 0 else 0.0


class MetricsCollector:
    """Kolektor metryk dla wielu sesji."""

    def __init__(self):
        self.metrics: dict[str, SessionMetrics] = {}

    def create_session(self, session_id: str, client_addr: tuple):
        """Stwórz nowy obiekt metryk."""
        self.metrics[session_id] = SessionMetrics(
            session_id=session_id, client_addr=client_addr, created_at=time.monotonic()
        )

    def record_sent(
        self, session_id: str, payload_size: int, seq: Optional[int] = None
    ):
        """Zanotuj wysłany pakiet."""
        if session_id not in self.metrics:
            return

        m = self.metrics[session_id]
        m.packets_sent += 1
        m.total_data_bytes += payload_size
        m.last_packet_time = time.monotonic()
        if seq is not None:
            m.last_seq_sent = seq

    def record_received(
        self,
        session_id: str,
        payload_size: int,
        seq: Optional[int] = None,
        latency: Optional[float] = None,
    ):
        """Zanotuj odebrany pakiet."""
        if session_id not in self.metrics:
            return

        m = self.metrics[session_id]
        m.packets_received += 1
        m.total_data_bytes += payload_size
        m.last_packet_time = time.monotonic()

        if seq is not None:
            # Detekcja luk w sekwencji
            if m.last_seq_received > 0 and seq != m.last_seq_received + 1:
                gap_start = m.last_seq_received + 1
                gap_end = seq - 1
                m.seq_gaps.append((gap_start, gap_end))
                m.packets_lost += gap_end - gap_start + 1
            m.last_seq_received = seq

        if latency is not None:
            m.latencies.append(latency)
            m.last_rtt = latency

    def record_error(self, session_id: str):
        """Zanotuj błąd."""
        if session_id in self.metrics:
            self.metrics[session_id].errors += 1

    def get_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """Pobierz metryki sesji."""
        return self.metrics.get(session_id)

    def remove_session(self, session_id: str):
        """Usuń sesję."""
        if session_id in self.metrics:
            del self.metrics[session_id]

    def get_all_metrics(self) -> dict[str, SessionMetrics]:
        """Pobierz metryki wszystkich sesji."""
        return dict(self.metrics)


class MetricsFormatter:
    """Formatowanie metryk do raportu."""

    @staticmethod
    def format_session_summary(metrics: SessionMetrics) -> str:
        """Podsumowanie sesji."""
        lines = [
            f"Session: {metrics.session_id}",
            f"Client: {metrics.client_addr}",
            f"Duration: {metrics.duration():.2f}s",
            f"Packets sent/rcv: {metrics.packets_sent}/{metrics.packets_received}",
            f"Packet loss: {metrics.packet_loss_rate():.2f}%",
            f"Avg RTT: {metrics.last_rtt or 0:.4f}s",
            f"Jitter: {metrics.jitter():.4f}s",
            f"Throughput: {metrics.throughput_mbps():.2f} Mbps",
            f"Packet rate: {metrics.pps():.2f} PPS",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_all_metrics(collector: MetricsCollector) -> str:
        """Raport ze wszystkich sesji."""
        lines = ["=" * 60, "SESSION METRICS REPORT", "=" * 60]

        for session_id, metrics in collector.get_all_metrics().items():
            lines.append(MetricsFormatter.format_session_summary(metrics))
            lines.append("-" * 60)

        return "\n".join(lines)


if __name__ == "__main__":
    print("[*] Session Metrics Collection Module")

    collector = MetricsCollector()
    collector.create_session("test-123", ("127.0.0.1", 12345))

    # Symulacja przesyłu
    for i in range(10):
        collector.record_sent("test-123", 500, seq=i)
        time.sleep(0.1)
        collector.record_received(
            "test-123", 50, seq=i, latency=0.05 + (0.01 * (i % 2))
        )

    metrics = collector.get_metrics("test-123")
    print("\n" + MetricsFormatter.format_session_summary(metrics))
