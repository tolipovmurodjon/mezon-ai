"""Resumable crawl of every regulation.gov.uz draft page; local drafts also get their PDF text and entry-into-force class.

Run:   .venv/Scripts/python.exe -X utf8 -m mezon.sync.regulation_all   (set MEZON_CACHE to a drive with space)
Stop:  create data/store/regulation_all.STOP (the crawler exits after the current draft), or kill the PID in
       data/store/regulation_all.pid. Re-running resumes: ids already in the database are skipped.
"""

import datetime as dt
import gzip
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from mezon.config import ROOT, STORE
from research import polite_http
from research.regulation_window import (
    BASE,
    classify,
    clause_gap,
    ddmmyyyy,
    entry_into_force,
    is_local,
    parse_page,
    pin_dns,
)

DB = STORE / "regulation.sqlite"
LOG = ROOT / "data" / "interim" / "regulation_all.log"
STOP_FILE = STORE / "regulation_all.STOP"
PID_FILE = STORE / "regulation_all.pid"
NEWEST_GUESS = 118_200
FLOORS = (105_000, 95_000)
MIN_FREE_GB = 1.0
MISSES_TO_STOP_PROBE = 30
LOG_EVERY = 200

_STATUS = re.compile(r'class="dis_has_expired">\s*([^<]+?)\s*<')
_DOC_TYPE = re.compile(r'class="tab_content_in_title">\s*([^<]+?)\s*<')

SCHEMA = """
create table if not exists drafts(
  id integer primary key, creator text, is_local integer, doc_type text, title text, start text, end text,
  proposals integer, anti_corruption integer, gender integer, survey integer, status text, text text,
  eif_class text, eif_date text, clause_gap text, fetched_at text);
create table if not exists missing(id integer primary key, fetched_at text);
"""


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _gz_path(draft_id: int) -> Path:
    return polite_http.WRITE_CACHE / "regulation" / f"d{draft_id}.html.gz"


def page_html(draft_id: int) -> str:
    """The draft page, cache-first; after the first read the raw page is kept gzipped to save disk."""
    gz = _gz_path(draft_id)
    if gz.exists():
        return gzip.decompress(gz.read_bytes()).decode("utf-8", "replace")
    url, key = f"{BASE}/oz/d/{draft_id}", f"d{draft_id}.html"
    body = polite_http.fetch(url, source="regulation", key=key)
    raw = polite_http._path("regulation", key, url, None)
    if raw.exists() and raw.is_relative_to(polite_http.WRITE_CACHE) and raw.stat().st_size:
        gz.parent.mkdir(parents=True, exist_ok=True)
        gz.write_bytes(gzip.compress(body))
        raw.unlink()
    return body.decode("utf-8", "replace")


def _pdf_text(draft_id: int, pdf_id: str) -> str:
    name = f"d{draft_id}_{pdf_id}"
    for root in (polite_http.CACHE, polite_http.WRITE_CACHE):
        txt = root / "regulation" / f"{name}.txt"
        if txt.exists():
            return txt.read_text(encoding="utf-8", errors="replace")
    url, key = f"{BASE}/oz/download/get-pdf?id={pdf_id}&type=paragraph", f"{name}.pdf"
    body = polite_http.fetch(url, source="regulation", key=key)
    cached = polite_http._path("regulation", key, url, None)
    text = ""
    if body.startswith(b"%PDF"):
        with tempfile.TemporaryDirectory() as tmp:
            pdf, out = Path(tmp) / "d.pdf", Path(tmp) / "d.txt"
            pdf.write_bytes(body)
            subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(out)], check=False)
            if out.exists():
                text = out.read_text(encoding="utf-8", errors="replace")
    if cached.exists() and cached.is_relative_to(polite_http.WRITE_CACHE):
        cached.unlink()
    return text


def draft_text(draft_id: int, pdf_ids: list[str]) -> str:
    texts = []
    for pdf_id in pdf_ids[:2]:
        t = _pdf_text(draft_id, pdf_id)
        if t:
            texts.append(t)
            if entry_into_force(t)["kind"] != "none":
                break
    return "\n".join(texts)


def process(con: sqlite3.Connection, draft_id: int, today: dt.date) -> dict | None:
    """Fetch, parse and store one draft id; returns the stored row, or None when the id has no draft."""
    now = dt.datetime.now().isoformat(timespec="seconds")
    page = page_html(draft_id)
    rec = parse_page(page) if page else None
    if rec is None:
        con.execute("insert or replace into missing values(?,?)", (draft_id, now))
        return None
    local = is_local(rec["creator"])
    status_m, type_m = _STATUS.search(page), _DOC_TYPE.search(page)
    end = ddmmyyyy(rec["end"])
    status = status_m[1] if status_m else ("open" if end >= today else "closed")
    text, eif_class, eif_date, gap = None, None, None, None
    if local:
        text = draft_text(draft_id, rec["pdf_ids"])
        eif = entry_into_force(text)
        eif_class = classify(eif, end) if text else "no_text"
        eif_date = eif["date"].isoformat() if eif["date"] else None
        gap = clause_gap(text) if text else ""
    row = {
        "id": draft_id, "creator": rec["creator"], "is_local": int(local), "doc_type": type_m[1] if type_m else None,
        "title": rec["title"], "start": rec["start"], "end": rec["end"], "proposals": rec["proposals"],
        "anti_corruption": rec["anti_corruption"], "gender": rec["gender"], "survey": rec["survey"],
        "status": status, "text": text, "eif_class": eif_class, "eif_date": eif_date, "clause_gap": gap,
        "fetched_at": now,
    }
    con.execute(f"insert or replace into drafts values({','.join('?' * len(row))})", tuple(row.values()))
    return row


def _free_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free / 1e9


def _newest(con: sqlite3.Connection, today: dt.date) -> int:
    """Probe upward from the highest known id until a run of missing ids; returns the newest draft id."""
    known = con.execute("select max(id) from drafts").fetchone()[0] or NEWEST_GUESS
    i, misses, newest = max(known, NEWEST_GUESS), 0, known
    while misses < MISSES_TO_STOP_PROBE:
        if process(con, i, today):
            newest, misses = i, 0
        else:
            misses += 1
        con.commit()
        i += 1
    for j in range(newest + 1, i):
        con.execute("delete from missing where id=?", (j,))
    con.commit()
    return newest


def run() -> int:
    today = dt.date.today()
    STORE.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    STOP_FILE.unlink(missing_ok=True)
    pin_dns("regulation.gov.uz")
    con = connect()
    newest = _newest(con, today)
    done = {r[0] for r in con.execute("select id from drafts union select id from missing")}
    queue = [i for i in range(newest, FLOORS[1] - 1, -1) if i not in done]
    log(f"start: newest id {newest}, {len(done)} ids already done, {len(queue)} to go "
        f"(first {newest}..{FLOORS[0]}, then ..{FLOORS[1]}), cache {polite_http.WRITE_CACHE}")
    t0, n, local, errors, pauses = time.monotonic(), 0, 0, 0, 0
    for draft_id in queue:
        if STOP_FILE.exists():
            log("stop file found, exiting")
            break
        if n % 50 == 0 and (_free_gb(polite_http.WRITE_CACHE) < MIN_FREE_GB or _free_gb(STORE) < 0.3):
            log(f"low disk (cache {_free_gb(polite_http.WRITE_CACHE):.2f} GB, store {_free_gb(STORE):.2f} GB), exiting")
            break
        try:
            row = process(con, draft_id, today)
            errors = 0
        except RuntimeError as e:
            errors += 1
            log(f"error at {draft_id}: {e}")
            if errors >= 15:
                pauses += 1
                if pauses > 6:
                    log("too many network errors, exiting")
                    break
                log("15 errors in a row, pausing 5 min")
                time.sleep(300)
                errors = 0
            continue
        n += 1
        local += bool(row and row["is_local"])
        if n % 20 == 0:
            con.commit()
        if n % LOG_EVERY == 0:
            hours = (time.monotonic() - t0) / 3600
            rate = n / hours if hours else 0
            left = len(queue) - n
            log(f"id {draft_id}: {n} done this run, local {local}, {rate:.0f} ids/h, "
                f"ETA {left / rate:.1f} h for {left} ids" if rate else f"id {draft_id}: {n} done")
    con.commit()
    total = con.execute("select count(*), sum(is_local) from drafts").fetchone()
    log(f"end of run: {n} ids this run; database {total[0]} drafts, {total[1]} local")
    PID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
