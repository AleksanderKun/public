#!/usr/bin/env python3
"""
Attack Monitor - Zbiera statystyki podczas każdego ataku
Uruchom przed analyze_attacks.py w osobnym terminalu
"""

import socket
import json
import time
import threading
from datetime import datetime


# === KONFIGURACJA ===
LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 16001  # Inny port niż sam serwer
STATS_INTERVAL = 1  # Sekundy między snapshottami
OUTPUT_FILE = "attack_stats.jsonl"  # JSON Lines format


class AttackMonitor:
    """Monitor zbierający statystyki"""

    def __init__(self):
        self.snapshots = []
        self.running = False
        self.lock = threading.Lock()

    def log(self, msg):
        """Log with timestamp"""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def start_monitoring(self):
        """Główna pętla monitoringu"""
        self.running = True
        self.log("📊 Attack Monitor Started")
        self.log(f"Collecting stats every {STATS_INTERVAL}s")
        self.log(f"Output: {OUTPUT_FILE}")

        # Stwórz dedykowany socket do czytania statystyk
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((LISTEN_IP, LISTEN_PORT))
        sock.settimeout(1.0)

        snapshot_id = 0

        try:
            while self.running:
                snapshot_id += 1
                start_time = time.time()

                snapshot = {
                    "id": snapshot_id,
                    "timestamp": datetime.now().isoformat(),
                    "packets": 0,
                    "bytes": 0,
                    "valid_sessions": 0,
                    "invalid_packets": 0,
                    "anomalies": 0,
                    "sequence_violations": 0,
                }

                # Zbierz pakiety przez N sekund
                snapshot_start = time.time()
                while time.time() - snapshot_start < STATS_INTERVAL:
                    try:
                        data, addr = sock.recvfrom(65535)
                        snapshot["packets"] += 1
                        snapshot["bytes"] += len(data)

                        # Analiza
                        try:
                            msg = json.loads(data.decode("utf-8", errors="ignore"))

                            # Count valid vs invalid
                            if "session_id" in msg and "token" in msg:
                                snapshot["valid_sessions"] += 1
                            else:
                                snapshot["invalid_packets"] += 1

                            # Check sequence violations
                            if "seq" in msg:
                                seq = msg["seq"]
                                if seq < 0 or seq > 1000000:
                                    snapshot["sequence_violations"] += 1
                        except:
                            snapshot["invalid_packets"] += 1

                    except socket.timeout:
                        pass

                # Save snapshot
                with self.lock:
                    self.snapshots.append(snapshot)
                    self.save_snapshot(snapshot)

                # Print live stats
                pps = snapshot["packets"] / STATS_INTERVAL
                mbps = (snapshot["bytes"] * 8) / (STATS_INTERVAL * 1_000_000)

                print(
                    f"  📦 PPS: {pps:,.0f} | Valid: {snapshot['valid_sessions']:,} | "
                    f"Invalid: {snapshot['invalid_packets']:,} | "
                    f"SeqViol: {snapshot['sequence_violations']:,}"
                )

        except KeyboardInterrupt:
            self.log("\n[!] Monitoring stopped by user")
        except Exception as e:
            self.log(f"[!] Error: {e}")
        finally:
            sock.close()
            self.running = False

    def save_snapshot(self, snapshot):
        """Zapisz snapshot do pliku"""
        try:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot) + "\n")
        except Exception as e:
            print(f"[!] Error saving snapshot: {e}")

    def stop(self):
        """Zatrzymaj monitoring"""
        self.running = False


def main():
    monitor = AttackMonitor()

    print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║              ATTACK MONITOR - Statistics Collector                  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  This tool collects real-time statistics during attacks             ║
║  Output: attack_stats.jsonl (JSON Lines format)                     ║
║                                                                      ║
║  Run this in Terminal 1:                                            ║
║    python attack_monitor.py                                         ║
║                                                                      ║
║  Then in Terminal 2 run:                                            ║
║    python analyze_attacks.py                                        ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    )

    try:
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")


if __name__ == "__main__":
    main()
