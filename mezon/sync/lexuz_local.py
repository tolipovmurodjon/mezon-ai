"""Resumable crawl of local (hokim / Kengash) decisions on lex.uz, enumerated from the respondents panels of core laws.

Run:   .venv/Scripts/python.exe -X utf8 -m mezon.sync.lexuz_local   (set MEZON_CACHE to a drive with space)
       add --followups to queue the later decisions of every body whose decision was cancelled on an official
       trigger (lex.uz title search, same region / district / type, adopted later)
Stop:  create data/store/lexuz_local.STOP, or kill the PID in data/store/lexuz_local.pid. Re-running resumes.
"""

import datetime as dt
import html
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from mezon.config import ROOT, STORE
from research import polite_http
from research.lexuz_crawl import fetch_doc, load_text
from research.lexuz_crawl import search as lex_search
from research.regnum import parse as parse_regnum

DB = STORE / "lexuz_local.sqlite"
LOG = ROOT / "data" / "interim" / "lexuz_local.log"
STOP_FILE = STORE / "lexuz_local.STOP"
PID_FILE = STORE / "lexuz_local.pid"
MIN_FREE_GB = 1.0

# Core acts whose "respondents" panel lists the acts that cite them; most citing acts are local decisions.
CITED_ACTS = {
    "local_state_power": "-112170", "nla": "-5378966", "land_code": "-152653", "budget_code": "-2304138",
    "tax_code": "-4674902", "eqaror_vmq390": "-5470461", "admin_procedures": "-3492199", "pq3666": "-3681790",
    "land_public_needs": "-6087433", "public_control": "-3679092",
}

_ROW = re.compile(
    r"status_code_(\w+).*?getCorrespondentList\('(-?\d+)'.*?\">(.*?)</a></td>\s*"
    r'<td align="center">(.*?)</td>\s*<td align="center">(.*?)</td>\s*<td align="center">(.*?)</td>',
    re.DOTALL,
)

SCHEMA = """
create table if not exists queue(lex_id text primary key, number text, title text, adopted text, in_force text,
  status text, sources text, done integer default 0);
create table if not exists decisions(lex_id text primary key, url text, number text, type text, region integer,
  district integer, year integer, title text, header text, adopted text, entry_into_force text, lost_force text,
  status text, sharhi text, text text, text_source text, fetched_at text);
"""


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _iso(d: str) -> str:
    try:
        return dt.datetime.strptime(d.strip(), "%d.%m.%Y").date().isoformat()
    except ValueError:
        return ""


def parse_respondents(page: str) -> list[dict]:
    """Rows of a lex.uz respondents panel that are local decisions (their number parses as a hokim/Kengash number)."""
    rows = []
    for status, lex_id, title, number, adopted, in_force in _ROW.findall(page):
        number = html.unescape(re.sub(r"<[^>]+>", "", number)).strip()
        if parse_regnum(number) is None:
            continue
        rows.append({
            "lex_id": lex_id.lstrip("-"), "number": number, "status": status,
            "title": html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title))).strip(),
            "adopted": _iso(adopted), "in_force": _iso(in_force),
        })
    return rows


def connect() -> sqlite3.Connection:
    STORE.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    return con


def enumerate_queue(con: sqlite3.Connection) -> None:
    for name, act in CITED_ACTS.items():
        try:
            page = polite_http.fetch(f"https://lex.uz/uz/actinfo/respondents/{act}", "lexuz",
                                     key=f"actinfo/respondents/{act.lstrip('-')}.html").decode("utf-8", "replace")
        except RuntimeError as e:
            log(f"respondents {name}: {e}")
            continue
        rows = parse_respondents(page)
        for r in rows:
            cur = con.execute("select sources from queue where lex_id=?", (r["lex_id"],)).fetchone()
            if cur:
                if name not in cur[0].split(","):
                    con.execute("update queue set sources=? where lex_id=?", (f"{cur[0]},{name}", r["lex_id"]))
            else:
                con.execute("insert into queue(lex_id, number, title, adopted, in_force, status, sources) "
                            "values(?,?,?,?,?,?,?)",
                            (r["lex_id"], r["number"], r["title"], r["adopted"], r["in_force"], r["status"], name))
        con.commit()
        log(f"respondents {name}: {len(rows)} local rows; queue now {con.execute('select count(*) from queue').fetchone()[0]}")


FOLLOWUP_WORDS = 8


def enumerate_followups(con: sqlite3.Connection) -> None:
    """Queue later same-body decisions on the title of every POSITIVE (officially cancelled) decision in the store."""
    from mezon.config import DECISIONS_DB

    src = sqlite3.connect(f"file:{DECISIONS_DB}?mode=ro", uri=True)
    pos = src.execute("select reg_number, title, adopted from decisions where role='adopted' and label='POSITIVE' "
                      "and title != '' and adopted != ''").fetchall()
    src.close()
    seen, added = set(), 0
    for number, title, adopted in pos:
        rn = parse_regnum(number) or {}
        phrase = " ".join(re.sub(r"[«»“”\"'ʻʼ‘’`]", " ", title).split()[:FOLLOWUP_WORDS])
        if not rn or phrase in seen:
            continue
        seen.add(phrase)
        try:
            _, hits = lex_search(phrase, max_pages=2)
        except RuntimeError as e:
            log(f"followup search failed for {number}: {e}")
            continue
        for h in hits:
            hn = parse_regnum(h.get("number") or "") or {}
            same = all(hn.get(k) == rn.get(k) for k in ("region", "district", "type"))
            if not same or not h.get("date") or _iso(h["date"]) <= adopted:
                continue
            lex_id = h["id"]  # keep the sign: it marks the Latin version the search returned
            if con.execute("select 1 from queue where lex_id in (?, ?)", (lex_id, lex_id.lstrip("-"))).fetchone():
                continue
            con.execute("insert into queue(lex_id, number, title, adopted, in_force, status, sources) "
                        "values(?,?,?,?,?,?,?)",
                        (lex_id, h["number"], h["title"], _iso(h["date"]), "", h.get("status"), f"followup:{number}"))
            added += 1
        con.commit()
    log(f"followups: {len(seen)} titles searched, {added} later same-body decisions queued")


def enumerate_positives(con: sqlite3.Connection) -> None:
    """Queue the officially cancelled (POSITIVE) decisions that the decision store holds without text."""
    from mezon.config import DECISIONS_DB

    src = sqlite3.connect(f"file:{DECISIONS_DB}?mode=ro", uri=True)
    rows = src.execute("select src_id, reg_number, title, adopted from decisions where label='POSITIVE' "
                       "and length(coalesce(text,''))=0").fetchall()
    src.close()
    from research.resolve_original import find_by_number

    added = 0
    for src_id, number, title, adopted in rows:
        if src_id.startswith("http"):  # an E-qaror record: E-qaror shows no text, so find the same act on lex.uz
            try:
                hit = find_by_number(number) if number else None
            except RuntimeError as e:
                log(f"positives: lex.uz search failed for {number}: {e}")
                continue
            if not hit:
                continue
            src_id = hit["id"]
        if con.execute("select 1 from queue where lex_id in (?, ?)", (src_id, src_id.lstrip("-"))).fetchone():
            continue
        con.execute("insert into queue(lex_id, number, title, adopted, in_force, status, sources) values(?,?,?,?,?,?,?)",
                    (src_id, number, title, adopted, "", "", "positive"))
        added += 1
        if added % 20 == 0:
            con.commit()  # a stopped run keeps what it queued
    con.commit()
    log(f"positives: {added} cancelled decisions without text queued")


def store_one(con: sqlite3.Connection, q: dict) -> bool:
    meta = fetch_doc(q["lex_id"])
    text = load_text(meta["id"]) if meta.get("text_source") else ""
    if not text and meta.get("text_path"):
        text = Path(meta["text_path"]).read_text(encoding="utf-8")
    rn = parse_regnum(q["number"]) or {}
    con.execute(
        "insert or replace into decisions values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (q["lex_id"], meta.get("url"), q["number"], rn.get("type"), rn.get("region"), rn.get("district"),
         rn.get("year"), meta.get("title") or q["title"], meta.get("header"), q["adopted"],
         _iso(meta.get("entry_into_force") or "") or q["in_force"], _iso(meta.get("lost_force") or ""),
         q["status"], meta.get("sharhi"), text, meta.get("text_source"),
         dt.datetime.now().isoformat(timespec="seconds")),
    )
    con.execute("update queue set done=1 where lex_id=?", (q["lex_id"],))
    return bool(text)


def run() -> int:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    STOP_FILE.unlink(missing_ok=True)
    con = connect()
    con.row_factory = sqlite3.Row
    if "--followups" in sys.argv:
        enumerate_followups(con)
    elif "--positives" in sys.argv:
        enumerate_positives(con)
    else:
        enumerate_queue(con)
    todo = [dict(r) for r in con.execute("select * from queue where done=0 order by adopted desc, lex_id desc")]
    log(f"start: {len(todo)} decisions to fetch, newest first, cache {polite_http.WRITE_CACHE}")
    t0, n, texts, errors = time.monotonic(), 0, 0, 0
    for q in todo:
        if STOP_FILE.exists():
            log("stop file found, exiting")
            break
        if n % 50 == 0 and shutil.disk_usage(polite_http.WRITE_CACHE).free / 1e9 < MIN_FREE_GB:
            log("low disk on the cache drive, exiting")
            break
        try:
            texts += store_one(con, q)
            errors = 0
        except (RuntimeError, OSError) as e:
            errors += 1
            log(f"error at {q['lex_id']}: {e}")
            if errors >= 15:
                log("15 errors in a row, pausing 5 min")
                time.sleep(300)
                errors = 0
            continue
        n += 1
        if n % 20 == 0:
            con.commit()
        if n % 100 == 0:
            rate = n / ((time.monotonic() - t0) / 3600)
            log(f"{n} fetched ({texts} with text), {rate:.0f}/h, ETA {(len(todo) - n) / rate:.1f} h")
    con.commit()
    log(f"end of run: {n} fetched this run, {texts} with text")
    PID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
