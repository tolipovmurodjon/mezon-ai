"""Local receiver for the browser console scripts: Chrome (Boss's own session) POSTs JSON-line batches to
http://127.0.0.1:8765/put?name=<name>, and each batch is streamed straight to the Mezon box over ssh
(~/mezon/data/raw/browser/<name>.jsonl). Nothing is stored on the laptop (its disks are full).

    .venv/Scripts/python.exe -X utf8 -m research.browser_sink          # leave running while the console script runs

Listens on 127.0.0.1 only. Answers Chrome's private-network preflight so a page on https can reach localhost.
GET /status shows rows received per name.
"""

import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

HOST, PORT, BOX = "127.0.0.1", 8765, "mezon-gpu"
_pipes: dict[str, subprocess.Popen] = {}
_rows: dict[str, int] = {}
_lock = Lock()


def _pipe(name: str) -> subprocess.Popen:
    p = _pipes.get(name)
    if p is None or p.poll() is not None:
        remote = f"mkdir -p ~/mezon/data/raw/browser && cat >> ~/mezon/data/raw/browser/{name}.jsonl"
        p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", BOX, remote],
                             stdin=subprocess.PIPE)
        _pipes[name] = p
    return p


class H(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(repr(_rows).encode())

    def do_POST(self) -> None:
        name = "".join(ch for ch in parse_qs(urlparse(self.path).query).get("name", ["batch"])[0]
                       if ch.isalnum() or ch in "_-")[:60] or "batch"
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if body and not body.endswith(b"\n"):
            body += b"\n"
        with _lock:
            p = _pipe(name)
            p.stdin.write(body)
            p.stdin.flush()
            _rows[name] = _rows.get(name, 0) + body.count(b"\n")
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")
        print(f"{name}: +{body.count(b'\n')} rows (total {_rows[name]})", flush=True)

    def log_message(self, *a) -> None:
        pass


if __name__ == "__main__":
    print(f"browser sink on http://{HOST}:{PORT} -> {BOX}:~/mezon/data/raw/browser/", flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
