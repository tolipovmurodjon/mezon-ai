"""Before going on stage: does every decision we show still give the verdict the deck and the script promise?

    .venv/Scripts/python.exe -X utf8 -m research.demo_check

Exits 1 and names the case if any verdict, flag or queue status changed (after a rule change, a crawl or a rebuild).
"""

import sys

from mezon.api.main import _decisions, queue
from mezon.rules.run import audit, load_law
from research.regnum import REGIONS

# reg number -> (verdict, a check that must be among the flags or None, must it be in the adliya queue?)
EXPECTED = {
    "231-4-59-Q/24": ("negative", "R_duplicate", False),            # Qarshi copy, cancelled on adliya representation
    "269-4-59-Q/24": ("negative", "R_double_repeal", False),        # the repeat six days later
    "207-4-59-Q/24": ("positive", None, False),                     # the original, 8 explained checks
    "VII-3-1-5-77-K/25": ("negative", "R_retroactive", False),      # retroactive; cancelled on adliya representation
    "265-4-60-Q/25": ("positive_with_fixable_defects", "R_corruption_factor", True),
    "VII-18-37-3-44-K/26": ("positive", None, False),               # uses the 3-month delay correctly
    "355-4-68-Q/25": ("positive_with_fixable_defects", "R_basis", True),  # cites dead LSP art. 25
    "VI-76-4-10-146-K/24": ("positive_with_fixable_defects", "R_discussion", False),  # Yangiyo'l, cancelled
}


def main() -> int:
    law, bad = load_law(), []
    in_queue = {i["reg_number"] for i in queue(limit=200)["items"]}
    if queue(limit=200)["total"] > 200:  # the queue is capped at 200 rows; check membership region by region
        in_queue = {i["reg_number"] for r in REGIONS for i in queue(region=r, limit=200)["items"]}
    for reg, (verdict, check, queued) in EXPECTED.items():
        ids = _decisions.by_reg(reg)
        if not ids:
            bad.append(f"{reg}: not in the store")
            continue
        r = audit(ids[0], law=law, decisions=_decisions).to_dict()
        checks = {f["check"] for f in r["flags"]}
        problems = [f"verdict {r['verdict']} (expected {verdict})"] if r["verdict"] != verdict else []
        if check and check not in checks:
            problems.append(f"{check} missing")
        if (reg in in_queue) != queued:
            problems.append("in queue" if reg in in_queue else "not in queue")
        print(f"{'OK ' if not problems else 'BAD'} {reg:24} {r['verdict']:30} {', '.join(problems)}")
        bad += [f"{reg}: {p}" for p in problems]
    print("demo path OK" if not bad else f"{len(bad)} problem(s): fix before the demo")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
