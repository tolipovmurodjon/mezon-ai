"""E-qaror decision-text download through the page's own public XHR (approved 20-21 Nov 2026, see CLAUDE.md and
docs/research/eqaror_text_access.md): GET https://api-eqaror.gov.uz/v2/doc/show?code=<32hex>&lang=oz  -> text PDF.

    python -X utf8 -m research.eqaror_text run [--workers 3] [--limit N]
    python -X utf8 -m research.eqaror_text status

Codes come from the list files research/eqaror_api.py saved (data/raw/eqaror_api/<slice>/p*.json). State is
data/raw/eqaror_text/state.sqlite (code, slice, status todo/ok/empty/fail, http, chars, fetched_at); only todo rows
run, so it resumes. Touch data/raw/eqaror_text/STOP to pause. ONE shared 1.2 s gate for all workers, 60 s brake on
429/5xx/timeouts or a low X-RateLimit-Remaining. Any captcha / PoW / Turnstile / challenge: write STOP and exit (never
solve). Text goes to data/cache/eqaror_text/<code[:2]>/<code>.txt.gz (pdftotext -enc UTF-8 -layout, via an ASCII temp
name); the PDF is deleted unless the text is < 200 chars (scan): then it is kept under data/raw/eqaror_text/scans/ for OCR.
PRIVACY: individual decisions contain citizens' names. Private cache only, never git; mask before any training/publishing.
"""

import gzip
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "eqaror_text"
LIST = ROOT / "data" / "raw" / "eqaror_api"
CACHE = Path(os.environ.get("MEZON_CACHE_TEXT", ROOT / "data" / "cache" / "eqaror_text"))
API = "https://api-eqaror.gov.uz/v2/doc/show"
HEAD = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)", "Referer": "https://e-qaror.gov.uz/"}
SLICES = ["declared_invalid", "normative", "kengash", "kengash_rais", "hokim_qaror"]
GAP = 1.2
MIN_CHARS = 200
LOW_REMAINING = 10
CHALLENGE = re.compile(r"captcha|turnstile|challenge|cf-chl|just a moment|proof.of.work", re.I)


# ---- pure helpers (tested without network) ----
def text_path(code: str, root: Path = CACHE) -> Path:
    return root / code[:2] / f"{code}.txt.gz"


def pdf_tmp_name(code: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]", "", code)[:40] + ".pdf"


def is_scan(text: str) -> bool:
    return len(text.strip()) < MIN_CHARS


def save_text(code: str, text: str, root: Path = CACHE) -> Path:
    p = text_path(code, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(text)
    return p


def load_text(code: str, root: Path = CACHE) -> str | None:
    p = text_path(code, root)
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return f.read()


def page_no(p: Path) -> int:
    m = re.search(r"p(\d+)\.json$", p.name)
    return int(m.group(1)) if m else 0


def list_codes(slice_name: str, base: Path = LIST):
    d = base / slice_name
    for f in sorted(d.glob("p*.json"), key=page_no) if d.exists() else []:
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))["data"]["list"]
        except (ValueError, KeyError, TypeError):
            continue
        for r in rows:
            c = r.get("code")
            if c and re.fullmatch(r"[0-9a-f]{32}", c):
                yield c, bool(r.get("is_hidden"))


# ---- state ----
def db() -> sqlite3.Connection:
    RAW.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(RAW / "state.sqlite", timeout=60, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS docs(code TEXT PRIMARY KEY, slice TEXT, ord INTEGER, status TEXT, http INTEGER,
                 chars INTEGER, fetched_at TEXT, hidden INTEGER DEFAULT 0)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix ON docs(status, ord)")
    return c


def load_todo(c: sqlite3.Connection) -> None:
    n = c.execute("SELECT COALESCE(MAX(ord),0) FROM docs").fetchone()[0]
    for s in SLICES:
        for code, hidden in list_codes(s):
            n += 1
            c.execute("INSERT OR IGNORE INTO docs(code,slice,ord,status,hidden) VALUES(?,?,?,'todo',?)", (code, s, n, int(hidden)))
    c.commit()


# ---- fetch ----
GATE = {"next": 0.0, "lock": threading.Lock()}
BRAKE = {"until": 0.0, "hits": 0}
STOPPED = threading.Event()
_local = threading.local()


def client():
    import httpx
    if not hasattr(_local, "c"):
        _local.c = httpx.Client(headers=HEAD, timeout=90)
    return _local.c


def brake(reason: str) -> None:
    BRAKE["until"] = max(BRAKE["until"], time.time() + 60)
    BRAKE["hits"] += 1
    print(f"BRAKE 60s ({reason}), total {BRAKE['hits']}", flush=True)


def gate() -> None:
    """One shared 1.2 s slot for every request of every worker."""
    while True:
        while time.time() < BRAKE["until"]:
            time.sleep(1)
        with GATE["lock"]:
            now = time.time()
            if now >= GATE["next"] and now >= BRAKE["until"]:
                GATE["next"] = now + GAP
                return
            wait = max(GATE["next"] - now, 0.05)
        time.sleep(min(wait, 1))


def stop_requested() -> bool:
    return (RAW / "STOP").exists() or STOPPED.is_set()


def pdf_text(pdf: Path) -> str:
    out = pdf.with_suffix(".txt")
    subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(out)], check=True, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = out.read_text(encoding="utf-8", errors="replace")
    out.unlink(missing_ok=True)
    return t


def fetch_one(code: str) -> tuple[str, int, int]:
    """-> (status, http, chars). status 'todo' means: not done (stopped / challenge), leave the row alone."""
    import httpx
    tmp = Path(tempfile.gettempdir()) / "eqtext"
    tmp.mkdir(exist_ok=True)
    pdf = tmp / pdf_tmp_name(code)
    for wait in (0, 30, 60, 120, 240):
        if stop_requested():
            return "todo", 0, 0
        if wait:
            time.sleep(wait)
        gate()
        t0 = time.time()
        try:
            r = client().get(API, params={"code": code, "lang": "oz"})
        except httpx.HTTPError as e:
            brake(type(e).__name__)
            continue
        if time.time() - t0 > 20:
            brake(f"slow {time.time() - t0:.0f}s")
        rem = r.headers.get("X-RateLimit-Remaining")
        if rem is not None and rem.isdigit() and int(rem) < LOW_REMAINING:
            brake(f"RateLimit-Remaining {rem}")
        ctype = r.headers.get("content-type", "")
        if r.status_code in (429, 500, 502, 503, 504):
            brake(f"HTTP {r.status_code}")
            continue
        if "pdf" not in ctype:
            if CHALLENGE.search(r.text[:2000]) or CHALLENGE.search(str(r.headers)):
                (RAW / "STOP").write_text("challenge seen: stop and report, never solve\n")
                STOPPED.set()
                print(f"CHALLENGE detected (HTTP {r.status_code}); STOP written", flush=True)
                return "todo", r.status_code, 0
            return "fail", r.status_code, 0
        pdf.write_bytes(r.content)
        try:
            text = pdf_text(pdf)
        except Exception as e:  # noqa: BLE001
            print(f"pdftotext failed {code}: {type(e).__name__}", flush=True)
            pdf.unlink(missing_ok=True)
            return "fail", 200, 0
        if is_scan(text):
            sc = RAW / "scans"
            sc.mkdir(parents=True, exist_ok=True)
            pdf.replace(sc / f"{code}.pdf")
            return "empty", 200, len(text.strip())
        pdf.unlink(missing_ok=True)
        save_text(code, text)
        return "ok", 200, len(text)
    return "fail", 0, 0


def run(workers: int, limit: int | None) -> None:
    c = db()
    load_todo(c)
    lock = threading.Lock()
    done = {"n": 0}
    t0 = time.time()

    def work(code: str) -> None:
        if stop_requested():
            return
        st, http, chars = fetch_one(code)
        if st == "todo":
            return
        with lock:
            c.execute("UPDATE docs SET status=?, http=?, chars=?, fetched_at=datetime('now') WHERE code=?", (st, http, chars, code))
            c.commit()
            done["n"] += 1
            if done["n"] % 50 == 0:
                print(f"{done['n']} done, {done['n'] / (time.time() - t0):.2f} doc/s", flush=True)

    while not stop_requested():
        rows = [r[0] for r in c.execute("SELECT code FROM docs WHERE status='todo' ORDER BY ord LIMIT ?", (limit or 300,))]
        if not rows:
            break
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(work, rows))
        if limit:
            break
    print("EQTEXT_STOPPED" if stop_requested() else "EQTEXT_DONE", flush=True)


def status() -> None:
    c = db()
    print(f"{'slice':18}{'todo':>8}{'ok':>8}{'empty':>8}{'fail':>8}{'total':>8}")
    for s in SLICES:
        d = dict(c.execute("SELECT status, COUNT(*) FROM docs WHERE slice=? GROUP BY status", (s,)).fetchall())
        print(f"{s:18}{d.get('todo', 0):8}{d.get('ok', 0):8}{d.get('empty', 0):8}{d.get('fail', 0):8}{sum(d.values()):8}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        a = sys.argv
        run(int(a[a.index("--workers") + 1]) if "--workers" in a else 3, int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    else:
        status()
