"""E-qaror list download through the page's own visible API (approved by Boss, 20-21 Nov 2026; seen in DevTools as
the call e-qaror.gov.uz/search makes): GET https://api-eqaror.gov.uz/v2/doc/list?<filter>&page=N&limit=20&lang=oz

    python -X utf8 -m research.eqaror_api run --workers 6          # priority slices first, then every page
    python -X utf8 -m research.eqaror_api status

One JSON file per (slice, page) under data/raw/eqaror_api/<slice>/p<N>.json; a re-run skips pages already saved.
Polite: each worker waits 1.2 s between its own requests (CLAUDE.md), backs off 30 s, 60 s, 120 s on 429/5xx or
errors. Max page size is 20 (the API returns 422 above it). The list carries metadata only (title, body, number,
type, normative flag, release status, code); individual-decision titles can contain citizens' names, which the
refinery masks before any training.
"""

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "eqaror_api"
API = "https://api-eqaror.gov.uz/v2/doc/list"
HEAD = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)", "Referer": "https://e-qaror.gov.uz/"}
SLICES = [("declared_invalid", {"release": 200}), ("normative", {"is_normative": 1}), ("kengash", {"document_type_id": 3}),
          ("kengash_rais", {"document_type_id": 12}), ("hokim_qaror", {"document_type_id": 1}), ("all", {})]
GAP = 1.2
_local = threading.local()


def client() -> httpx.Client:
    if not hasattr(_local, "c"):
        _local.c = httpx.Client(headers=HEAD, timeout=60)
    return _local.c


BRAKE = {"until": 0.0, "hits": 0}  # shared by all workers: any error or a page slower than 20 s pauses everyone 60 s


def brake(reason: str) -> None:
    BRAKE["until"] = max(BRAKE["until"], time.time() + 60)
    BRAKE["hits"] += 1
    print(f"BRAKE 60s ({reason}), total {BRAKE['hits']}", flush=True)


def get(params: dict) -> dict | None:
    for wait in (0, 30, 60, 120, 240):
        time.sleep(wait or GAP)
        while time.time() < BRAKE["until"]:
            time.sleep(1)
        t0 = time.time()
        try:
            r = client().get(f"{API}?{urlencode({**params, 'limit': 20, 'lang': 'oz'})}")
            if time.time() - t0 > 20:
                brake(f"slow page {time.time() - t0:.0f}s")
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                return {"_status": r.status_code, "_body": r.text[:200]}
            brake(f"HTTP {r.status_code}")
        except (httpx.HTTPError, ValueError) as e:
            brake(type(e).__name__)
    return None


def fetch_page(name: str, flt: dict, page: int) -> str:
    f = OUT / name / f"p{page}.json"
    if f.exists():
        return "skip"
    d = get({**flt, "page": page})
    if d is None:
        return "fail"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return "ok"


def run(workers: int) -> None:
    for name, flt in SLICES:
        (OUT / name).mkdir(parents=True, exist_ok=True)
        first = get({**flt, "page": 1})
        if not first or "data" not in first:
            print(f"{name}: no first page ({first})", flush=True)
            continue
        last = int(first["data"]["last_page"])
        (OUT / name / "p1.json").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: total {first['data']['total']} docs, {last} pages", flush=True)
        t0, c = time.time(), {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(workers) as pool:
            for n, res in enumerate(pool.map(lambda p, nm=name, fl=flt: fetch_page(nm, fl, p), range(2, last + 1)), 1):
                c[res] += 1
                if n % 200 == 0:
                    print(f"{name}: {n}/{last - 1} pages {c} {time.time() - t0:.0f}s", flush=True)
        print(f"{name} DONE {c} {time.time() - t0:.0f}s", flush=True)
    print("EQAROR_API_DONE", flush=True)


def status() -> None:
    for name, _ in SLICES:
        d = OUT / name
        files = list(d.glob("p*.json")) if d.exists() else []
        rows = 0
        for f in files:
            try:
                rows += len(json.loads(f.read_text(encoding="utf-8"))["data"]["list"])
            except (ValueError, KeyError, TypeError):
                pass
        print(f"{name:18} {len(files):6d} pages {rows:8d} rows")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6)
    else:
        status()
