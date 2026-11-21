"""When a higher act changes, which local decisions should adliya look at again?

    .venv/Scripts/python.exe -X utf8 -m research.law_change_impact

For every act in the law store, each edition date D where article texts changed (a unit whose validity ends on D),
paired with the local decisions in force that cite that act and were adopted before D. A decision citing a specific
changed article ("4-bandiga", "24-moddasi") is marked as the strongest case. Nothing here says a decision is now
unlawful: it is a re-check list, the same work adliya does by hand after an amendment.
Writes data/interim/law_change_impact.csv.
"""

import csv
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from mezon.config import LAW_DB
from mezon.decisions.store import DecisionStore
from mezon.rules.basis import references
from mezon.rules.run import load_law
from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "interim" / "law_change_impact.csv"
SINCE = "2023-01-01"  # Boss: recent years only


def changes(con) -> dict[tuple[str, str], list[str]]:
    """(act_key, change date) -> top-level paths whose text ended on that date (changed or removed)."""
    out = defaultdict(set)
    for key, path, vt in con.execute(
            "SELECT act_key, path, valid_to FROM units WHERE valid_to IS NOT NULL AND valid_to >= ?", (SINCE,)):
        out[(key, vt)].add(path.split("/")[0])
    return {k: sorted(v) for k, v in out.items()}


def _cites_path(text: str, path: str) -> bool:
    """Does the decision name this article or clause number near an article word ("24-moddasi", "4-bandiga")?"""
    m = re.match(r"(art|cl):(\d+(?:-\d+)?)$", path)
    if not m:
        return False  # annexes ("1-ilova") are too common to match on their number alone
    word = {"art": "modda", "cl": "band"}[m[1]]
    num = re.escape(m[2])
    return bool(re.search(rf"(?<![\d-]){num}(?!-\d)\W{{0,2}}{word}", text))


def main() -> None:
    con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
    law, store = load_law(), DecisionStore()
    titles = dict(con.execute("SELECT act_key, title FROM acts"))
    cited: dict[str, list[dict]] = defaultdict(list)
    for (i,) in store.con.execute(
            "SELECT id FROM decisions WHERE role='adopted' AND length(coalesce(text,'')) > 0 "
            "AND coalesce(lost_force,'') = ''"):
        d = store.get(i)
        f = fold(d["text"])
        for num, _ in references(d["text"]):
            key = num[1:] if num.startswith("@") else law.find_act(num)
            if key:
                cited[key].append({"d": d, "folded": f})
    rows = []
    for (key, day), paths in sorted(changes(con).items(), key=lambda x: (x[0][1], x[0][0])):
        hits = [c for c in cited.get(key, []) if (c["d"].get("adopted") or "9999") < day]
        if not hits:
            continue
        for c in hits:
            exact = [p for p in paths if _cites_path(c["folded"], p)]
            gone = [p for p in exact if not con.execute(
                "SELECT 1 FROM units WHERE act_key=? AND path=? AND valid_to IS NULL", (key, p)).fetchone()]
            rows.append({"act_key": key, "act": (titles.get(key) or "")[:80], "changed_on": day,
                         "changed_units": len(paths), "reg_number": c["d"].get("reg_number"),
                         "adopted": c["d"].get("adopted"), "body": c["d"].get("body"),
                         "cites_changed_unit": " ".join(exact),
                         "status": "removed" if gone else ("reworded" if exact else "act amended"),
                         "url": c["d"].get("url") or ""})
    rows.sort(key=lambda r: (r["cites_changed_unit"] == "", r["changed_on"]), reverse=False)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["act_key"])
        w.writeheader()
        w.writerows(rows)
    events = {(r["act_key"], r["changed_on"]) for r in rows}
    strong = [r for r in rows if r["status"] == "removed"]
    print(f"cited article reworded: {sum(r['status'] == 'reworded' for r in rows)} pairs; "
          f"cited article REMOVED: {len(strong)} pairs, {len({r['reg_number'] for r in strong})} decisions")
    print(f"{len(events)} amendments since {SINCE} touch acts that local decisions in force cite; "
          f"{len(rows)} re-check pairs, {len({r['reg_number'] for r in rows})} decisions; "
          f"{len(strong)} cite the exact changed article or clause")
    for r in strong[:12]:
        print(f"  {r['changed_on']} {r['act_key']:12s} {r['cites_changed_unit']:12s} -> {r['reg_number']} "
              f"({r['adopted']}) {(r['body'] or '')[:40]}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
