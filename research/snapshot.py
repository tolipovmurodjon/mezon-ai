"""Save today's per-region counts so the region report can show the change since the last snapshot.

    .venv/Scripts/python.exe -X utf8 -m research.snapshot      # after `python -m mezon.rules.run --all`

Writes data/interim/snapshots/<date>.json: {region code: {section: count}}. Counts come from the same queue the screen
uses, so a fall from one snapshot to the next means flagged decisions were fixed, cancelled or re-adopted correctly.
"""

import datetime as dt
import json
from pathlib import Path

from mezon.api.main import queue
from mezon.version import ruleset
from research.regnum import REGIONS

DIR = Path(__file__).resolve().parents[1] / "data" / "interim" / "snapshots"


SECTIONS = {
    "flagged": lambda i: True,
    "possible_violation": lambda i: i["n_hard"] > 0,
    "dead_article": lambda i: "R_basis" in i["checks"],
    "repeats": lambda i: bool({"R_duplicate", "R_double_repeal"} & set(i["checks"])),
    "corruption_factor": lambda i: "R_corruption_factor" in i["checks"],
}


def counts(items: list[dict]) -> dict:
    """Counts per section, plus the decision ids in each, so a later report can say which ones left and why."""
    out = {name: sum(1 for i in items if test(i)) for name, test in SECTIONS.items()}
    out["ids"] = {name: sorted(i["id"] for i in items if test(i)) for name, test in SECTIONS.items()}
    return out


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    out = {str(code): counts(queue(region=code, limit=200)["items"]) for code in REGIONS}
    out["_ruleset"] = ruleset()
    path = DIR / f"{dt.date.today().isoformat()}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(v['flagged'] for k, v in out.items() if k != '_ruleset')} flagged decisions across {len(out) - 1} regions -> {path}")


if __name__ == "__main__":
    main()
