"""E-qaror-respublika (ministry and agency orders) list download through the page's own visible API, seen in Chrome as
the call e-qaror-respublika.gov.uz makes: GET https://e-res.ecdn.uz/v2/documents?page=N&limit=100

    python -X utf8 -m research.eqaror_resp_api run --workers 4
    python -X utf8 -m research.eqaror_resp_api status

60,762 documents on 21 Nov 2026 (24,904 open, 35,858 hidden), 352 organizations. One JSON file per page under
data/raw/eqaror_resp_api/; a re-run skips saved pages. Each worker waits 1.2 s between its requests and backs off on
errors. Metadata only (title, number, organization, type, status, approval date, code); hidden documents have no text
in the list.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("EQR_OUT", ROOT / "data" / "raw" / "eqaror_resp_api"))  # EQR_OUT: a 2nd pass dir (pagination drift)
API = "https://e-res.ecdn.uz/v2"
HEAD = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)", "Referer": "https://e-qaror-respublika.gov.uz/"}


def get(url: str) -> dict | None:
    for wait in (1.2, 30, 60, 120):
        time.sleep(wait)
        try:
            r = httpx.get(url, headers=HEAD, timeout=60)
            if r.status_code == 200:
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
    return None


def page(n: int) -> str:
    f = OUT / f"p{n}.json"
    if f.exists():
        return "skip"
    d = get(f"{API}/documents?page={n}&limit=100")
    if not d or not d.get("success"):
        return "fail"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return "ok"


def run(workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("statistics/general-statistics", "documents/types", "authority/category"):
        d = get(f"{API}/{name}")
        if d:
            (OUT / f"_{name.replace('/', '_')}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    first = get(f"{API}/documents?page=1&limit=100")
    last = int(first["data"]["meta"]["last_page"])
    (OUT / "p1.json").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    print(f"total {first['data']['meta']['total']} docs, {last} pages", flush=True)
    c = {"ok": 0, "skip": 0, "fail": 0}
    with ThreadPoolExecutor(workers) as pool:
        for res in pool.map(page, range(2, last + 1)):
            c[res] += 1
    print(f"EQAROR_RESP_DONE {c}", flush=True)


def status() -> None:
    rows = sum(len(json.loads(f.read_text(encoding="utf-8"))["data"]["items"]) for f in OUT.glob("p*.json"))
    print(f"{len(list(OUT.glob('p*.json')))} pages, {rows} rows")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4)
    else:
        status()
