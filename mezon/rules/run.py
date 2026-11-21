"""Audit a decision with every rule, verify each flag, and return a Report in adliya's three-verdict format.

CLI:  uv run python -X utf8 -m mezon.rules.run <reg_number | decision id>
      uv run python -X utf8 -m mezon.rules.run --all     (audits everything, writes data/interim/rule_flags.csv)
"""

import csv
import json
import sys
from collections import Counter

from mezon.config import DATA
from mezon.decisions.store import DecisionStore
from mezon.report import Report, verdict_for
from mezon.rules import basis, business, corruption, duplicate, form, land, procedure
from mezon.rules.common import SafeLaw
from mezon.verify import verify_flag

# A lex.uz decision with no defect found by any rule: the "positive" control in tests/test_rules.py.
CLEAN_CONTROL = "14-11-169-Q/24"
GATE1 = {"R_discussion", "R_adopted_before_end"}
_DEFAULT = object()


def load_law():
    try:
        from mezon.lawstore import store as m
    except Exception:  # noqa: BLE001 - no law store yet: audit without citations
        return None
    for name in ("LawStore", "Store"):
        cls = getattr(m, name, None)
        if cls is not None:
            try:
                return cls()
            except Exception:  # noqa: BLE001 - store file missing or unreadable
                return None
    return m if hasattr(m, "get_unit") else None


def audit(decision_id: str, law=_DEFAULT, decisions: DecisionStore | None = None) -> Report:
    decisions = decisions or DecisionStore()
    law = SafeLaw(load_law() if law is _DEFAULT else law)
    d = decisions.get(decision_id)
    if d is None:
        raise KeyError(decision_id)
    drafts = decisions.drafts()
    raw, checks_run = [], []

    def run(name, fn, *args):
        checks_run.append(name)
        raw.extend(fn(*args))

    run("R_business_3m+R_retroactive", business.check, d, law)
    run("R_draft_window+R_discussion_short", procedure.draft_window, d, law)
    run("R_discussion+R_adopted_before_end", procedure.discussion, d, law, drafts)
    run("R_expertise", procedure.expertise, d, law)
    run("R_form", form.check, d, law)
    run("R_competence_land", land.check, d, law)
    run("R_duplicate+R_double_repeal", duplicate.check, d, law, decisions)
    run("R_corruption_factor", corruption.check, d, law)
    if law:
        run("R_basis", basis.check, d, law)
    else:
        checks_run.append("R_basis (not checked: law store unavailable)")

    flags = []
    for f in raw:
        kept, _ = verify_flag(f, d, law, decisions)
        if kept:
            flags.append(kept)
    gate = (
        "0_draft"
        if d["role"] == "draft"
        else ("1_slipped" if {f.check for f in flags} & GATE1 else "2_adopted")
    )
    return Report(
        decision_id=d["id"],
        reg_number=d.get("reg_number") or "",
        title=d.get("title") or "",
        body=d.get("body") or "",
        date=d.get("adopted") or d.get("disc_end") or "",
        gate=gate,
        verdict=verdict_for(flags),
        flags=flags,
        checks_run=checks_run,
        affected=sorted({f.impact for f in flags if f.impact}),
        url=d.get("url") or "",
    )


def audit_all(out=DATA / "interim" / "rule_flags.csv", law=_DEFAULT) -> None:
    decisions = DecisionStore()
    law = load_law() if law is _DEFAULT else law
    by_rule: Counter = Counter()
    seen: dict[str, Counter] = {}
    rows = []
    for did in decisions.ids():
        d = decisions.get(did)
        rep = audit(did, law, decisions)
        group = f"{d['role']}/{d['label']}"
        c = seen.setdefault(group, Counter())
        c["n"] += 1
        if rep.flags:
            c["flagged"] += 1
        if any(f.status == "possible_violation" for f in rep.flags):
            c["possible_violation"] += 1
        for f in rep.flags:
            by_rule[(f.check, f.status)] += 1
            rows.append(
                {
                    "decision_id": did,
                    "reg_number": d["reg_number"],
                    "role": d["role"],
                    "label": d["label"],
                    "check": f.check,
                    "severity": f.severity,
                    "status": f.status,
                    "verdict": rep.verdict,
                    "title": f.title,
                    "url": d["url"],
                }
            )
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["decision_id"])
        w.writeheader()
        w.writerows(rows)
    print(f"law store: {'loaded' if law else 'unavailable (citations unverified, flags unclear)'}")
    print("\nflags per rule (status):")
    for (rule, status), n in sorted(by_rule.items()):
        print(f"  {rule:24s} {status:22s} {n}")
    print("\nper role/label: decisions · any flag · any possible_violation")
    for g, c in sorted(seen.items()):
        print(
            f"  {g:28s} {c['n']:5d} · {c['flagged']:4d} ({c['flagged'] / c['n']:.0%}) · {c['possible_violation']:4d}"
        )
    print(f"\n{len(rows)} flags -> {out}")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "--all"
    if arg == "--all":
        audit_all()
        return
    decisions = DecisionStore()
    did = arg if decisions.get(arg) else (decisions.by_reg(arg) or [None])[0]
    if did is None:
        sys.exit(f"not found: {arg}")
    print(json.dumps(audit(did, decisions=decisions).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
