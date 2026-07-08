import argparse
import mimetypes
import os
import socket
import sys
import threading
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

#TCP_HOST = "0.0.0.0"
#TCP_PORT = 8000
#UDP_HOST = "0.0.0.0"
# Fallback default, hanya untuk HOST dan UDP
HOST = "0.0.0.0"
UDP_PORT = 9000
BUFFER_SIZE = 4096
REQUEST_TIMEOUT = 5

shutdown_event = threading.Event()

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message):
    thread_name = threading.current_thread().name
    print(f"[{timestamp()}] [{thread_name}] {message}", flush=True)

def build_response(status_code, reason, body=b"", content_type="text/plain; charset=utf-8"):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        "Server: Python-Socket-WebServer",
        f"Content-Length: {len(body)}",
        f"Content-Type: {content_type}",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("iso-8859-1") + body

def read_http_request(conn):
    conn.settimeout(REQUEST_TIMEOUT)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data

def safe_file_path(request_path, web_root):
    split_path = urlsplit(request_path)
    path = unquote(split_path.path)

    if path == "/":
        path = "/index.html"

    normalized = os.path.normpath(path.lstrip("/"))
    full_path = os.path.abspath(os.path.join(web_root, normalized))
    web_root_abs = os.path.abspath(web_root)

    if not full_path.startswith(web_root_abs + os.sep) and full_path != web_root_abs:
        return None

    return full_path

def handle_tcp_client(conn, addr, web_root):
    client_ip, client_port = addr
    request_path = "-"
    status_code = 500

    try:
        request_data = read_http_request(conn)
        if not request_data:
            return

        try:
            request_text = request_data.decode("iso-8859-1")
            request_line = request_text.split("\r\n", 1)[0]
            parts = request_line.split()
        except Exception:
            response = build_response(500, "Internal Server Error", "Gagal membaca HTTP request.\n")
            status_code = 500
            conn.sendall(response)
            return

        if len(parts) < 3:
            response = build_response(500, "Internal Server Error", "Format HTTP request tidak valid.\n")
            status_code = 500
            conn.sendall(response)
            return

        method, request_path, _version = parts[0], parts[1], parts[2]

        if method.upper() != "GET":
            response = build_response(405, "Method Not Allowed", "Hanya metode GET yang didukung.\n")
            status_code = 405
            conn.sendall(response)
            return

        file_path = safe_file_path(request_path, web_root)
        if file_path is None:
            body = "403 Forbidden\nAkses path tidak diizinkan.\n"
            response = build_response(403, "Forbidden", body)
            status_code = 403
            conn.sendall(response)
            return

        if not os.path.isfile(file_path):
            body = f"404 Not Found\nFile {urlsplit(request_path).path} tidak ditemukan.\n"
            response = build_response(404, "Not Found", body)
            status_code = 404
            conn.sendall(response)
            return

        try:
            with open(file_path, "rb") as f:
                body = f.read()
            content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            response = build_response(200, "OK", body, content_type)
            status_code = 200
            conn.sendall(response)
        except Exception as exc:
            body = f"500 Internal Server Error\n{exc}\n"
            response = build_response(500, "Internal Server Error", body)
            status_code = 500
            conn.sendall(response)

    except socket.timeout:
        status_code = 500
        try:
            conn.sendall(build_response(500, "Internal Server Error", "Request timeout di web server.\n"))
        except Exception:
            pass
    except Exception as exc:
        status_code = 500
        try:
            conn.sendall(build_response(500, "Internal Server Error", f"Terjadi error: {exc}\n"))
        except Exception:
            pass
    finally:
        log(f"TCP request dari {client_ip}:{client_port} path={request_path} status={status_code}")
        try:
            conn.close()
        except Exception:
            pass

def tcp_server(host, port, web_root):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(50)
    server_socket.settimeout(1)

    log(f"TCP HTTP Server aktif di {host}:{port}, web_root={os.path.abspath(web_root)}")

    try:
        while not shutdown_event.is_set():
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            # Multithreading
            thread = threading.Thread(
                target=handle_tcp_client,
                args=(conn, addr, web_root),
                name=f"TCP-{addr[0]}:{addr[1]}",
                daemon=True,
            )
            thread.start()
    finally:
        server_socket.close()
        log("TCP HTTP Server berhenti")

def udp_echo_server(host, port):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.bind((host, port))
    udp_socket.settimeout(1)

    log(f"UDP Echo Server aktif di {host}:{port}")

    try:
        while not shutdown_event.is_set():
            try:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            udp_socket.sendto(data, addr)
            payload_preview = data.decode("utf-8", errors="replace")[:80]
            log(f"UDP echo ke {addr[0]}:{addr[1]} size={len(data)} payload='{payload_preview}'")
    finally:
        udp_socket.close()
        log("UDP Echo Server berhenti")

# Parser, untuk menentukan usage perintah (mis. py webserver.py --tcp 8000)
def parse_args():
    parser = argparse.ArgumentParser(description="Web Server TCP HTTP + UDP Echo berbasis socket manual")
    parser.add_argument("--host", required=True, default=HOST, help="Host TCP dan UDP, default 0.0.0.0")
    parser.add_argument("--tcp", type=int, required=True, help="Port TCP HTTP, default 8000")
    parser.add_argument("--udp", type=int, default=UDP_PORT, help="Port UDP Echo, default 9000")
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)), help="Folder asset web")
    return parser.parse_args()

def main():
    args = parse_args()
    web_root = os.path.abspath(args.root)
    
    if not os.path.isdir(web_root):
        print(f"Folder web root tidak ditemukan: {web_root}", file=sys.stderr)
        sys.exit(1)

    tcp_thread = threading.Thread(target=tcp_server, args=(args.host, args.tcp, web_root), name="TCP-Main", daemon=True)
    udp_thread = threading.Thread(target=udp_echo_server, args=(args.host, args.udp), name="UDP-Main", daemon=True)

    tcp_thread.start()
    udp_thread.start()

    log("Tekan Ctrl+C untuk menghentikan server")
    try:
        while True:
            tcp_thread.join(timeout=1)
            udp_thread.join(timeout=1)
            if not tcp_thread.is_alive() or not udp_thread.is_alive():
                break
    except KeyboardInterrupt:
        log("Menerima Ctrl+C, menghentikan server...")
        shutdown_event.set()
        tcp_thread.join(timeout=2)
        udp_thread.join(timeout=2)

if __name__ == "__main__":
    main()
