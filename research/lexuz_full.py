"""The whole of lex.uz, politely: every act, every edition, both scripts, its files and annex images. Box only (1 TB).

    python -X utf8 -m research.lexuz_full seed        # build the queue (cache, store, RSS, open-corpus ids)
    python -X utf8 -m research.lexuz_full run         # crawl; resumable, rerun to continue
    python -X utf8 -m research.lexuz_full status      # exact counts
    touch data/raw/lexuz_full/STOP                    # pause cleanly after the current act

One request at a time through research/polite_http.py (cache-first, ~1.2 s spacing, 404s cached), so a rerun never
refetches. Per act: the current page, every edition page (?ONDATE=), the amending/cited/citing panels, every
/uz/files/ ZIP or PDF it links, and every content image. New act ids found in any link join the queue (breadth first),
so the crawl walks the whole law graph. Latin (x) and Cyrillic (-x) versions are both fetched. Public pages only:
never a login, never a bot check, never another site. Stops by itself when the disk has under MIN_FREE_GB left.
"""

import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from mezon.lawstore import fetch as lx
from research.polite_http import fetch

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "raw" / "lexuz_full"
DB = DIR / "state.sqlite"
STOP = DIR / "STOP"
MIN_FREE_GB = float(os.environ.get("MEZON_MIN_FREE_GB", "25"))  # laptop: 4
DOC_LINK = re.compile(r'href="(?:https?://lex\.uz)?/(?:uz|ru|oz|en)/docs/(-?\d+)')
FILE_LINK = re.compile(r'href="(/(?:uz|ru|oz)/files/-?\d+\.(?:zip|pdf|docx?|xlsx?|rtf))"', re.IGNORECASE)
IMG = re.compile(r'<img[^>]+src="(/[^"]+)"', re.IGNORECASE)
UI_IMG = re.compile(r"^/(img|image|images/icons|assets|Content|bundles|plugins)/", re.IGNORECASE)


def connect() -> sqlite3.Connection:
    DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS acts(lex_id TEXT PRIMARY KEY, prio INTEGER, status TEXT DEFAULT 'todo',
      title TEXT, editions INTEGER, files INTEGER, images INTEGER, links INTEGER, done_at TEXT);
    CREATE INDEX IF NOT EXISTS acts_todo ON acts(status, prio);
    """)
    return con


def add(con: sqlite3.Connection, ids, prio: int, twins: bool = True) -> int:
    """Queue ids. twins=True also queues the other-sign id (Uzbek Cyrillic <-> Latin twin; Russian and English ids
    have no twin, so ids from the official catalog are queued without guessing)."""
    before = con.total_changes
    for i in ids:
        i = str(i).strip()
        if re.fullmatch(r"-?\d{3,9}", i):
            rows = [(i, prio)] + ([(i[1:] if i.startswith("-") else f"-{i}", prio + 1)] if twins else [])
            con.executemany("INSERT OR IGNORE INTO acts(lex_id, prio) VALUES(?,?)", rows)
            if not twins:  # a catalog id is real: raise it to this priority if it was queued lower as a guess
                con.execute(
                    "UPDATE acts SET prio=? WHERE lex_id=? AND prio>? AND status='todo'", (prio, i, prio)
                )
    con.commit()
    return con.total_changes - before


def seed(con: sqlite3.Connection) -> None:
    from mezon.lawstore.build import CORE

    n = add(con, [c[2] for c in CORE if c[2].lstrip("-").isdigit()], 0)
    cache = ROOT / "data" / "cache" / "lexuz" / "docs"
    n += add(
        con,
        [f"{'-' if p.stem.endswith('_m') else ''}{p.stem.split('_')[0]}" for p in cache.glob("*.html")]
        if cache.exists()
        else [],
        1,
    )
    try:
        from mezon.decisions.store import DecisionStore

        urls = [
            u for (u,) in DecisionStore().con.execute("SELECT url FROM decisions WHERE url LIKE '%lex.uz%'")
        ]
        n += add(con, [m.group(1) for u in urls if (m := re.search(r"/docs/(-?\d+)", u))], 2)
    except Exception as e:  # noqa: BLE001 - the store is optional on a fresh box
        print("decision store skipped:", e)
    rss = fetch("https://lex.uz/uz/rss", "lexuz", key=f"rss/{time.strftime('%Y-%m-%d')}.xml").decode(
        "utf-8", "replace"
    )
    n += add(con, re.findall(r"/docs/(-?\d+)", rss), 1)
    hf = ROOT / "data" / "raw" / "hf"
    try:
        import pyarrow.parquet as pq

        for f in hf.rglob("*.parquet"):
            t = pq.read_table(f)
            for col in t.column_names:
                vals = [str(v) for v in t.column(col).to_pylist()[:50000] if v is not None]
                ids = [
                    m.group(1) for v in vals if (m := re.search(r"lex\.uz/(?:uz|ru|oz|en)/docs/(-?\d+)", v))
                ]
                if not ids and re.search(r"(lex|doc)_?id", col, re.IGNORECASE):
                    ids = [v for v in vals if re.fullmatch(r"-?\d{3,9}", v)]
                n += add(con, ids, 2)
    except ImportError:
        print("pyarrow missing: open-corpus ids skipped (uv add pyarrow)")
    print(f"seeded {n} new queue rows; total {con.execute('SELECT count(*) FROM acts').fetchone()[0]}")


def _get(path: str, key: str) -> bytes:
    return fetch(f"{lx.BASE}{path}", "lexuz", key=key)


def crawl_one(con: sqlite3.Connection, lex_id: str, level: int = 1) -> None:
    """Pass 1: page, every edition, amendment history, legal-analysis card 1, files, images.
    Pass 2: cites / cited-by panels, card 2, basrev, the official-publication page and the PDF of the document."""
    page = lx.doc_page(lex_id)
    if not page:
        con.execute("UPDATE acts SET status='missing', done_at=datetime('now') WHERE lex_id=?", (lex_id,))
        return
    n = lex_id.lstrip("-") if not lex_id.startswith("-") else lex_id
    pages = [page]
    eds: list[str] = []
    if level == 1:
        eds = sorted(lx.edition_dates(page, lex_id) | {f"{d} 00" for d in lx.amendment_dates(page)})
        for ondate in eds:
            if p := lx.edition_page(lex_id, ondate):
                pages.append(p)
        pages.append(lx.relation_page(lex_id, "revhis"))
        pages.append(
            _get(
                f"/uz/actinfo/card1/{n}",
                f"actinfo/card1/{lex_id.lstrip('-')}_{'m' if lex_id.startswith('-') else 'p'}.html",
            ).decode("utf-8", "replace")
        )
    else:
        for panel in ("correspondents", "respondents"):
            pages.append(lx.relation_page(lex_id, panel))
        tag = f"{lex_id.lstrip('-')}_{'m' if lex_id.startswith('-') else 'p'}"
        for path, key in (
            (f"/uz/actinfo/card2/{n}", f"actinfo/card2/{tag}.html"),
            (f"/uz/actinfo/basrev/{n}", f"actinfo/basrev/{tag}.html"),
            (f"/uz/pdfs/{n}", f"pdfs/{tag}.html"),
        ):
            pages.append(_get(path, key).decode("utf-8", "replace"))
        if not SKIP_PRINT_PDF:  # the printable PDF is lex.uz rendering the same HTML text (96-100 % same words)
            _get(f"/uz/docs/{n}?type=pdf", f"pdf/{tag}.pdf")
    # lex.uz file links may carry the id's minus sign (/uz/files/-123.pdf), which 404s; the file lives at /files/123.pdf
    files = {re.sub(r"/files/-", "/files/", m.group(1)) for p in pages for m in FILE_LINK.finditer(p)}
    for path in sorted(files):
        _get(path, f"files{path.split('/files')[1]}")
    imgs = {m.group(1) for p in pages for m in IMG.finditer(p) if not UI_IMG.match(m.group(1))}
    for path in sorted(imgs):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", path.strip("/"))[:180]
        _get(path, f"img/{lex_id.lstrip('-')}/{safe}")
    found = {m.group(1) for p in pages for m in DOC_LINK.finditer(p)}
    add(con, found, 3, twins=False)
    if level == 1:
        con.execute(
            "UPDATE acts SET status='done1', title=?, editions=?, files=?, images=?, links=?, "
            "done_at=datetime('now') WHERE lex_id=?",
            (lx.page_title(page)[:300], len(eds), len(files), len(imgs), len(found), lex_id),
        )
    else:
        con.execute(
            "UPDATE acts SET status='done', files=coalesce(files,0)+?, images=coalesce(images,0)+?, "
            "links=coalesce(links,0)+?, done_at=datetime('now') WHERE lex_id=?",
            (len(files), len(imgs), len(found), lex_id),
        )


# MEZON_SHARD="k/N": worker k of N takes the ids with abs(id) % N == k (scripts/box_resume.sh starts N of them, each
# with its own spacing, so the total rate stays N / MEZON_HTTP_INTERVAL). Unset = one worker takes everything.
SHARD_K, SHARD_N = (int(x) for x in os.environ.get("MEZON_SHARD", "0/1").split("/"))
SHARD_SQL = f" AND abs(cast(lex_id AS integer)) % {SHARD_N} = {SHARD_K}"
# MEZON_PASS=2: this worker only does pass 2 (links, cards, basrev, PDFs) on documents pass 1 has finished, so both
# passes run at the same time. Unset = pass 1 first, then pass 2.
PASS2_ONLY = os.environ.get("MEZON_PASS") == "2"
# Boss 20.11: skip the printable PDF copy; pass 2 takes national acts (prio 2) before local decisions (prio 1).
SKIP_PRINT_PDF = os.environ.get("MEZON_SKIP_PRINT_PDF") == "1"
P2_ORDER = " ORDER BY (prio = 1), prio, rowid" if os.environ.get("MEZON_P2_NATIONAL_FIRST") == "1" else " ORDER BY prio, rowid"


def _single_instance() -> object | None:
    """One crawler per shard per machine: a second `run` of the same shard exits instead of doubling the rate."""
    try:
        import fcntl
    except ImportError:  # Windows: no lock, the laptop runs one crawler by hand
        return True
    fh = (DIR / f"run{'p2_' if PASS2_ONLY else ''}{SHARD_K}of{SHARD_N}.lock").open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return fh


def run(con: sqlite3.Connection) -> None:
    lock = _single_instance()
    if lock is None:
        print("another lexuz_full run is active on this machine: exiting")
        return
    n, t0 = 0, time.time()
    while True:
        if STOP.exists():
            print("STOP file found: pausing cleanly")
            break
        from research.polite_http import WRITE_CACHE

        if min(shutil.disk_usage(DIR).free, shutil.disk_usage(WRITE_CACHE.anchor).free) / 1e9 < MIN_FREE_GB:
            print(f"under {MIN_FREE_GB} GB free on the state or cache drive: stopping")
            break
        row = (
            (None if PASS2_ONLY else con.execute(
                "SELECT lex_id, 1 FROM acts WHERE status='todo'" + SHARD_SQL + " ORDER BY prio, rowid LIMIT 1"
            ).fetchone())
            or con.execute(
                "SELECT lex_id, 2 FROM acts WHERE status='done1'" + SHARD_SQL + P2_ORDER + " LIMIT 1"
            ).fetchone()
        )
        if not row and PASS2_ONLY and con.execute("SELECT 1 FROM acts WHERE status='todo' LIMIT 1").fetchone():
            time.sleep(60)  # pass 1 has not handed over anything in this shard yet: wait, don't quit
            continue
        if not row:
            print("queue empty: lex.uz walked, both passes")
            break
        try:
            crawl_one(con, row[0], row[1])
        except Exception as e:  # noqa: BLE001 - log and move on; the act is retried on the next run
            con.execute("UPDATE acts SET status='error', title=? WHERE lex_id=?", (str(e)[:300], row[0]))
            print("error", row[0], e, flush=True)
        con.commit()
        n += 1
        if n % 50 == 0:
            status(con, f"after {n} acts, {(time.time() - t0) / 3600:.1f} h")


def status(con: sqlite3.Connection, head: str = "") -> None:
    by = dict(con.execute("SELECT status, count(*) FROM acts GROUP BY 1").fetchall())
    eds, files, imgs = con.execute(
        "SELECT sum(editions), sum(files), sum(images) FROM acts WHERE status IN ('done1','done')"
    ).fetchone()
    print(
        f"{time.strftime('%F %T')} {head} | acts {by} | editions {eds or 0} | files {files or 0} | images {imgs or 0}"
        f" | free {shutil.disk_usage(DIR).free / 1e9:.0f} GB",
        flush=True,
    )


if __name__ == "__main__":
    c = connect()
    {"seed": seed, "run": run, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"](c)
    if sys.argv[1:2] == ["run"]:
        status(c, "final")
