import os
import signal
import socket
import threading
import time
from collections import deque

import psutil
import requests
from scapy.all import IP, UDP, sniff

# --- CONFIGURATION ---
TARGET_PORT = 16000

GAME_PROCESS_NAMES = [
    "GameRanger.exe",
    "age2_x1.exe",
    "empire.exe",
    "stronghold.exe",
    "swbg.exe",
    "cnc3.exe",
]

HOSTING_ISPS = [
    "OVH",
    "DigitalOcean",
    "Amazon",
    "Microsoft",
    "Google",
    "Datacamp",
    "Hetzner",
    "Choopa",
    "Akamai",
    "Relay",
    "Cloudflare",
]

LOG_FILE = "p2p_security_log.json"

# --- ALERT SETTINGS ---
PPS_THRESHOLD = 300
ALARM_ENABLED = True

# --- GLOBAL DATA ---
p2p_intel = {}
keep_running = True
data_lock = threading.Lock()
active_game_ports = {TARGET_PORT}


def signal_handler(sig, frame):
    global keep_running

    keep_running = False
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)


def get_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]

    except OSError:
        return "127.0.0.1"

    finally:
        try:
            sock.close()
        except Exception:
            pass


MY_IP = get_local_ip()


def is_p2p_node(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,country,city,isp,hosting"

        response = requests.get(url, timeout=2)
        response.raise_for_status()

        data = response.json()

        if data.get("status") == "success":
            isp = data.get("isp", "Unknown")

            # Ignore hosting providers / relays / cloud infrastructure
            if data.get("hosting") or any(
                hosting.lower() in isp.lower() for hosting in HOSTING_ISPS
            ):
                return None

            return {
                "loc": f"{data.get('country')}, {data.get('city')}",
                "isp": isp,
            }

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ):
        return None

    return None


def packet_callback(pkt):
    if not keep_running:
        return

    if pkt.haslayer(IP) and pkt.haslayer(UDP):
        with data_lock:
            ports = active_game_ports

        if pkt[UDP].sport in ports or pkt[UDP].dport in ports:
            remote_ip = pkt[IP].src if pkt[IP].src != MY_IP else pkt[IP].dst

            # Ignore localhost and LAN traffic
            if remote_ip == "127.0.0.1" or remote_ip.startswith("192.168."):
                return

            current_time = time.time()

            with data_lock:
                if remote_ip not in p2p_intel:
                    # Register asynchronously to avoid blocking packet sniffing
                    threading.Thread(
                        target=async_register,
                        args=(remote_ip,),
                        daemon=True,
                    ).start()

                    p2p_intel[remote_ip] = {
                        "loc": "Analyzing...",
                        "isp": "...",
                        "packets": 1,
                        "last_seen": current_time,
                        "history": deque([current_time], maxlen=1000),
                    }

                else:
                    p2p_intel[remote_ip]["packets"] += 1
                    p2p_intel[remote_ip]["last_seen"] = current_time
                    p2p_intel[remote_ip]["history"].append(current_time)


def async_register(ip):
    intel = is_p2p_node(ip)

    with data_lock:
        if intel and ip in p2p_intel:
            p2p_intel[ip]["loc"] = intel["loc"]
            p2p_intel[ip]["isp"] = intel["isp"]

        elif not intel:
            # Remove non-P2P nodes from monitoring
            p2p_intel.pop(ip, None)


def refresh_ui():
    if not keep_running:
        return

    os.system("cls" if os.name == "nt" else "clear")

    now = time.time()

    print("=" * 110)
    print(
        f" SECURITY MONITOR (IDS) | "
        f"MY IP: {MY_IP} | "
        f"ALERT THRESHOLD: {PPS_THRESHOLD} PPS"
    )
    print("=" * 110)
    print(f" {'IP Address':<15} | {'PPS':<6} | {'Status':<12} | Location and ISP")
    print("-" * 110)

    with data_lock:
        sorted_items = sorted(
            p2p_intel.items(),
            key=lambda item: item[1]["packets"],
            reverse=True,
        )

        for ip, data in sorted_items:
            if now - data["last_seen"] < 30:
                # Calculate packets per second
                pps = sum(1 for timestamp in data["history"] if timestamp > now - 1)

                status = "SAFE"

                if ALARM_ENABLED and pps > PPS_THRESHOLD:
                    status = "!! ATTACK !!"

                    if os.name == "nt":
                        try:
                            import winsound

                            # Short alert sound
                            winsound.Beep(1000, 200)

                        except RuntimeError:
                            pass

                print(
                    f" {ip:<15} | "
                    f"{pps:<6} | "
                    f"{status:<12} | "
                    f"{data['loc']} ({data['isp']})"
                )


def update_ports():
    global active_game_ports

    while keep_running:
        ports = {TARGET_PORT}

        try:
            for proc in psutil.process_iter(["name"]):
                process_name = proc.info.get("name")

                if not process_name:
                    continue

                if any(
                    game_name.lower() in process_name.lower()
                    for game_name in GAME_PROCESS_NAMES
                ):
                    try:
                        for connection in proc.connections(kind="udp"):
                            if connection.laddr.port:
                                ports.add(connection.laddr.port)

                    except (
                        psutil.AccessDenied,
                        psutil.NoSuchProcess,
                        psutil.ZombieProcess,
                    ):
                        continue

        except (psutil.Error, OSError):
            pass

        with data_lock:
            active_game_ports = ports

        time.sleep(5)


def main():
    if os.name == "nt":
        import ctypes

        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("RUN AS ADMINISTRATOR!")
            return

    threading.Thread(target=update_ports, daemon=True).start()

    try:
        while keep_running:
            sniff(
                prn=packet_callback,
                filter="udp",
                store=False,
                timeout=1,
            )

            refresh_ui()

    except KeyboardInterrupt:
        print("\nShutting down monitor...")

    except Exception as error:
        print(f"\nCritical error: {error}")

    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
