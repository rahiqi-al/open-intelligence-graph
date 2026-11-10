import socket
import sys
import urllib.request

HTTP = {
    "qdrant": "http://localhost:6333/healthz",
    "minio": "http://localhost:9000/minio/health/live",
    "neo4j": "http://localhost:7474",
}
TCP = {"postgres": ("localhost", 5432), "neo4j-bolt": ("localhost", 7687)}


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status < 400
    except Exception:
        return False


def tcp_ok(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


failed = 0
for name, url in HTTP.items():
    ok = http_ok(url)
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name:12} {url}")
for name, (h, p) in TCP.items():
    ok = tcp_ok(h, p)
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name:12} {h}:{p}")
sys.exit(1 if failed else 0)