import argparse
import socket
import statistics
import sys
import time

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
WEB_HOST = "127.0.0.1"
UDP_PORT = 9000
BUFFER_SIZE = 4096
TCP_TIMEOUT = 5
UDP_TIMEOUT = 1


def tcp_get(proxy_host, proxy_port, path):
    if not path.startswith("/"):
        path = "/" + path

    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {proxy_host}:{proxy_port}\r\n"
        "User-Agent: Python-Socket-Client/1.0\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("iso-8859-1")

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.settimeout(TCP_TIMEOUT)
    response = b""

    try:
        start = time.perf_counter()
        client_socket.connect((proxy_host, proxy_port))
        client_socket.sendall(request)

        while True:
            chunk = client_socket.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"[TCP] Request GET {path} via proxy {proxy_host}:{proxy_port}")
        print(f"[TCP] Response time: {elapsed_ms:.2f} ms")
        print("=" * 70)
        print(response.decode("utf-8", errors="replace"))
        print("=" * 70)
    finally:
        client_socket.close()


def calculate_jitter(rtts):
    """
    Jitter = standar deviasi dari selisih RTT berturut-turut: σ(RTTi − RTTi−1)
    Sesuai spesifikasi tubes (Figure 6, halaman 14).
    """
    if len(rtts) < 2:
        return 0.0
    differences = [rtts[i] - rtts[i - 1] for i in range(1, len(rtts))]
    return statistics.stdev(differences)


def udp_qos(web_host, udp_port, count, timeout):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(timeout)

    rtts = []
    sent_packets = 0
    received_packets = 0
    total_received_bytes = 0
    test_start = time.perf_counter()

    print(f"[UDP] QoS test ke {web_host}:{udp_port}, jumlah paket={count}, timeout={timeout:.2f}s")

    try:
        for seq in range(1, count + 1):
            send_timestamp = time.time()
            payload = f"Ping {seq} {send_timestamp}"
            data = payload.encode("utf-8")

            sent_packets += 1
            send_perf = time.perf_counter()
            udp_socket.sendto(data, (web_host, udp_port))

            try:
                response, _addr = udp_socket.recvfrom(BUFFER_SIZE)
                recv_perf = time.perf_counter()
                rtt_ms = (recv_perf - send_perf) * 1000
                rtts.append(rtt_ms)
                received_packets += 1
                total_received_bytes += len(response)

                response_text = response.decode("utf-8", errors="replace")
                print(f"Reply from {web_host}: seq={seq} RTT={rtt_ms:.2f} ms payload='{response_text}'")
            except socket.timeout:
                print(f"Request timed out: seq={seq}")

            time.sleep(0.1)
    finally:
        udp_socket.close()

    test_duration = max(time.perf_counter() - test_start, 0.000001)
    lost_packets = sent_packets - received_packets
    packet_loss = (lost_packets / sent_packets) * 100 if sent_packets else 0.0

    # Throughput: total payload berhasil diterima / durasi pengujian (dalam kbps)
    throughput_kbps = (total_received_bytes * 8) / (test_duration * 1000)

    print("\nStatistik QoS UDP")
    print("-" * 70)
    print(f"Packets: Sent={sent_packets}, Received={received_packets}, Lost={lost_packets}")
    print(f"Packet loss: {packet_loss:.2f}%")

    if rtts:
        print(f"RTT minimum: {min(rtts):.2f} ms")
        print(f"RTT average: {statistics.mean(rtts):.2f} ms")
        print(f"RTT maximum: {max(rtts):.2f} ms")
        print(f"Jitter: {calculate_jitter(rtts):.2f} ms")
    else:
        print("RTT minimum: -")
        print("RTT average: -")
        print("RTT maximum: -")
        print("Jitter: -")

    print(f"Throughput UDP diterima: {throughput_kbps:.2f} kbps")


def parse_args():
    parser = argparse.ArgumentParser(description="Client TCP HTTP via Proxy dan UDP QoS berbasis socket manual")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    tcp_parser = subparsers.add_parser("tcp", help="Mode TCP/HTTP: GET ke proxy")
    tcp_parser.add_argument("--proxy-host", default=PROXY_HOST, help="Host proxy, default 127.0.0.1")
    tcp_parser.add_argument("--proxy-port", type=int, default=PROXY_PORT, help="Port proxy, default 8080")
    tcp_parser.add_argument("--path", default="/", help="Path file yang diminta, contoh /index.html")

    udp_parser = subparsers.add_parser("udp", help="Mode UDP/QoS: ping UDP ke web server")
    udp_parser.add_argument("--web-host", default=WEB_HOST, help="Host web server UDP, default 127.0.0.1")
    udp_parser.add_argument("--udp-port", type=int, default=UDP_PORT, help="Port UDP echo web server, default 9000")
    udp_parser.add_argument("--count", type=int, default=10, help="Jumlah paket UDP, minimal 10 sesuai instruksi")
    udp_parser.add_argument("--timeout", type=float, default=UDP_TIMEOUT, help="Timeout per paket, default 1 detik")

    return parser.parse_args()


def main():
    args = parse_args()

    try:
        if args.mode == "tcp":
            tcp_get(args.proxy_host, args.proxy_port, args.path)
        elif args.mode == "udp":
            count = max(args.count, 10)
            timeout = min(args.timeout, 1.0)
            udp_qos(args.web_host, args.udp_port, count, timeout)
        else:
            print("Mode tidak dikenal", file=sys.stderr)
            sys.exit(1)
    except ConnectionRefusedError:
        print("Koneksi ditolak. Pastikan server/proxy sudah berjalan.", file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print("Koneksi timeout.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nDihentikan oleh user.")


if __name__ == "__main__":
    main()
