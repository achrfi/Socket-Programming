# Client–Proxy–Server Socket Programming with TCP, UDP, and QoS Analysis

Implementasi sistem jaringan berbasis arsitektur Client–Proxy–Server menggunakan Python Socket Programming. Proyek ini dibuat untuk memenuhi Tugas Besar Mata Kuliah Jaringan Komputer Telkom University.

## 📌 Fitur

- Web Server berbasis TCP
- Proxy Server dengan mekanisme forwarding
- Proxy caching (Cache HIT & Cache MISS)
- HTTP GET Request handling
- UDP Echo Server
- Pengukuran QoS:
  - Round Trip Time (RTT)
  - Packet Loss
  - Jitter
  - Throughput
- Multithreading (Thread-per-Connection)
- Error Handling:
  - 404 Not Found
  - 403 Forbidden
  - 502 Bad Gateway
  - 504 Gateway Timeout

---

## 🏗️ Arsitektur Sistem

```text
Client
   |
   v
Proxy Server (TCP 8080)
   |
   v
Web Server (TCP 8000)

Client
   |
   +-------- UDP QoS Test -------->
                                  Web Server (UDP 9000)
```

Semua request HTTP wajib melewati Proxy Server sebelum mencapai Web Server.

---

## 📂 Struktur Project

```text
.
├── client.py
├── proxy.py
├── webserver.py
├── cache/
├── html/
└── README.md
```

---

## 🚀 Menjalankan Program

### 1. Jalankan Web Server

```bash
python webserver.py --host 0.0.0.0 --tcp 8000 --udp 9000
```

### 2. Jalankan Proxy Server

```bash
python proxy.py \
--host 0.0.0.0 \
--port 8080 \
--target-host <IP_SERVER> \
--target-port 8000
```

### 3. Jalankan Client TCP

```bash
python client.py tcp \
--proxy-host <IP_PROXY> \
--proxy-port 8080
```

### 4. Jalankan Pengujian QoS UDP

```bash
python client.py udp \
--web-host <IP_SERVER> \
--udp-port 9000 \
--count 10
```

---

## 🛠️ Teknologi

- Python 3
- Socket Programming
- TCP
- UDP
- Multithreading
- Wireshark

---

## 👥 Kelompok 2

| Nama | NIM | Tugas |
|--------|--------|--------|
| Achmad Rafi Dwiyandar | 103032400089 | Web Server |
| Fazli Rabbi | 103032400079 | Proxy Server |
| Sarah Nur Aqilah Tanjung | 103032430026 | Client |

---
