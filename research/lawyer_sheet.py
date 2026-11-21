"""Stratified review sheet for the lawyer: up to N flags per rule, with the exact evidence and law quote, ready to mark."""

import csv
import random
import sys
from collections import defaultdict

from mezon.config import DATA
from mezon.decisions.store import DecisionStore
from mezon.plain import TEXTS
from mezon.rules.run import audit, load_law

FLAGS = DATA / "interim" / "rule_flags.csv"
OUT = DATA.parent / "research" / "flags_for_lawyer_round1.csv"
PER_RULE = 5
# R_business_3m makes ~90 % of flags on decisions in force, so its precision decides the headline number.
OVERRIDE = {"R_business_3m": 12}
SEED = 7


def main() -> None:
    per_rule = int(sys.argv[1]) if len(sys.argv) > 1 else PER_RULE
    with open(FLAGS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    by_rule = defaultdict(list)
    for r in rows:
        by_rule[r["check"]].append(r)
    rng = random.Random(SEED)
    picked = [r for rule in sorted(by_rule)
              for r in rng.sample(by_rule[rule], min(OVERRIDE.get(rule, per_rule), len(by_rule[rule])))]
    law, store = load_law(), DecisionStore()
    out = []
    for r in picked:
        report = audit(r["decision_id"], law=law, decisions=store)
        flag = next((f for f in report.flags if f.check == r["check"]), None)
        if flag is None:
            continue
        ev = flag.evidence[0] if flag.evidence else None
        ct = flag.citations[0] if flag.citations else None
        out.append({
            "n": len(out) + 1, "rule": r["check"], "rule_uz": TEXTS.get(r["check"], (flag.title,))[0],
            "decision": report.reg_number or r["decision_id"], "body": report.body, "date": report.date,
            "url": report.url or r["url"], "status": flag.status, "severity": flag.severity,
            "evidence_quote": ev.quote if ev else "", "law": f"{ct.act_title}, {ct.article} ({ct.on_date})" if ct else "",
            "law_quote": ct.quote if ct else "", "law_url": ct.url if ct else "",
            "lawyer_verdict (correct / wrong / unclear)": "", "lawyer_note": "",
        })
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} flags from {len(by_rule)} rules -> {OUT}")


if __name__ == "__main__":
    main()
