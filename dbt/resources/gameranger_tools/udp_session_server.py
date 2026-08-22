#!/usr/bin/env python3
"""
UDP Session Server (Educational Reference Implementation)
Demonstruje prawidłowe zarządzanie sesją, autentykację i ochronę przed atakami.
"""

import socket
import threading
import time
from session_protocol import (
    SessionPacket,
    Session,
    SessionValidator,
    ProtocolConstants,
)


class UdpSessionServer:
    """Serwer obsługujący sesje UDP z autoryzacją."""

    def __init__(self, host: str = "178.223.86.114", port: int = 16000):
        self.address = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.address)

        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()
        self.running = True

        print(f"[SERVER] listening on {host}:{port}")
        print(f"[SERVER] session timeout: {ProtocolConstants.SESSION_TIMEOUT}s")

    def start(self):
        """Uruchom serwer z wątkiem czyszczenia sesji."""
        cleaner = threading.Thread(target=self._cleanup_thread, daemon=True)
        cleaner.start()

        try:
            self._receive_loop()
        except KeyboardInterrupt:
            print("[SERVER] shutting down...")
            self.running = False

    def _cleanup_thread(self):
        """Periodic cleanup of expired sessions."""
        while self.running:
            time.sleep(1.0)
            now = time.monotonic()

            with self.lock:
                expired = [
                    sid
                    for sid, session in self.sessions.items()
                    if session.is_expired(ProtocolConstants.SESSION_TIMEOUT)
                ]

                for sid in expired:
                    print(f"[SERVER] session expired: {sid}")
                    del self.sessions[sid]

    def _receive_loop(self):
        """Main receive loop."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = SessionPacket.from_json(data)

                if packet is None:
                    print(f"[SERVER] malformed packet from {addr}")
                    continue

                self._handle_packet(packet, addr)

            except Exception as e:
                print(f"[SERVER] error in receive: {e}")

    def _send(self, addr: tuple, response: SessionPacket):
        """Wyślij pakiet odpowiedzi."""
        try:
            self.sock.sendto(response.to_json(), addr)
        except Exception as e:
            print(f"[SERVER] error sending to {addr}: {e}")

    def _handle_packet(self, packet: SessionPacket, addr: tuple):
        """Obsłuż pakiet na podstawie typu i walidacji."""

        with self.lock:
            session = (
                self.sessions.get(packet.session_id) if packet.session_id else None
            )

        # Walidacja pakietu
        is_valid, reason = SessionValidator.validate_packet(
            packet, session, addr, allow_login=(packet.packet_type == "LOGIN")
        )

        if not is_valid:
            print(
                f"[SERVER] invalid packet from {addr}: {reason} (type={packet.packet_type})"
            )
            response = SessionPacket(
                packet_type="ERROR", session_id=packet.session_id, payload=reason
            )
            self._send(addr, response)
            return

        # Handler pakietów
        if packet.packet_type == "LOGIN":
            self._handle_login(packet, addr)
        elif packet.packet_type == "HEARTBEAT":
            self._handle_heartbeat(packet, session, addr)
        elif packet.packet_type == "DATA":
            self._handle_data(packet, session, addr)
        elif packet.packet_type == "DISCONNECT":
            self._handle_disconnect(packet, session, addr)
        else:
            response = SessionPacket(
                packet_type="ERROR",
                session_id=packet.session_id,
                token=packet.token,
                payload="unknown packet type",
            )
            self._send(addr, response)

    def _handle_login(self, packet: SessionPacket, addr: tuple):
        """Nowa sesja."""
        session = Session(
            session_id=str(time.time_ns()),
            token=f"token_{time.time_ns()}",
            client_addr=addr,
            created_at=time.monotonic(),
            last_seen=time.monotonic(),
        )

        with self.lock:
            self.sessions[session.session_id] = session

        print(f"[SERVER] new session: {session.session_id} from {addr}")

        response = SessionPacket(
            packet_type="LOGIN_ACK",
            session_id=session.session_id,
            token=session.token,
            seq=0,
            timestamp=time.monotonic(),
        )
        self._send(addr, response)

    def _handle_heartbeat(self, packet: SessionPacket, session: Session, addr: tuple):
        """Refresh sesji."""
        with self.lock:
            session.refresh()
            print(f"[SERVER] heartbeat seq={packet.seq} session={packet.session_id}")

        response = SessionPacket(
            packet_type="HEARTBEAT_ACK",
            session_id=packet.session_id,
            token=packet.token,
            seq=packet.seq,
            timestamp=time.monotonic(),
        )
        self._send(addr, response)

    def _handle_data(self, packet: SessionPacket, session: Session, addr: tuple):
        """Odbierz dane i potwierdź."""
        with self.lock:
            session.refresh()
            session.expected_seq += 1
            print(f"[SERVER] data seq={packet.seq}: {packet.payload}")

        response = SessionPacket(
            packet_type="DATA_ACK",
            session_id=packet.session_id,
            token=packet.token,
            seq=packet.seq,
            timestamp=time.monotonic(),
        )
        self._send(addr, response)

    def _handle_disconnect(self, packet: SessionPacket, session: Session, addr: tuple):
        """Zamknij sesję."""
        with self.lock:
            if packet.session_id in self.sessions:
                del self.sessions[packet.session_id]
                print(f"[SERVER] session disconnected: {packet.session_id}")

        response = SessionPacket(
            packet_type="DISCONNECT_ACK",
            session_id=packet.session_id,
            token=packet.token,
            seq=packet.seq,
            timestamp=time.monotonic(),
        )
        self._send(addr, response)


if __name__ == "__main__":
    server = UdpSessionServer()
    server.start()
