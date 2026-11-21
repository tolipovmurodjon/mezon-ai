"""Daily change log: which articles of which core act were added, changed or removed, and from what date.

    .venv/Scripts/python.exe -X utf8 -m mezon.lawstore.changelog          # rebuild from the law store, print a summary
    .venv/Scripts/python.exe -X utf8 -m mezon.lawstore.changelog --since 2026-11-01

Derived only from the editions and units the store already holds (each unit carries seq_from/seq_to), so the log is
exactly as good as the store: a missing edition is a missing change. Table change_log(act_key, path, change_type,
effective_date, edition, old_text, new_text). The daily sync rebuilds an act's rows after it stores a new edition;
/api/law-changes and the agent read this table instead of recomputing.
"""

import sqlite3
import sys

from mezon.config import LAW_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS change_log(
  act_key TEXT, path TEXT, change_type TEXT CHECK(change_type IN ('added','changed','removed')),
  effective_date TEXT, edition TEXT, old_text TEXT, new_text TEXT,
  PRIMARY KEY(act_key, path, effective_date, change_type));
CREATE INDEX IF NOT EXISTS change_log_date ON change_log(effective_date);
"""


def rebuild(con: sqlite3.Connection) -> int:
    con.executescript(SCHEMA)
    con.execute("DELETE FROM change_log")
    eds = {(a, s): (vf, od) for a, s, vf, od in con.execute("SELECT act_key, seq, valid_from, ondate FROM editions")}
    units = con.execute("SELECT act_key, path, text, seq_from, seq_to FROM units ORDER BY act_key, path, seq_from").fetchall()
    rows, by = [], {}
    for a, path, text, sf, st in units:
        by.setdefault((a, path), []).append((sf, st, text))
    for (a, path), vers in by.items():
        prev = None
        for sf, st, text in vers:
            if sf > 0 and (a, sf) in eds:  # seq 0 is the first stored edition: no "before" to compare with
                vf, od = eds[(a, sf)]
                if prev is None or prev[1] < sf - 1:
                    rows.append((a, path, "added", vf, od, None, text))
                elif prev[2] != text:
                    rows.append((a, path, "changed", vf, od, prev[2], text))
            prev = (sf, st, text)
        last_seq = max(s for (x, s) in eds if x == a)
        if prev and prev[1] < last_seq and (a, prev[1] + 1) in eds:
            vf, od = eds[(a, prev[1] + 1)]
            rows.append((a, path, "removed", vf, od, prev[2], None))
    con.executemany("INSERT OR REPLACE INTO change_log VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def main() -> None:
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "2023-01-01"
    con = sqlite3.connect(LAW_DB)
    n = rebuild(con)
    print(f"change_log: {n} rows")
    for a, t, c in con.execute("SELECT act_key, change_type, count(*) FROM change_log WHERE effective_date >= ? "
                               "GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15", (since,)):
        print(f"  {a:14} {t:8} {c}  (since {since})")
    for row in con.execute("SELECT act_key, path, change_type, effective_date FROM change_log "
                           "ORDER BY effective_date DESC LIMIT 5"):
        print("  latest:", row)


if __name__ == "__main__":
    main()
