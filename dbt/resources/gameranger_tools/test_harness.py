#!/usr/bin/env python3
"""
Integrated Test Harness
Uruchamia serwer, klienta i monitor w jednym procesie dla testów edukacyjnych.
"""

import subprocess
import sys
import threading
import time


def run_server():
    """Uruchom serwer."""
    print("\n" + "=" * 70)
    print("STARTING UDP SESSION SERVER")
    print("=" * 70)
    subprocess.run([sys.executable, "udp_session_server.py"])


def run_client():
    """Uruchom klienta (opóźniony start)."""
    time.sleep(2.0)  # Czekaj na serwer
    print("\n" + "=" * 70)
    print("STARTING UDP SESSION CLIENT")
    print("=" * 70)
    subprocess.run([sys.executable, "udp_session_client.py"])


def main():
    """Uruchom serwer i klienta w parallel."""
    print("[HARNESS] Educational UDP Session Test")
    print("[HARNESS] This demonstrates proper layer-7 protocol design")

    server_thread = threading.Thread(target=run_server, daemon=False)
    client_thread = threading.Thread(target=run_client, daemon=False)

    server_thread.start()
    client_thread.start()

    try:
        server_thread.join()
        client_thread.join()
    except KeyboardInterrupt:
        print("\n[HARNESS] shutting down...")


if __name__ == "__main__":
    main()
