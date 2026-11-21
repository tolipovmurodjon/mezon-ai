"""Daily refresh: lex.uz feed -> new local decisions fetched -> decision store rebuilt -> every decision re-audited.

Run once a day (or before the demo):  .venv/Scripts/python.exe -X utf8 -m mezon.sync.daily
Restart the API afterwards so the adliya queue reads the new rule_flags.csv.
"""

import sqlite3

from mezon.decisions.build import build
from mezon.rules.run import audit_all
from mezon.sync import lexuz_local, rss
from research.lexuz_crawl import fetch_doc


def fetch_new_local() -> int:
    """Store every local decision the feed has announced that the lex.uz crawl doesn't hold yet."""
    rss.poll()
    feed = rss._db()
    announced = feed.execute("select lex_id, title from feed where is_local=1").fetchall()
    feed.close()
    con = lexuz_local.connect()
    con.row_factory = sqlite3.Row
    have = {r[0].lstrip("-") for r in con.execute("select lex_id from decisions")}
    added = 0
    for lex_id, title in announced:
        if lex_id.lstrip("-") in have:
            continue
        try:
            meta = fetch_doc(lex_id)
        except RuntimeError as e:
            lexuz_local.log(f"daily: {lex_id} failed: {e}")
            continue
        q = {"lex_id": lex_id, "number": meta.get("number") or "", "title": meta.get("title") or title,
             "adopted": lexuz_local._iso(meta.get("date") or ""),
             "in_force": lexuz_local._iso(meta.get("entry_into_force") or ""), "status": ""}
        con.execute("insert or ignore into queue(lex_id, number, title, adopted, in_force, status, sources) "
                    "values(?,?,?,?,?,?,?)", (*q.values(), "rss"))
        added += lexuz_local.store_one(con, q)
        con.commit()
    con.close()
    return added


def main() -> None:
    added = fetch_new_local()
    print(f"feed: {added} new local decisions with text")
    print(f"store: {build()} decisions")
    audit_all()


if __name__ == "__main__":
    main()
