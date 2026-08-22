#!/usr/bin/env python3
"""
UDP Session Client (Educational Reference Implementation)
Demonstruje prawidłowe działanie klienta z autoryzacją i heartbeat.
"""

import socket
import threading
import time
from session_protocol import SessionPacket, ProtocolConstants


class UdpSessionClient:
    """Klient komunikujący się z serwerem UDP z sesją."""

    def __init__(self, server_host: str = "178.223.86.114", server_port: int = 16000):
        self.server_addr = (server_host, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2.0)

        self.session_id: str = None
        self.token: str = None
        self.seq: int = 1
        self.running = True

        print(f"[CLIENT] connecting to {server_host}:{server_port}")

    def _send_packet(self, packet_type: str, payload: str = None) -> bool:
        """Wyślij pakiet do serwera."""
        try:
            packet = SessionPacket(
                packet_type=packet_type,
                session_id=self.session_id,
                token=self.token,
                seq=self.seq if packet_type != "LOGIN" else None,
                timestamp=time.monotonic(),
                payload=payload,
            )
            self.sock.sendto(packet.to_json(), self.server_addr)
            return True
        except Exception as e:
            print(f"[CLIENT] send error: {e}")
            return False

    def _receive_packet(self, timeout: float = 2.0) -> SessionPacket:
        """Odbierz pakiet z serwera."""
        try:
            self.sock.settimeout(timeout)
            data, _ = self.sock.recvfrom(4096)
            packet = SessionPacket.from_json(data)
            return packet
        except socket.timeout:
            return None
        except Exception as e:
            print(f"[CLIENT] receive error: {e}")
            return None

    def login(self) -> bool:
        """Zaloguj się do serwera."""
        print("[CLIENT] sending LOGIN...")
        if not self._send_packet("LOGIN"):
            return False

        response = self._receive_packet()
        if response is None or response.packet_type != "LOGIN_ACK":
            print("[CLIENT] LOGIN failed, no valid response")
            return False

        self.session_id = response.session_id
        self.token = response.token
        print("[CLIENT] LOGIN successful!")
        print(f"[CLIENT] session_id: {self.session_id}")
        print(f"[CLIENT] token: {self.token}")
        return True

    def start_heartbeat(self):
        """Uruchom wątek heartbeat w tle."""

        def heartbeat_loop():
            while self.running and self.session_id:
                time.sleep(ProtocolConstants.HEARTBEAT_INTERVAL)
                print("[CLIENT] sending HEARTBEAT...")
                if not self._send_packet("HEARTBEAT"):
                    continue

                response = self._receive_packet()
                if response and response.packet_type == "HEARTBEAT_ACK":
                    print(f"[CLIENT] heartbeat ack seq={response.seq}")
                else:
                    print("[CLIENT] heartbeat timeout or error")

        thread = threading.Thread(target=heartbeat_loop, daemon=True)
        thread.start()

    def send_data(self, payload: str) -> bool:
        """Wyślij dane do serwera."""
        print(f"[CLIENT] sending DATA seq={self.seq}: {payload}")
        if not self._send_packet("DATA", payload=payload):
            return False

        response = self._receive_packet()
        if response and response.packet_type == "DATA_ACK":
            print(f"[CLIENT] data ack seq={response.seq}")
            self.seq += 1
            return True
        else:
            print("[CLIENT] data not acknowledged")
            return False

    def disconnect(self) -> bool:
        """Rozłącz się z serwera."""
        print(f"[CLIENT] sending DISCONNECT seq={self.seq}...")
        if not self._send_packet("DISCONNECT"):
            return False

        response = self._receive_packet()
        if response and response.packet_type == "DISCONNECT_ACK":
            print("[CLIENT] disconnect ack")
            self.running = False
            return True
        else:
            print("[CLIENT] disconnect not acknowledged")
            return False

    def close(self):
        """Zamknij gniazdo."""
        self.running = False
        self.sock.close()


def demo():
    """Demonstracyjny przepływ."""
    client = UdpSessionClient()

    if not client.login():
        print("[DEMO] login failed")
        return

    # Uruchom heartbeat w tle
    client.start_heartbeat()

    # Wyślij kilka pakietów danych
    time.sleep(1.0)
    client.send_data("hello world")

    time.sleep(2.0)
    client.send_data("second message")

    time.sleep(2.0)
    client.send_data("third message")

    # Czekaj i pozwól heartbeat działać
    time.sleep(5.0)

    # Rozłącz się
    client.disconnect()
    client.close()
    print("[DEMO] done")


if __name__ == "__main__":
    demo()
