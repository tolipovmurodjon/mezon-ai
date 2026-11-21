"""The numbers said on stage, printed from their sources in one place (run 10 minutes before the pitch).

    .venv/Scripts/python.exe -X utf8 -m research.stage_numbers

Reads eval/report.md (written by `python -m eval.run`) and the running demo server's /api/live-drafts. Nothing here
is typed by hand: if a source is missing, the line says so instead of guessing.
"""

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "eval" / "report.md"
LIVE = "http://127.0.0.1:8090/api/live-drafts"


def _report() -> dict:
    if not REPORT.exists():
        return {}
    t = REPORT.read_text(encoding="utf-8")
    out = {}
    m = re.search(r"\| cancelled, with text \| (\d+) \| (\d+)/\d+ = [\d.]+% \| (\d+)/", t)
    if m:
        out["cancelled_n"], out["cancelled_flagged"], out["cancelled_high"] = m.groups()
    m = re.search(r"\*\*Citation validity\*\*[^:]*: (\d+)/(\d+)", t)
    if m:
        out["cit_ok"], out["cit_n"] = m.groups()
    m = re.search(r"\*\*Lawyer precision:\*\* (.+)", t)
    if m:
        out["lawyer"] = m.group(1).strip()
    m = re.search(r"# Mezon eval \(([\d-]+)\)", t)
    if m:
        out["date"] = m.group(1)
    return out


def _live() -> dict:
    try:
        with urllib.request.urlopen(LIVE, timeout=30) as r:
            d = json.load(r)
    except OSError:
        return {}
    return {"today": d["today"], "short": len(d["short"]), "rest": d.get("open_normative_candidates"),
            "open": d["open_local"], "budget": d.get("budget_allocations")}


def main() -> None:
    r, live = _report(), _live()
    print(f"eval/report.md ({r.get('date', 'missing: run python -m eval.run')})")
    if "cancelled_n" in r:
        print(f"  cancelled decisions with text: {r['cancelled_flagged']} of {r['cancelled_n']} flagged, "
              f"{r['cancelled_high']} high-confidence")
    if "cit_n" in r:
        print(f"  citations verbatim in the edition on the decision date: {r['cit_ok']} of {r['cit_n']}")
    print(f"  lawyer precision: {r.get('lawyer', 'missing')}")
    if live:
        print(f"live drafts ({live['today']}): {live['short']} of {live['rest']} open local drafts under 15 days "
              f"(budget allocations set aside: {live['budget']} of {live['open']})")
    else:
        print("live drafts: the demo server is not running (start uvicorn on :8090)")


if __name__ == "__main__":
    main()
