"""The numbers we may say on stage, each with N, printed by this script and written to eval/report.md.

Run:  .venv/Scripts/python.exe -X utf8 -m eval.run
Every figure comes from the local stores as they are now; rerun after any rebuild. Flagged != illegal.
"""

import datetime as dt
import sqlite3
from collections import Counter
from pathlib import Path

from mezon.config import STORE
from mezon.decisions.store import DecisionStore
from mezon.rules.common import squash
from mezon.rules.run import audit, load_law

OUT = Path(__file__).resolve().parent / "report.md"


def pct(a: int, n: int) -> str:
    return f"{a}/{n} = {a / n:.1%}" if n else f"{a}/0 = n/a"


def main() -> None:
    law, store = load_law(), DecisionStore()
    groups: dict[str, Counter] = {}
    cites, by_rule = Counter(), Counter()
    for did in store.ids():
        d = store.get(did)
        if d["role"] == "draft":
            g = "draft"
        elif d["role"] == "cancelling":
            continue
        elif d["label"] == "POSITIVE":
            g = "cancelled, with text" if d["text"] else "cancelled, E-qaror stages only"
        elif d["label"] == "none" and not d["lost_force"]:
            g = "in force, not cancelled"
        else:
            continue
        rep = audit(did, law, store)
        c = groups.setdefault(g, Counter())
        c["n"] += 1
        c["any_flag"] += bool(rep.flags)
        c["possible_violation"] += any(f.status == "possible_violation" for f in rep.flags)
        for f in rep.flags:
            by_rule[(g, f.check)] += 1
            for ct in f.citations:
                cites["total"] += 1
                unit = law.get_unit(ct.act_id, ct.article, ct.on_date) if law else None
                ok = bool(unit and ct.quote and squash(ct.quote) in squash(unit["text"]))
                cites["valid" if ok else "invalid"] += 1

    rv = Counter()
    rdb = STORE / "reviews.sqlite"
    if rdb.exists():
        con = sqlite3.connect(f"file:{rdb}?mode=ro", uri=True)
        for v, n in con.execute("select verdict, count(*) from reviews group by 1"):
            rv[v] = n

    lines = [f"# Mezon eval ({dt.date.today().isoformat()})", "",
             "Printed by `python -m eval.run`. Flagged ≠ illegal: every flag is a possible violation for expert review.",
             "", "| Group | N | Any flag | Possible violation (high-confidence) |", "|---|---|---|---|"]
    for g in ("cancelled, with text", "cancelled, E-qaror stages only", "in force, not cancelled", "draft"):
        c = groups.get(g, Counter())
        lines.append(f"| {g} | {c['n']} | {pct(c['any_flag'], c['n'])} | {pct(c['possible_violation'], c['n'])} |")
    lines += ["", (f"**Citation validity** (quote is verbatim in the law edition in force on the decision date): "
              f"{pct(cites['valid'], cites['total'])}"), ""]
    judged = rv["correct"] + rv["wrong"]
    lines.append(f"**Lawyer precision:** {pct(rv['correct'], judged)} (plus {rv['unclear']} marked unclear)"
                 if judged else "**Lawyer precision:** not measured yet (0 reviewed flags).")
    lines += ["", "Flags per rule and group:", "", "| Group | Rule | Flags |", "|---|---|---|"]
    lines += [f"| {g} | {r} | {n} |" for (g, r), n in sorted(by_rule.items())]
    lines += ["", ("Read with care: 'cancelled' = cancelled on an official trigger (adliya, prosecutor, court) or "
              "E-qaror 'declared invalid'; most are individual decisions that procedure rules don't cover. "
              "'In force' flags are not errors until a lawyer reviews them.")]
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
