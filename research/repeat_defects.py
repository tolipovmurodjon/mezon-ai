"""Repeat-defect watch: after a decision is cancelled on an official trigger (adliya, prosecutor, court), does the same
body adopt the same matter again with the same flagged defect?

For each POSITIVE adopted decision, look at the same body's later decisions (region, district, type) whose title is
near-identical (>= 0.9 after folding) and report which of them carry a rule flag the cancelled one also carried.
Input: data/store/decisions.sqlite and data/interim/rule_flags.csv (run `python -m mezon.rules.run --all` first).
Output: data/interim/repeat_defects.csv and a summary printed with N.
"""

import csv
from collections import defaultdict

from mezon.config import DATA
from mezon.decisions.store import DecisionStore
from research.textnorm import fold, similarity

TITLE_SIM = 0.9
FLAGS = DATA / "interim" / "rule_flags.csv"
OUT = DATA / "interim" / "repeat_defects.csv"


def main() -> None:
    flags: dict[str, set[str]] = defaultdict(set)
    with open(FLAGS, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            flags[r["decision_id"]].add(r["check"])
    s = DecisionStore()
    positives = [s.get(i) for i in s.ids("adopted")]
    positives = [d for d in positives if d and d["label"] == "POSITIVE" and d["title"] and d["adopted"]]
    rows, with_later, with_repeat = [], 0, 0
    for p in positives:
        if p["region"] is None:
            continue
        later = [
            x for x in s.same_body(p["region"], p["district"], p["type"])
            if x["id"] != p["id"] and (x["adopted"] or "") > p["adopted"]
            and similarity(fold(x["title"]), fold(p["title"])) >= TITLE_SIM
        ]
        if not later:
            continue
        with_later += 1
        hit = False
        for x in sorted(later, key=lambda x: x["adopted"]):
            shared = sorted(flags[p["id"]] & flags[x["id"]])
            hit |= bool(shared)
            rows.append({
                "cancelled": p["reg_number"], "cancelled_adopted": p["adopted"], "cancelled_lost_force": p["lost_force"],
                "cancelled_url": p["url"], "cancelled_flags": " ".join(sorted(flags[p["id"]])),
                "later": x["reg_number"], "later_adopted": x["adopted"], "later_url": x["url"],
                "later_flags": " ".join(sorted(flags[x["id"]])), "shared_flags": " ".join(shared),
                "title": p["title"][:160],
            })
        with_repeat += hit
    if rows:
        with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"POSITIVE adopted decisions with text and a parsed body: N={len(positives)}")
    print(f"  with a later same-body decision on a near-identical title: {with_later}")
    print(f"  ... where that later decision shares a Mezon flag with the cancelled one: {with_repeat}")
    print(f"{len(rows)} pairs -> {OUT}")
    for r in rows:
        if r["shared_flags"]:
            print(f"  {r['cancelled']} ({r['cancelled_adopted']}) -> {r['later']} ({r['later_adopted']}): {r['shared_flags']}")


if __name__ == "__main__":
    main()
