"""Use the readable catalogue of the official "LexUZ oflayn" package (ldb.db, snapshot 09.09.2025) and compare it with
today's lex.uz catalogue from research.lexuz_discover.

    python -X utf8 -m research.lexuz_offline_compare          # load + queue + compare (rerun after discovery ends)

ldb.db is a plain SQLite file inside the official installer (unpacked with innoextract, nothing executed): acts
(153,635: id, language, title, number, adoption / effective / lost-force dates, status Y/R/N, word count), the table of
contents of each act (390,108 headings), issuing bodies, and the classifier of legislation branches. The document
texts in the package (DLD/Docs/*.bin) are encrypted for the licensed program and are NOT decrypted: texts come from
the public lex.uz pages through the crawl. Comparison = what changed on lex.uz since the snapshot (new documents,
documents whose status changed), which the crawl fetches first.
"""

import sqlite3
from pathlib import Path

from research.lexuz_full import DB, add, connect

ROOT = Path(__file__).resolve().parents[1]
LDB = ROOT / "data" / "raw" / "lexuz_offline" / "ldb.db"
LANG = {1: "ru", 2: "en", 3: "uz_cyrl", 4: "uz_latn"}


def main() -> None:
    con = connect()
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("""CREATE TABLE IF NOT EXISTS offline_acts(lex_id TEXT PRIMARY KEY, lang TEXT, title TEXT, number TEXT,
                   adopted TEXT, effective TEXT, obsolete TEXT, status TEXT, words INTEGER)""")
    src = sqlite3.connect(f"file:{LDB}?mode=ro", uri=True)
    rows = [(str(lid), LANG.get(lang, str(lang)), t, n, a, e, o, s, w) for lid, lang, t, n, a, e, o, s, w in src.execute(
        "SELECT lact_id, lang_id, title, lact_number, acceptance_date, effective_date, obsolete_date, status, word_cnt "
        "FROM acts")]
    con.executemany("INSERT OR REPLACE INTO offline_acts VALUES(?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    queued = add(con, [r[0] for r in rows], 2, twins=False)
    print(f"offline catalogue: {len(rows):,} acts (snapshot 09.09.2025); {queued:,} queue rows added or raised")
    have_cat = con.execute("SELECT count(*) FROM catalog").fetchone()[0] if con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='catalog'").fetchone() else 0
    if not have_cat:
        print("no lex.uz catalogue yet: run research.lexuz_discover, then rerun this for the comparison")
        return
    q = lambda s: con.execute(s).fetchone()[0]
    print(f"today's lex.uz catalogue (discovery so far): {have_cat:,}")
    print(f"  in both: {q('SELECT count(*) FROM catalog c JOIN offline_acts o USING(lex_id)'):,}")
    print(f"  new on lex.uz since the snapshot: {q('SELECT count(*) FROM catalog WHERE lex_id NOT IN (SELECT lex_id FROM offline_acts)'):,}")
    print(f"  in the snapshot, not (yet) in today's catalogue: "
          f"{q('SELECT count(*) FROM offline_acts WHERE lex_id NOT IN (SELECT lex_id FROM catalog)'):,}")
    changed = con.execute("""SELECT count(*) FROM catalog c JOIN offline_acts o USING(lex_id)
                             WHERE o.status='Y' AND c.status IS NOT NULL AND lower(c.status) NOT IN ('y')""").fetchone()[0]
    print(f"  in force in the snapshot, other status today (by the search badge): {changed:,}")
    con.execute("UPDATE acts SET prio=0 WHERE status='todo' AND lex_id IN "
                "(SELECT lex_id FROM catalog WHERE lex_id NOT IN (SELECT lex_id FROM offline_acts))")
    con.commit()
    print("documents new since the snapshot moved to the front of the crawl queue; state:", DB)


if __name__ == "__main__":
    main()
