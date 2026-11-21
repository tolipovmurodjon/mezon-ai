"""Cache-first HTTP client, one request at a time, every response kept on disk.

Spacing: MEZON_HTTP_INTERVAL seconds (default 1.2; Boss approved 0.5 for the full lex.uz crawl on the box, 20.11.2026).
If the server answers 429 or 5xx, the spacing doubles for 10 minutes (and Retry-After is honoured), so a busy
server slows us down by itself. Never run several crawlers against one site to multiply the rate."""

import hashlib
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
# Where new responses are written; D: can be full, so MEZON_CACHE (or the machine-local data/cache_root.txt) may point
# elsewhere. Reads check both. Without it, texts cached elsewhere silently vanish from audits.
_ROOT_FILE = ROOT / "data" / "cache_root.txt"
WRITE_CACHE = Path(
    os.environ.get("MEZON_CACHE")
    or (_ROOT_FILE.read_text(encoding="utf-8").strip() if _ROOT_FILE.exists() else "")
    or CACHE
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MIN_INTERVAL = float(os.environ.get("MEZON_HTTP_INTERVAL", "1.2"))
_slow_until = 0.0  # while now < _slow_until, spacing is doubled (server said 429/5xx)

_last = 0.0
# MEZON_PROXY=socks5://127.0.0.1:1080 on the box = exit through the laptop (scripts/tunnel_box.sh), for Uzbek-only
# public sites. Needs the socksio package (httpx[socks]).
_client = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True,
                       proxy=os.environ.get("MEZON_PROXY") or None)


def _wait() -> None:
    global _last
    need = MIN_INTERVAL * (2 if time.monotonic() < _slow_until else 1)
    gap = time.monotonic() - _last
    if gap < need:
        time.sleep(need - gap)
    _last = time.monotonic()


def _path(source: str, key: str | None, url: str, data: dict | None) -> Path:
    if key is None:
        key = hashlib.sha1((url + repr(sorted((data or {}).items()))).encode()).hexdigest()[:16]
    primary = CACHE / source / key
    return primary if primary.exists() else WRITE_CACHE / source / key


def fetch(url: str, source: str, key: str | None = None, data: dict | None = None, retries: int = 3) -> bytes:
    """GET (or form POST when `data` is given) through the cache; raises after `retries` failures."""
    path = _path(source, key, url, data)
    if path.exists():
        return path.read_bytes()
    err: Exception | None = None
    for attempt in range(retries):
        _wait()
        try:
            r = _client.post(url, data=data) if data is not None else _client.get(url)
            if r.status_code == 404:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")
                return b""
            if r.status_code == 429 or r.status_code >= 500:
                global _slow_until
                _slow_until = time.monotonic() + 600
                wait = r.headers.get("Retry-After", "")
                time.sleep(min(int(wait), 300) if wait.isdigit() else 10 * (attempt + 1))
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return r.content
        except httpx.HTTPError as e:
            err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")
