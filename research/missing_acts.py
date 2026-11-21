"""Which cited acts the law store lacks, ranked by how many decisions cite them (where to grow the store next).

    .venv/Scripts/python.exe -X utf8 -m research.missing_acts

Reads every adopted decision with text, takes the acts its preamble cites (mezon.rules.basis.references) and writes
data/interim/missing_acts.csv: act, decisions citing it, whether the store has it, one example sentence.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

from mezon.decisions.store import DecisionStore
from mezon.rules.basis import references
from mezon.rules.run import load_law

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "interim" / "missing_acts.csv"


def main() -> None:
    store, law = DecisionStore(), load_law()
    count: Counter = Counter()
    example: dict[str, str] = {}
    bodies: dict[str, set] = defaultdict(set)
    rows = store.con.execute(
        "SELECT id FROM decisions WHERE role='adopted' AND length(coalesce(text,'')) > 0").fetchall()
    for (i,) in rows:
        d = store.get(i)
        for num, sentence in {n: s for n, s in references(d["text"])}.items():
            count[num] += 1
            example.setdefault(num, " ".join(sentence.split())[:220])
            bodies[num].add(d.get("body") or "")
    out = []
    for num, n in count.most_common():
        key = num[1:] if num.startswith("@") else (law.find_act(num) if law else None)
        out.append({"act": num, "decisions": n, "bodies": len(bodies[num]), "in_store": "yes" if key else "no",
                    "example": example[num]})
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    missing = [r for r in out if r["in_store"] == "no"]
    held = sum(r["decisions"] for r in out if r["in_store"] == "yes")
    total = sum(r["decisions"] for r in out)
    print(f"{len(rows)} decisions, {len(out)} distinct acts cited, {total} citations; "
          f"{held} ({held / max(total, 1):.0%}) resolve to the store")
    print("top missing:")
    for r in missing[:15]:
        print(f"  {r['act']:12s} {r['decisions']:4d} decisions, {r['bodies']:3d} bodies | {r['example'][:110]}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
