#!/usr/bin/env python3
"""
Session Anomaly Detector (Layer 7 Security)
Wykrywa zaburzenia w normalnym przepływie sesji UDP.
"""

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AnomalyType(Enum):
    """Typy anomalii detektowane na warstwie aplikacji."""

    SEQUENCE_JUMP = "sequence_jump"  # Skok w numerach sekwencji
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"  # Brak heartbeat w oczekiwanym oknie
    SPOOFING_ATTEMPT = "spoofing_attempt"  # IP/token mismatch
    PROTOCOL_VIOLATION = "protocol_violation"  # Nieoczekiwane przejście stanu
    TOKEN_REUSE = "token_reuse"  # Odczyt starego tokenu
    FLOOD_DETECTION = "flood_detection"  # Zbyt wiele pakietów z jednego źródła


@dataclass
class AnomalyAlert:
    """Alert o wykrytej anomalii."""

    anomaly_type: AnomalyType
    session_id: str
    client_addr: tuple
    details: str
    timestamp: float


class SessionAnomalyDetector:
    """Detektor anomalii dla sesji UDP."""

    def __init__(self, window_size: int = 100, threshold_pps: int = 50):
        self.window_size = window_size
        self.threshold_pps = threshold_pps

        # Per-session state tracking
        self.session_states: dict[str, dict] = {}

    def track_session(self, session_id: str, client_addr: tuple, token: str):
        """Zarejestruj nową sesję."""
        self.session_states[session_id] = {
            "client_addr": client_addr,
            "token": token,
            "last_seq": 0,
            "last_heartbeat": time.monotonic(),
            "packet_history": deque(maxlen=self.window_size),
            "invalid_attempts": 0,
        }

    def record_packet(
        self, session_id: str, packet_type: str, seq: int = None
    ) -> list[AnomalyAlert]:
        """Zarejestruj pakiet i zwróć listę anomalii."""
        alerts = []

        if session_id not in self.session_states:
            return alerts

        state = self.session_states[session_id]
        now = time.monotonic()
        state["packet_history"].append(now)

        # Detekcja: sequence jump
        if seq is not None and seq != 0:
            if seq != state["last_seq"] + 1:
                # Wyjątek: ACK pakiety mogą mieć różne numery
                if packet_type not in ("HEARTBEAT_ACK", "DATA_ACK", "DISCONNECT_ACK"):
                    alerts.append(
                        AnomalyAlert(
                            anomaly_type=AnomalyType.SEQUENCE_JUMP,
                            session_id=session_id,
                            client_addr=state["client_addr"],
                            details=f"expected seq {state['last_seq'] + 1}, got {seq}",
                            timestamp=now,
                        )
                    )
            state["last_seq"] = seq

        # Detekcja: heartbeat timeout
        if packet_type == "HEARTBEAT":
            state["last_heartbeat"] = now
        else:
            heartbeat_timeout = now - state["last_heartbeat"]
            if heartbeat_timeout > 10.0:
                alerts.append(
                    AnomalyAlert(
                        anomaly_type=AnomalyType.HEARTBEAT_TIMEOUT,
                        session_id=session_id,
                        client_addr=state["client_addr"],
                        details=f"no heartbeat for {heartbeat_timeout:.1f}s",
                        timestamp=now,
                    )
                )

        # Detekcja: flood
        pps = self._calculate_pps(state["packet_history"], now)
        if pps > self.threshold_pps:
            alerts.append(
                AnomalyAlert(
                    anomaly_type=AnomalyType.FLOOD_DETECTION,
                    session_id=session_id,
                    client_addr=state["client_addr"],
                    details=f"packet rate {pps} PPS (threshold {self.threshold_pps})",
                    timestamp=now,
                )
            )

        return alerts

    def verify_session_integrity(
        self, session_id: str, expected_addr: tuple, expected_token: str
    ) -> Optional[AnomalyAlert]:
        """Weryfikacja integralności sesji (anti-spoofing)."""
        if session_id not in self.session_states:
            return None

        state = self.session_states[session_id]

        if state["client_addr"] != expected_addr:
            return AnomalyAlert(
                anomaly_type=AnomalyType.SPOOFING_ATTEMPT,
                session_id=session_id,
                client_addr=expected_addr,
                details=f"address mismatch: expected {state['client_addr']}, got {expected_addr}",
                timestamp=time.monotonic(),
            )

        if state["token"] != expected_token:
            state["invalid_attempts"] += 1
            return AnomalyAlert(
                anomaly_type=AnomalyType.TOKEN_REUSE,
                session_id=session_id,
                client_addr=expected_addr,
                details=f"invalid token attempt #{state['invalid_attempts']}",
                timestamp=time.monotonic(),
            )

        return None

    def close_session(self, session_id: str):
        """Usuń sesję z śledzenia."""
        if session_id in self.session_states:
            del self.session_states[session_id]

    @staticmethod
    def _calculate_pps(history: deque, now: float, window: float = 1.0) -> int:
        """Oblicz pakiety na sekundę z historii."""
        return sum(1 for t in history if t > now - window)


class ProtocolViolationDetector:
    """Detektor naruszeń protokołu (state machine)."""

    # Dozwolone przejścia stanów
    VALID_TRANSITIONS = {
        None: {"LOGIN"},
        "LOGIN": {"HEARTBEAT", "DATA", "DISCONNECT"},
        "HEARTBEAT": {"HEARTBEAT", "DATA", "DISCONNECT"},
        "DATA": {"HEARTBEAT", "DATA", "DISCONNECT"},
        "DISCONNECT": set(),  # brak przejść po disconnect
    }

    def __init__(self):
        self.session_states: dict[str, str] = {}

    def check_transition(
        self, session_id: str, packet_type: str
    ) -> Optional[AnomalyAlert]:
        """Sprawdzenie legalności przejścia."""
        current_state = self.session_states.get(session_id)

        if packet_type not in self.VALID_TRANSITIONS.get(current_state, set()):
            alert = AnomalyAlert(
                anomaly_type=AnomalyType.PROTOCOL_VIOLATION,
                session_id=session_id,
                client_addr=("0.0.0.0", 0),  # placeholder
                details=f"invalid transition {current_state} -> {packet_type}",
                timestamp=time.monotonic(),
            )
            return alert

        # Przejście jest legalne, aktualizuj stan
        if packet_type == "LOGIN":
            self.session_states[session_id] = "LOGIN"
        elif packet_type == "DISCONNECT":
            self.session_states[session_id] = "DISCONNECT"
        else:
            self.session_states[session_id] = packet_type

        return None

    def close_session(self, session_id: str):
        """Usuń sesję ze śledzenia."""
        if session_id in self.session_states:
            del self.session_states[session_id]


if __name__ == "__main__":
    print("[*] Session Anomaly Detection Module")

    detector = SessionAnomalyDetector(threshold_pps=10)
    pv_detector = ProtocolViolationDetector()

    # Test scenario
    session_id = "test-123"
    client_addr = ("127.0.0.1", 12345)
    token = "test-token"

    detector.track_session(session_id, client_addr, token)

    # Prawidłowe pakiety
    print("\n[TEST] Normal flow:")
    for seq in [1, 2, 3, 4]:
        alerts = detector.record_packet(session_id, "DATA", seq)
        viol = pv_detector.check_transition(session_id, "DATA")
        print(f"seq={seq}, alerts={len(alerts)}, violation={viol}")

    # Anomalia: skok sekwencji
    print("\n[TEST] Sequence anomaly:")
    alerts = detector.record_packet(session_id, "DATA", 10)
    print(f"seq=10 (expected 5), alerts={len(alerts)}")
    if alerts:
        print(f"  -> {alerts[0].details}")

    # Anomalia: naruszenie protokołu
    print("\n[TEST] Protocol violation:")
    viol = pv_detector.check_transition(session_id, "HEARTBEAT")
    print(f"transition DATA -> HEARTBEAT: violation={viol is None}")
