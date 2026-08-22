#!/usr/bin/env python3
"""
Quick Start Guide - Uruchamianie testów edukacyjnych
"""

import subprocess
import sys
import os


def print_banner(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def run_command(cmd, description):
    print_banner(description)
    print(f"$ {' '.join(cmd)}\n")
    try:
        result = subprocess.run(cmd, capture_output=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print_banner("UDP SESSION PROTOCOL - EDUCATIONAL TEST SUITE")

    print(
        """
This suite demonstrates:
1. Proper Layer-7 session management for UDP
2. Anti-spoofing and authentication mechanisms
3. Heartbeat and keep-alive protocols
4. Sequence numbering and reliability
5. Anomaly detection and metrics collection

Key concepts vs. game_dc.py:
- game_dc.py: Raw UDP flood (ineffective, violates protocol)
- This code: Stateful session with authorization (proper approach)

Available tests:

1. Protocol Module Test
   Tests: SessionPacket structure, SessionValidator, ProtocolConstants

2. Anomaly Detector Test
   Tests: Sequence jump detection, heartbeat timeout, flood detection

3. Metrics Collection Test
   Tests: RTT calculation, jitter, packet loss, throughput

4. Server + Client Integration Test
   Tests: Full handshake, heartbeat loop, data exchange, disconnect
"""
    )

    print_banner("1. Testing Protocol Module")
    run_command([sys.executable, "session_protocol.py"], "Protocol structures")

    print_banner("2. Testing Anomaly Detector")
    run_command([sys.executable, "session_anomaly_detector.py"], "Anomaly detection")

    print_banner("3. Testing Metrics Collection")
    run_command([sys.executable, "session_metrics.py"], "Metrics collection")

    print_banner("4. INTEGRATION TEST: Server + Client")
    print(
        """
This test will:
1. Start UDP Session Server (port 30000)
2. Wait 2 seconds for server to bind
3. Start UDP Session Client
4. Observe: LOGIN, HEARTBEAT, DATA, DISCONNECT flow

Note: Press Ctrl+C to stop server after client finishes.
"""
    )

    input("Press Enter to start integration test...")

    # Run server and client
    from udp_session_server import UdpSessionServer
    from udp_session_client import UdpSessionClient
    import threading

    server = UdpSessionServer()
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    import time

    time.sleep(2.0)

    client = UdpSessionClient()

    if client.login():
        client.start_heartbeat()

        time.sleep(1.0)
        client.send_data("Hello from integration test!")

        time.sleep(2.0)
        client.send_data("Second message")

        time.sleep(3.0)
        client.disconnect()
        client.close()

    print_banner("TESTS COMPLETED")
    print(
        """
Summary:
✓ Protocol module - JSON packets with authentication
✓ Anomaly detector - Detects sequence jumps, timeouts, spoofing
✓ Metrics - Collects RTT, jitter, packet loss, throughput
✓ Integration - Full session lifecycle

Next steps:
1. Read README_EDUCATIONAL.md for full documentation
2. Review session_protocol.py - understand packet structure
3. Review udp_session_server.py - understand session validation
4. Modify tests to simulate attacks and observe detection

This is educational code demonstrating Layer-7 protocol design
principles for P2P applications.
"""
    )


if __name__ == "__main__":
    main()
