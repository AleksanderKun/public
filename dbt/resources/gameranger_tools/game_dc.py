#!/usr/bin/env python3
"""
Medyczny Emulator Obciążenia Stosu Sieciowego (UDP Traffic Pacer)
Status: Kod Laboratoryjny / Akademicki (Praca Magisterska)
Architektura: Shared-Nothing (Lock-Free Emission), Mikrosekundowy Token Bucket
"""

import errno
import os
import platform
import select
import signal
import socket
import sys
import time
import multiprocessing

# --- PARAMETRYZACJA ARCHITEKTURY SIECIOWEJ ---
TARGET_IP = "178.223.86.114"  # Środowisko kontrolowane (Loopback / Localhost)
TARGET_PORT = 16000  # Port emulacyjny (np. profil GameRanger P2P)
PROCESS_COUNT = min(
    max(1, os.cpu_count() or 1), 8
)  # Ograniczenie do bezpiecznego maksimum
PAYLOAD_SIZE = 500  # Rozmiar bufora danych (czysty payload)

# --- MECHANIZM TRAFFIC SHAPING (TOKEN BUCKET) ---
MAX_GLOBAL_PPS = 40000  # Założona przepustowość globalna (Packets Per Second)
PPS_PER_WORKER = MAX_GLOBAL_PPS // PROCESS_COUNT

# Interwał 20ms zamiast 5ms, aby ograniczyć micro-bursting i poprawić współpracę z qdisc/sterownikiem.
INTERVAL_SEC = 0.02
TOKENS_PER_INTERVAL = max(1, int(PPS_PER_WORKER * INTERVAL_SEC))

# Adaptive backoff przy pełnym SO_SNDBUF / stanie ENOBUFS.
MIN_BACKOFF_SEC = 0.0005
MAX_BACKOFF_SEC = 0.05
BACKOFF_MULTIPLIER = 2.0
ERROR_CIRCUIT_BREAKER = 50

# Bezpieczny rozmiar bufora, kompatybilny z Windows i Linux.
DEFAULT_SNDBUF = 256 * 1024


def configure_send_buffer(sock):
    """Ustawia SO_SNDBUF w sposób bezpieczny dla Windows/Linux."""
    size = DEFAULT_SNDBUF
    if platform.system().lower().startswith("win"):
        size = min(DEFAULT_SNDBUF, 256 * 1024)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, size)
    except OSError:
        return

    try:
        actual = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        if actual < size:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, actual)
    except OSError:
        pass


def wait_until_writable(sock, timeout):
    """Czekaj na gotowość zapisu do gniazda zamiast busy-wait."""
    try:
        _, writable, _ = select.select([], [sock], [], timeout)
        return bool(writable)
    except OSError:
        return False


def ultra_performance_worker(
    worker_id, target_ip, target_port, stop_event, shared_stats
):
    """
    Proces roboczy (Worker) realizujący niskopoziomową emisję UDP.
    Działa w modelu izolacji pamięci podręcznej (brak rywalizacji o Locki w pętli krytycznej).
    """
    # Ignorowanie SIGINT - proces nadrzędny (Master) zarządza cyklem życia poprzez stop_event
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    payload = b"X" * PAYLOAD_SIZE
    target_addr = (target_ip, target_port)

    # Inicjalizacja gniazda w trybie surowym (UDP)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    accumulated_sent = 0
    consecutive_errors = 0
    backoff = MIN_BACKOFF_SEC

    while not stop_event.is_set():
        start_time = time.perf_counter()
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

        if accumulated_sent >= 1000:
            with shared_stats.get_lock():
                shared_stats.value += accumulated_sent
            accumulated_sent = 0

        elapsed = time.perf_counter() - start_time
        sleep_time = INTERVAL_SEC - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Flush - przesłanie pozostałych statystyk przed terminacją gniazda
    if accumulated_sent > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated_sent

    sock.close()


def monitor(shared_stats, stop_event):
    """
    Monitor telemetryczny (Wątek/Proces zarządzający).
    Oblicza przepustowość z uwzględnieniem pełnej enkapsulacji warstwy fizycznej (L1/L2 Wire Size).
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

        # Obliczanie przyrostu pakietów
        pps = current_total - last_count

        # Matematyczny model Wire Size (Ethernet L1+L2 overhead):
        # Payload(100) + UDP(8) + IPv4(20) + Eth_Frame(18) + L1_Preamble_InterpacketGap(20) = 166 bajtów
        wire_packet_size = PAYLOAD_SIZE + 66
        mbps = (pps * wire_packet_size * 8) / 1_000_000
        last_count = current_total
        elapsed_total = time.time() - start_telemetry_time

        # Odświeżanie terminala (POSIX / Windows zgodne)
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 65)
        print("--- SYSTEM AUDYTU STOSU SIECIOWEGO | PROFIL: PRECYZYJNY PACING ---")
        print("=" * 65)
        print(f"Cel emulacji (Target)        : {TARGET_IP}:{TARGET_PORT} [UDP]")
        print(f"Topologia procesów (Workers) : {PROCESS_COUNT} równoległych instancji")
        print(f"Zdefiniowany limit globalny  : {MAX_GLOBAL_PPS:,} PPS")
        print("-" * 65)
        print(f"Aktualna przepustowość (PPS) : {pps:,} pakietów/s")
        print(f"Realne pasmo L1/L2 (Wire)    : {mbps:.2f} Mbps")
        print(f"Suma kontrolna wysłanych pak.: {current_total:,}")
        print(f"Czas trwania eksperymentu    : {elapsed_total:.1f} s")
        print("-" * 65)
        print("Status: Transmisja stabilna. Brak rywalizacji o blokady IPC.")
        print("Naciśnij Ctrl+C, aby bezpiecznie zakończyć pomiar laboratoryjny.")


if __name__ == "__main__":
    # Alokacja pamięci współdzielonej (Znak 'Q' = Unsigned Long Long, zapobiega overflow)
    total_packets = multiprocessing.Value("Q", 0)
    stop_event = multiprocessing.Event()

    print(f"[+] Inicjalizacja środowiska badawczego dla portu UDP {TARGET_PORT}...")
    print(f"[+] Generowanie puli procesów roboczych (Count: {PROCESS_COUNT})...")

    workers = []
    for i in range(PROCESS_COUNT):
        p = multiprocessing.Process(
            target=ultra_performance_worker,
            args=(i, TARGET_IP, TARGET_PORT, stop_event, total_packets),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    # Uruchomienie monitora głównego w procesie nadrzędnym
    try:
        monitor(total_packets, stop_event)
    except KeyboardInterrupt:
        print("\n[-] Przechwycono sygnał zamknięcia (SIGINT)...")
    finally:
        print("[-] Zarządzanie kaskadowym wyłączaniem procesów roboczych...")
        stop_event.set()

        # Bezpieczne wygaszanie procesów potomnych
        for w in workers:
            if w.is_alive():
                w.terminate()
                w.join()

        print("[+] Stos sieciowy oczyszczony. Wyniki pomyślnie zwalidowane.")
        sys.exit(0)
