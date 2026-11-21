"""Group questions for the lawyer: one answer settles every 3-month flag on one kind of decision.

    .venv/Scripts/python.exe -X utf8 -m research.lawyer_questions

Reads data/interim/rule_flags.csv and writes research/lawyer_questions_round1.md. The groups come from decision
titles; the questions are drafts for the lawyer to answer, not legal conclusions.
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

from mezon.decisions.store import DecisionStore
from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ROOT / "data" / "interim" / "rule_flags.csv"
OUT = ROOT / "research" / "lawyer_questions_round1.md"

# (key, title pattern, the question, in the order a lawyer would answer them)
GROUPS = [
    ("job_quota", r"ishga joylasht|kvota|ehtiyojmand|ijtimoiy muhofazaga muhtoj",
     ("Annual job quotas for vulnerable groups, which VMQ No. 965 requires the hokim to set each year. Does the "
     "3-month rule of NLA art. 40 apply to them, or is the burden created by the higher act?")),
    ("land_tax", r"yer solig|mol-mulk solig|soliq stavka|bazaviy soliq|koeffitsiyent",
     ("Local land and property tax rates or coefficients, now checked against Tax Code art. 4 part 6 (rate changes take effect from the first day of the next month). Is 'in force on publication' in these decisions a violation, and does "
     "the Tax Code rule displace the NLA art. 40 3-month rule for them?")),
    ("annual_budget", r"budjetini tasdiqlash|byudjetini tasdiqlash|budjeti hamda|byudjeti hamda",
     ("Approval of the next year's local budget (adopted in December, in force from 1 January under the Budget "
     "Code). Is this a business burden under NLA art. 40 at all?")),
    ("utility_tariff", r"chiqindi|maxsustrans|issiqlik|suv|kommunal|tarif",
     ("Tariffs for waste removal, heating or water that businesses also pay. Is a new tariff an \"obligation for "
     "entrepreneurs\" under NLA art. 40, so that it takes effect no earlier than 3 months after publication?")),
    ("transport", r"transport|taksi|yolovchi|avtobus|yonalish",
     ("Passenger transport routes and fares. Is changing a route or fare a new obligation for carriers under "
     "NLA art. 40?")),
]


def main() -> None:
    store = DecisionStore()
    rows = [r for r in csv.DictReader(FLAGS.open(encoding="utf-8-sig")) if r["check"] in ("R_business_3m", "R_tax_timing")]
    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = store.get(r["decision_id"]) or {}
        title = fold(d.get("title") or "")
        key = next((k for k, pat, _ in GROUPS if re.search(pat, title)), "other")
        by_group[key].append({**r, "title": d.get("title") or "", "url": d.get("url") or ""})

    lines = [
        "# Mezon: group questions for the lawyer (round 1)",
        "",
        (f"Printed by `python -m research.lawyer_questions` from `data/interim/rule_flags.csv`: {len(rows)} flags of "
        "the 3-month rule (NLA art. 40). One answer per group settles every flag in it. The questions are drafts; "
        "please correct the question itself if it is framed wrongly."),
        "",
    ]
    covered = 0
    for n, (key, _, question) in enumerate(GROUPS, 1):
        items = by_group.get(key, [])
        if not items:
            continue
        covered += len(items)
        high = sum(i["status"] == "possible_violation" for i in items)
        lines += [f"## {n}. {question}", "",
                  f"{len(items)} flags ({high} high-confidence, {len(items) - high} needs expert). Examples:", ""]
        for i in items[:3]:
            lines.append(f"- {i['reg_number']}: {i['title'][:120]} {i['url']}")
        lines += ["", "Answer: [ ] the 3-month rule applies   [ ] it does not apply   [ ] depends on: ________", ""]
    rest = by_group.get("other", [])
    lines += [f"## Not grouped: {len(rest)} flags", "",
              "These are reviewed one by one in `research/flags_for_lawyer_round1.csv`.", "",
              (f"Coverage: the {len(GROUPS)} questions settle {covered} of {len(rows)} flags "
              f"({covered / max(len(rows), 1):.0%}).")]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{covered} of {len(rows)} flags covered by {len(GROUPS)} questions -> {OUT}")


if __name__ == "__main__":
    main()
