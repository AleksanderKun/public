#!/usr/bin/env python3
"""
UDP Session Protocol (Layer 7 - Application Layer)
Educational implementation showing proper session management with authentication.
Author: CyberSecurity Research
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class SessionPacket:
    """Strukturalnie poprawny pakiet UDP warstwy aplikacji."""

    packet_type: str  # LOGIN, LOGIN_ACK, HEARTBEAT, HEARTBEAT_ACK, DATA, DISCONNECT, ERROR
    session_id: Optional[str] = None
    token: Optional[str] = None
    seq: Optional[int] = None
    timestamp: Optional[float] = None
    payload: Optional[str] = None

    def to_json(self) -> bytes:
        """Konwersja do JSON (transport format)."""
        return json.dumps(asdict(self)).encode("utf-8")

    @staticmethod
    def from_json(data: bytes) -> Optional["SessionPacket"]:
        """Parsowanie z JSON."""
        try:
            obj = json.loads(data.decode("utf-8"))
            return SessionPacket(**obj)
        except (ValueError, UnicodeDecodeError, TypeError):
            return None


@dataclass
class Session:
    """Stan sesji serwera."""

    session_id: str
    token: str
    client_addr: tuple
    created_at: float
    last_seen: float
    expected_seq: int = 1
    state: str = "active"  # active, idle, closed

    def is_expired(self, timeout: float) -> bool:
        """Sprawdzenie, czy sesja wygasła z powodu braku heartbeat."""
        return time.monotonic() - self.last_seen > timeout

    def refresh(self):
        """Reset timera ostatnio widzianej aktywności."""
        self.last_seen = time.monotonic()


class SessionValidator:
    """Walidacja pakietów na podstawie stanu sesji."""

    @staticmethod
    def validate_packet(
        packet: SessionPacket,
        session: Optional[Session],
        client_addr: tuple,
        allow_login: bool = False,
    ) -> tuple[bool, str]:
        """
        Zwraca: (is_valid, reason)
        """

        # LOGIN jest wyjątkiem - nie wymaga sesji
        if packet.packet_type == "LOGIN":
            if allow_login and packet.timestamp:
                return True, "LOGIN accepted"
            return False, "LOGIN not allowed or missing timestamp"

        # Wszystkie inne pakiety wymagają sesji
        if session is None:
            return False, f"{packet.packet_type} requires active session"

        # Weryfikacja adresu (anti-spoofing)
        if session.client_addr != client_addr:
            return False, "client address mismatch (possible spoofing)"

        # Weryfikacja tokenu
        if packet.token != session.token:
            return False, "invalid session token"

        # Weryfikacja session_id
        if packet.session_id != session.session_id:
            return False, "invalid session_id"

        # Weryfikacja numeru sekwencji dla DATA/DISCONNECT
        if packet.packet_type in ("DATA", "DISCONNECT"):
            if packet.seq != session.expected_seq:
                return (
                    False,
                    f"sequence mismatch: expected {session.expected_seq}, got {packet.seq}",
                )

        return True, "packet valid"


class ProtocolConstants:
    """Stałe protokołu edukacyjnego."""

    # Timeout dla sesji (w sekundach)
    SESSION_TIMEOUT = 10.0

    # Interwał heartbeat dla klienta (rekomendacja)
    HEARTBEAT_INTERVAL = 2.0

    # Maksymalna długość payloadu
    MAX_PAYLOAD_SIZE = 1024

    # Maksymalna liczba sekwencji (rollover safe)
    MAX_SEQUENCE = 2**31 - 1

    # Kody błędów
    ERROR_INVALID_SESSION = "invalid_session"
    ERROR_INVALID_TOKEN = "invalid_token"
    ERROR_SEQUENCE_MISMATCH = "sequence_mismatch"
    ERROR_SPOOFING = "spoofing_detected"
    ERROR_PROTOCOL = "protocol_error"


if __name__ == "__main__":
    # Test struktury
    print("[*] Session Protocol Educational Module")
    print(f"[*] Constants: SESSION_TIMEOUT={ProtocolConstants.SESSION_TIMEOUT}s")

    # Test pakietu
    pkt = SessionPacket(packet_type="LOGIN", timestamp=time.monotonic())
    print(f"[*] LOGIN packet: {pkt.to_json()}")

    # Test walidacji
    session = Session(
        session_id="test-123",
        token="test-token",
        client_addr=("127.0.0.1", 12345),
        created_at=time.monotonic(),
        last_seen=time.monotonic(),
    )

    valid_pkt = SessionPacket(
        packet_type="HEARTBEAT",
        session_id="test-123",
        token="test-token",
        seq=1,
        timestamp=time.monotonic(),
    )

    is_valid, reason = SessionValidator.validate_packet(
        valid_pkt, session, ("127.0.0.1", 12345)
    )
    print(f"[*] Validation: valid={is_valid}, reason={reason}")
