"""The exact list of every lex.uz document, from lex.uz's own search: month by month, language by language.

    python -X utf8 -m research.lexuz_discover            # resumable; prints the running total vs the official count
    python -X utf8 -m research.lexuz_discover --check    # totals only

Search /uz/search/all?from=dd.mm.yyyy&to=dd.mm.yyyy&lang=N lists documents by adoption date, 20 per page, paged with
the page's own "Keyingisi" form post (approved). lang: 1 Russian, 2 English, 3 Uzbek Cyrillic, 4 Uzbek Latin (checked
20.11.2026: 44 + 26 + 60 + 60 = 190 = the all-language total for 1-19.11.2026). Every hit goes into the `catalog` table
of data/raw/lexuz_full/state.sqlite and into the crawl queue. Official total on lex.uz/uz/statistic (20.11.2026):
166,705 documents. A window whose fetched hits fall short of its stated total is logged, never silently accepted.
"""

import calendar
import re
import sqlite3
import sys
from datetime import date

from research.lexuz_crawl import search_url
from research.lexuz_full import DB, add, connect

BASE = "https://lex.uz"
LANGS = {1: "ru", 2: "en", 3: "uz_cyrl", 4: "uz_latn"}
OFFICIAL_TOTAL = 166_705


def windows(start_year: int = 1900):
    today = date.today()
    yield (date(start_year, 1, 1), date(1990, 12, 31))  # everything before independence in one window
    for y in range(1991, today.year + 1):
        for m in range(1, 13):
            a = date(y, m, 1)
            if a > today:
                return
            yield a, date(y, m, calendar.monthrange(y, m)[1])


def setup(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS catalog(lex_id TEXT PRIMARY KEY, lang TEXT, title TEXT, badge TEXT, body TEXT,
      adopted TEXT, number TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS windows(w TEXT PRIMARY KEY, stated INTEGER, got INTEGER);
    """)


def main(check: bool = False) -> None:
    con = connect()
    setup(con)
    for a, b in windows():
        for lang, code in LANGS.items():
            w = f"{a:%Y-%m}_{code}"
            if con.execute("SELECT 1 FROM windows WHERE w=?", (w,)).fetchone() or check:
                continue
            url = f"{BASE}/uz/search/all?from={a:%d.%m.%Y}&to={b:%d.%m.%Y}&lang={lang}"
            stated, hits = search_url(url, f"discover/{w}", max_pages=2000)
            con.executemany("INSERT OR IGNORE INTO catalog VALUES(?,?,?,?,?,?,?,?)",
                            [(h["id"], code, h["title"][:400], h["badge"][:300], h["body"][:200], h["date"],
                              h["number"], h["status"]) for h in hits])
            con.execute("INSERT OR REPLACE INTO windows VALUES(?,?,?)", (w, stated, len(hits)))
            local = [h["id"] for h in hits if re.search(r"hokim|kengash|ҳоким|кенгаш|хоким|кенгаш", h["body"], re.IGNORECASE)]
            add(con, local, 1, twins=False)  # local decisions first
            add(con, [h["id"] for h in hits], 2, twins=False)
            con.commit()
            if len(hits) < stated:
                print(f"SHORT {w}: stated {stated}, got {len(hits)}", flush=True)
        n = con.execute("SELECT count(*) FROM catalog").fetchone()[0]
        print(f"{a:%Y-%m}: catalog {n:,} / official {OFFICIAL_TOTAL:,}", flush=True)
    # guessed ids (dataset twins etc.) that the official catalog never listed go to the back of the queue, not away
    con.execute("UPDATE acts SET prio=9 WHERE status='todo' AND lex_id NOT IN (SELECT lex_id FROM catalog) AND prio>0")
    con.commit()
    stated, got = con.execute("SELECT sum(stated), sum(got) FROM windows").fetchone()
    print(f"windows stated {stated:,} · fetched {got:,} · catalog {con.execute('SELECT count(*) FROM catalog').fetchone()[0]:,}"
          f" · official {OFFICIAL_TOTAL:,}")
    for lang, n in con.execute("SELECT lang, count(*) FROM catalog GROUP BY 1"):
        print(f"  {lang}: {n:,}")


if __name__ == "__main__":
    print("state:", DB)
    main("--check" in sys.argv)
