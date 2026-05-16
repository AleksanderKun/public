import socket
import time
import threading

# --- KONFIGURACJA TESTU ---
TARGET_IP = "88.230.127.224"  # Wpisz adres IP swojego drugiego komputera
TARGET_PORT = 16000  # Port, który monitoruje Twój skrypt
PACKETS_TO_SEND = 5000  # Całkowita liczba pakietów
DELAY = 0.001  # Opóźnienie między pakietami (im mniejsze, tym wyższy PPS)


def flood_test():
    # Tworzymy surowe gniazdo UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"TEST_PACKET_DATA_IDS_CHECK"

    print(f"[*] Rozpoczynanie generowania ruchu na {TARGET_IP}:{TARGET_PORT}...")

    for i in range(PACKETS_TO_SEND):
        try:
            sock.sendto(payload, (TARGET_IP, TARGET_PORT))
            if i % 100 == 0:
                print(f"[+] Wysłano {i} pakietów...")
            time.sleep(DELAY)
        except Exception as e:
            print(f"[!] Błąd: {e}")
            break

    print("[*] Test zakończony.")


if __name__ == "__main__":
    # Możesz uruchomić kilka wątków, aby zwielokrotnić PPS
    threads = []
    for _ in range(3):  # 3 wątki wysyłające pakiety jednocześnie
        t = threading.Thread(target=flood_test)
        t.start()
        threads.append(t)
