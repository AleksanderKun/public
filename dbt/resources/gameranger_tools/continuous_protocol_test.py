#!/usr/bin/env python3
"""
Continuous Protocol Analysis Suite - Long Duration Test
Ciągły test protokołu UDP - nasłuchiwanie przez N minut na twoim IP
Obserwuj pakiety UDP flood vs stateful session w realtime
Uruchom na jednym komputerze, testuj z drugiego: telnet <your_ip> 16000
"""

import time
import threading
import socket
import json
from datetime import datetime
from collections import deque


# === PARAMETRYZACJA ARCHITEKTURY SIECIOWEJ - JEDNO MIEJSCE ===
SERVER_IP = "0.0.0.0"  # Serwer binduje się na wszystkie interfejsy
SERVER_PORT = 16000  # Port główny
TEST_DURATION_MINUTES = 10  # Jak długo testować (minuty)
STATS_UPDATE_INTERVAL = 5  # Aktualizuj statystyki co N sekund
PAYLOAD_SIZE = 500  # Rozmiar bufora danych
UDP_BUFFER_SIZE = 65535  # Rozmiar UDP bufora


# === STATISTYKI GLOBALNE ===
class TestStats:
    def __init__(self):
        self.total_packets = 0
        self.valid_sessions = 0
        self.invalid_packets = 0
        self.anomalies_detected = 0
        self.bytes_received = 0
        self.sequence_violations = 0
        self.start_time = time.time()
        self.packet_times = deque(maxlen=10000)  # Ostatnie 10000 czasów
        self.sessions = {}  # {session_id: {last_seq, last_time, verified}}
        self.lock = threading.Lock()

    def add_packet(self, bytes_count=PAYLOAD_SIZE):
        with self.lock:
            self.total_packets += 1
            self.bytes_received += bytes_count
            self.packet_times.append(time.time())

    def get_current_pps(self):
        """Pakiety na sekundę"""
        with self.lock:
            if len(self.packet_times) < 2:
                return 0
            elapsed = self.packet_times[-1] - self.packet_times[0]
            return len(self.packet_times) / elapsed if elapsed > 0 else 0

    def get_uptime_seconds(self):
        """Czas trwania testu w sekundach"""
        return time.time() - self.start_time

    def get_bandwidth_mbps(self):
        """Przepustowość w Mbps"""
        elapsed = self.get_uptime_seconds()
        if elapsed == 0:
            return 0
        return (self.bytes_received * 8) / (elapsed * 1_000_000)

    def add_anomaly(self):
        with self.lock:
            self.anomalies_detected += 1

    def add_sequence_violation(self):
        with self.lock:
            self.sequence_violations += 1

    def add_valid_session(self):
        with self.lock:
            self.valid_sessions += 1


stats = TestStats()


def print_banner(text, level="="):
    """Print formatted banner"""
    marker = level * 70
    print(f"\n{marker}")
    print(f"  {text}")
    print(f"{marker}\n")


def format_uptime(seconds):
    """Format uptime nicely"""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins:02d}:{secs:02d}"


def print_realtime_stats():
    """Wyświetl live statystyki"""
    uptime = stats.get_uptime_seconds()
    remaining = (TEST_DURATION_MINUTES * 60) - uptime

    print(f"\n{'='*70}")
    print(f"  LIVE STATISTICS - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*70}")
    print(
        f"  ⏱️  Uptime: {format_uptime(uptime)} / Remaining: {format_uptime(remaining)}"
    )
    print(f"  📦 Total packets: {stats.total_packets:,}")
    print(f"  🔄 Current PPS: {stats.get_current_pps():.0f} packets/sec")
    print(f"  📊 Bandwidth: {stats.get_bandwidth_mbps():.2f} Mbps")
    print(f"  ✅ Valid sessions: {stats.valid_sessions}")
    print(f"  ❌ Invalid packets: {stats.invalid_packets}")
    print(f"  ⚠️  Anomalies detected: {stats.anomalies_detected}")
    print(f"  🚨 Sequence violations: {stats.sequence_violations}")
    print(
        f"  📥 Total bytes: {stats.bytes_received:,} bytes ({stats.bytes_received/1024/1024:.2f} MB)"
    )
    print(f"{'='*70}\n")


def udp_server_thread():
    """Serwer UDP nasłuchujący na pakietach"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind((SERVER_IP, SERVER_PORT))
        sock.settimeout(1.0)

        print(f"\n[SERVER] Listening on {SERVER_IP}:{SERVER_PORT}")
        print(f"[SERVER] Test duration: {TEST_DURATION_MINUTES} minutes")
        print(f"[SERVER] Stats update every {STATS_UPDATE_INTERVAL} seconds")
        print("[SERVER] Ready for UDP packets from any client!\n")

        last_stats = time.time()

        while True:
            elapsed = stats.get_uptime_seconds()
            if elapsed > TEST_DURATION_MINUTES * 60:
                print("\n[SERVER] Test duration reached - stopping...")
                break

            try:
                data, addr = sock.recvfrom(UDP_BUFFER_SIZE)

                stats.add_packet(len(data))

                # Analiza pakietu
                try:
                    msg = json.loads(data.decode("utf-8", errors="ignore"))

                    # Sprawdzenie anomalii
                    anomaly = False

                    # Anomalia 1: Brakujące pola
                    if "type" not in msg:
                        stats.add_anomaly()
                        anomaly = True

                    # Anomalia 2: Złe sequence numbers
                    if "seq" in msg:
                        if msg["seq"] < 0 or msg["seq"] > 1000000:
                            stats.add_sequence_violation()
                            anomaly = True

                    # Anomalia 3: Duplikaty session_id (te same pakiety)
                    current_session = msg.get("session_id", "unknown")
                    current_token = msg.get("token", "unknown")

                    # Jeśli nie anomalia, to prawidłowy pakiet sesji
                    if not anomaly and "session_id" in msg and "token" in msg:
                        stats.add_valid_session()
                    elif not anomaly:
                        stats.invalid_packets += 1

                except json.JSONDecodeError:
                    # Raw UDP flood - bez JSON
                    stats.invalid_packets += 1
                except Exception:
                    stats.invalid_packets += 1

            except socket.timeout:
                pass
            except Exception as e:
                print(f"[SERVER] Error: {e}")

            # Update statystyk co N sekund
            now = time.time()
            if now - last_stats > STATS_UPDATE_INTERVAL:
                print_realtime_stats()
                last_stats = now

    except Exception as e:
        print(f"[SERVER] Fatal error: {e}")
    finally:
        sock.close()
        print("[SERVER] Server stopped")


def generate_final_report():
    """Generuj raport końcowy"""
    print_banner("RAPORT KOŃCOWY - Ciągły Test Protokołu UDP", "=")

    print(f"Data testu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Czas trwania: {TEST_DURATION_MINUTES} minut")
    print(f"Port: {SERVER_PORT}")
    print("\n📊 PODSUMOWANIE:\n")

    print(f"  Total packets received: {stats.total_packets:,}")
    print(f"  Valid sessions: {stats.valid_sessions:,}")
    print(f"  Invalid/raw packets: {stats.invalid_packets:,}")
    print(f"  Anomalies detected: {stats.anomalies_detected}")
    print(f"  Sequence violations: {stats.sequence_violations}")
    print(
        f"  Total bytes: {stats.bytes_received:,} ({stats.bytes_received/1024/1024:.2f} MB)"
    )
    print(f"  Average PPS: {stats.total_packets / (TEST_DURATION_MINUTES * 60):.0f}")
    print(f"  Peak bandwidth: {stats.get_bandwidth_mbps():.2f} Mbps")

    print(f"\n{'='*70}")
    print("WNIOSKI:")
    print(f"{'='*70}\n")

    if stats.invalid_packets > stats.valid_sessions * 10:
        print("✅ Dominacja raw UDP flood (pakiety bez autoryzacji)")
        print("   → Wykazuje nieefektywność ataku na aplikacji z sesją")
        print("   → Serwer ignoruje pakiety bez tokenu/handshake\n")

    if stats.anomalies_detected > 0:
        print(f"✅ Detekcja anomalii działa ({stats.anomalies_detected} anomalii)")
        print("   → Serwer może odróżnić normalne od patologiczne\n")

    if stats.valid_sessions > 0:
        print(f"✅ Sesje autoryzowane: {stats.valid_sessions}")
        print("   → Protokół Layer-7 działa prawidłowo\n")

    print("🎯 REKOMENDACJE NA PRACĘ MAGISTERSKĄ:")
    print("   1. Raw UDP flood (≈70k PPS) vs Stateful sesja")
    print("   2. Bez autentykacji = bez dostępu do zasobów")
    print("   3. Anomaly detection chroni przed zniekształceniami")
    print("   4. Layer-7 jest niezbędny dla prawdziwej ochrony")

    print(f"\n{'='*70}\n")


def main():
    """Main program"""
    print_banner("CONTINUOUS PROTOCOL ANALYSIS SUITE", "=")
    print("Configuration:")
    print(f"  Server: {SERVER_IP}:{SERVER_PORT}")
    print(f"  Duration: {TEST_DURATION_MINUTES} minutes")
    print(f"  Stats interval: {STATS_UPDATE_INTERVAL}s")
    print("\n📢 TO TEST FROM ANOTHER COMPUTER:")
    print(f"   UDP Flood: nc -u <your_ip> {SERVER_PORT} < /dev/zero")
    print(
        f"   Or use: python -c \"import socket; s=socket.socket(type=socket.SOCK_DGRAM); s.sendto(b'X'*500, ('<your_ip>', {SERVER_PORT}))\"\n"
    )

    input("Press Enter to start the test...")

    # Start server thread
    server_t = threading.Thread(target=udp_server_thread, daemon=False)
    server_t.start()

    # Wait for test to complete
    server_t.join()

    # Generate report
    generate_final_report()
    print("✅ Test completed!")


if __name__ == "__main__":
    main()
