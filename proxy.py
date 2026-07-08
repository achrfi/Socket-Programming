import argparse
import os
import socket
import threading
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

HOST = "0.0.0.0"
PROXY_PORT = 8080
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 8000
BUFFER_SIZE = 4096
CLIENT_TIMEOUT = 5   # timeout menunggu request dari client
SERVER_TIMEOUT = 5   # timeout menunggu balasan dari web server
CACHE_DIR = "cache"

shutdown_event = threading.Event()


def log(message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    thread_name = threading.current_thread().name
    print(f"[{ts}] [{thread_name}] {message}", flush=True)


def build_response(status_code, reason, body=b"", content_type="text/plain; charset=utf-8"):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        "Server: Python-Socket-Proxy",
        f"Content-Length: {len(body)}",
        f"Content-Type: {content_type}",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("iso-8859-1") + body


def read_http_request(conn):
    conn.settimeout(CLIENT_TIMEOUT)  # <-- pakai CLIENT_TIMEOUT
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data


def get_cache_path(request_path, cache_dir):
    """Petakan path URL ke file cache, dengan proteksi path traversal."""
    path = unquote(urlsplit(request_path).path)
    if path == "/":
        path = "/index.html"

    normalized = os.path.normpath(path.lstrip("/"))
    full_path = os.path.abspath(os.path.join(cache_dir, normalized))
    cache_dir_abs = os.path.abspath(cache_dir)

    if not full_path.startswith(cache_dir_abs + os.sep) and full_path != cache_dir_abs:
        return None
    return full_path


def forward_to_server(request_data, target_host, target_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SERVER_TIMEOUT)  # <-- pakai SERVER_TIMEOUT
    try:
        s.connect((target_host, target_port))
        s.sendall(request_data)
        response = b""
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk
        return response
    finally:
        s.close()


def get_status_code(response, default):
    try:
        return int(response.split(b"\r\n", 1)[0].split()[1])
    except Exception:
        return default


def handle_client(conn, addr, target_host, target_port, cache_dir):
    client_ip, client_port = addr
    request_path = "-"
    cache_status = "-"
    status_code = 500

    start = time.perf_counter()
    try:
        request_data = read_http_request(conn)
        if not request_data:
            return

        try:
            request_line = request_data.decode("iso-8859-1").split("\r\n", 1)[0]
            parts = request_line.split()
        except Exception:
            parts = []

        if len(parts) < 3:
            status_code = 400
            conn.sendall(build_response(400, "Bad Request", "Request tidak valid.\n"))
            return

        method, request_path = parts[0], parts[1]

        if method.upper() != "GET":
            status_code = 405
            conn.sendall(build_response(405, "Method Not Allowed", "Hanya GET yang didukung.\n"))
            return

        cache_file = get_cache_path(request_path, cache_dir)
        if cache_file is None:
            status_code = 403
            conn.sendall(build_response(403, "Forbidden", "Path tidak diizinkan.\n"))
            return

        # Cache HIT
        if os.path.isfile(cache_file):
            cache_status = "HIT"
            with open(cache_file, "rb") as f:
                response = f.read()
            status_code = get_status_code(response, 200)
            conn.sendall(response)
            return

        # Cache MISS -> forward ke web server
        cache_status = "MISS"
        try:
            response = forward_to_server(request_data, target_host, target_port)
        except socket.timeout:
            status_code = 504
            conn.sendall(build_response(504, "Gateway Timeout", "Web server tidak merespons.\n"))
            return
        except OSError as exc:
            status_code = 502
            conn.sendall(build_response(502, "Bad Gateway", f"Tidak dapat menghubungi web server: {exc}\n"))
            return

        status_code = get_status_code(response, 502)
        if status_code == 200:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "wb") as f:
                f.write(response)

        conn.sendall(response)

    except Exception as exc:
        status_code = 500
        try:
            conn.sendall(build_response(500, "Internal Server Error", f"Terjadi error: {exc}\n"))
        except Exception:
            pass
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log(f"Client {client_ip}:{client_port} path={request_path} cache={cache_status} status={status_code} time={elapsed_ms:.2f}ms")
        try:
            conn.close()
        except Exception:
            pass


def tcp_proxy_server(host, port, target_host, target_port, cache_dir):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(50)
    server_socket.settimeout(1)

    log(f"Proxy Server aktif di {host}:{port}, target={target_host}:{target_port}")

    try:
        while not shutdown_event.is_set():
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=handle_client,
                args=(conn, addr, target_host, target_port, cache_dir),
                name=f"PROXY-{addr[0]}:{addr[1]}",
                daemon=True,
            ).start()
    finally:
        server_socket.close()
        log("Proxy Server berhenti")


def parse_args():
    parser = argparse.ArgumentParser(description="Proxy Server: forwarding + caching")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PROXY_PORT)
    parser.add_argument("--target-host", default=TARGET_HOST)
    parser.add_argument("--target-port", type=int, default=TARGET_PORT)
    parser.add_argument("--cache-dir", default=CACHE_DIR)
    return parser.parse_args()


def main():
    args = parse_args()
    cache_dir = os.path.abspath(args.cache_dir)
    os.makedirs(cache_dir, exist_ok=True)
    try:
        tcp_proxy_server(args.host, args.port, args.target_host, args.target_port, cache_dir)
    except KeyboardInterrupt:
        log("Menerima Ctrl+C, menghentikan proxy...")
        shutdown_event.set()


if __name__ == "__main__":
    main()