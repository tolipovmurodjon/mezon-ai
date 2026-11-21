"""Has lex.uz changed the status of any flagged decision since we stored it? (lost force, a new LexUZ note)

    .venv/Scripts/python.exe -X utf8 -m research.freshness [--region N] [limit]   # safe to stop and rerun

Re-reads the lex.uz page of every adopted decision that has a flag, once per day (a dated cache key, so the polite
1.2 s spacing and the cache still hold). A decision that lost force or gained a "LexUZ sharhi" note since the store
was built goes back to the expert as "status changed on lex.uz". Writes data/interim/freshness_<date>.csv.
"""

import csv
import datetime as dt
import re
import sys
from pathlib import Path

from mezon.decisions.build import lost_from_note
from mezon.decisions.store import DecisionStore
from research.lexuz_crawl import parse_doc
from research.polite_http import fetch

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ROOT / "data" / "interim" / "rule_flags.csv"


def flagged_lexuz(store: DecisionStore) -> list[dict]:
    ids = {r["decision_id"] for r in csv.DictReader(FLAGS.open(encoding="utf-8-sig")) if r["role"] == "adopted"}
    out = []
    for i in sorted(ids):
        d = store.get(i)
        if d and re.search(r"lex\.uz/(?:uz/)?docs/-?\d+", d.get("url") or ""):
            out.append(d)
    return out


FIELDS = ["reg_number", "status", "detail", "url"]


def check_one(d: dict, today: str) -> dict:
    lex_id = re.search(r"docs/(-?\d+)", d["url"]).group(1)
    try:
        page = fetch(d["url"], "lexuz", key=f"fresh/{today}/{lex_id.lstrip('-')}.html").decode("utf-8", "replace")
    except RuntimeError as e:
        return {"reg_number": d["reg_number"], "status": "not reached", "detail": str(e)[:120], "url": d["url"]}
    now = parse_doc(page) if page else {}
    note = (now.get("sharhi") or "")[:240]
    lost_now = now.get("lost_force") or lost_from_note(note)
    status = "lost force (lex.uz), store says in force" if lost_now and not d.get("lost_force") else "unchanged"
    return {"reg_number": d["reg_number"], "status": status, "detail": lost_now or note, "url": d["url"]}


def main(limit: int | None = None, region: int | None = None, out: Path | None = None) -> list[dict]:
    """Writes each row as soon as it is checked and skips rows already in today's file, so a stopped run resumes."""
    today = dt.date.today().isoformat()
    out = out or ROOT / "data" / "interim" / f"freshness_{today}.csv"
    done = set()
    if out.exists():
        with out.open(encoding="utf-8-sig", newline="") as f:
            done = {r["reg_number"] for r in csv.DictReader(f) if r["status"] != "not reached"}
    decisions = [d for d in flagged_lexuz(DecisionStore()) if region is None or d.get("region") == region]
    todo = [d for d in decisions if d["reg_number"] not in done][:limit]
    new = not out.exists() or out.stat().st_size == 0
    rows = []
    with out.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for d in todo:
            row = check_one(d, today)
            w.writerow(row)
            f.flush()
            rows.append(row)
    changed = [r for r in rows if r["status"] != "unchanged"]
    print(f"{len(rows)} checked now, {len(done)} already done today, {len(decisions)} in scope; "
          f"{len(changed)} changed -> {out}")
    for r in changed:
        print(f"  {r['reg_number']}: {r['status']} | {r['detail'][:100]}")
    return rows


if __name__ == "__main__":
    args = sys.argv[1:]
    reg = int(args[args.index("--region") + 1]) if "--region" in args else None
    nums = [a for i, a in enumerate(args) if a.isdigit() and (i == 0 or args[i - 1] != "--region")]
    main(int(nums[0]) if nums else None, reg)
