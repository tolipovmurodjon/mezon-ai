"""Leaderboard: grade every run file in data/bench/audit_v1/runs/ and print one table (also written to leaderboard.md).

    .venv/Scripts/python.exe -X utf8 -m research.audit_bench.leaderboard [--public-only]

Run files named NAME_run1.jsonl, NAME_run2.jsonl ... are one model run k times (pass^k); any other NAME.jsonl is one run.
Every cell is a percentage with N; the intervals are 95 % Wilson (see grade.py). Baselines are rows like any model.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.audit_bench.grade import (
    RESULTS,
    SPLITS,
    collect,
    grade_run,
    pass_hat_k,
    read_run,
    summarise,
    wilson,
)

RUNS = ROOT / "data" / "bench" / "audit_v1" / "runs"
ORDER = ["oracle", "engine", "always-negative", "always-positive", "empty"]


def cell(k: int, n: int) -> str:
    if not n:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.0f}% [{100 * lo:.0f}-{100 * hi:.0f}] ({k}/{n})"


def split_cell(sp: dict, key: str) -> str:
    return cell(sp[key]["resolved"], sp[key]["n"]) if key in sp else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-only", action="store_true")
    a = ap.parse_args()
    from mezon.lawstore.store import LawStore

    law = LawStore()
    items = collect(SPLITS, private=not a.public_only)
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(RUNS.glob("*.jsonl")):
        groups[re.sub(r"_run\d+$", "", p.stem)].append(p)
    rows = []
    for name, files in groups.items():
        per_run = [grade_run(law, items, read_run(p)) for p in files]
        s = summarise(per_run[0])
        ph = pass_hat_k(per_run) if len(per_run) > 1 else {}
        rows.append((name, len(files), s, ph))
    rows.sort(
        key=lambda r: (ORDER.index(r[0]) if r[0] in ORDER else -1, -r[2]["macro_resolved"]), reverse=False
    )
    models = [r for r in rows if r[0] not in ORDER]
    base = sorted((r for r in rows if r[0] in ORDER), key=lambda r: ORDER.index(r[0]))
    n_pub = sum(1 for _, _, x in items if x == "public")
    head = f"MezonAudit-bench audit_v1 | N={len(items)} instances (public {n_pub}, private {len(items) - n_pub}) | 95% Wilson [lo-hi]"
    cols = [
        "run",
        "k",
        "REAL resolved",
        "SMITH resolved",
        "CLEAN resolved",
        "false alarm (CLEAN)",
        "cit. valid",
        "macro",
        "pass^k",
    ]
    out = [head, " | ".join(cols)]
    for name, k, s, ph in sorted(models, key=lambda r: -r[2]["macro_resolved"]) + base:
        sp = s["splits"]
        cits = sum(v["citations"] for v in sp.values())
        ok = sum(v["cit_ok"] for v in sp.values())
        fa = cell(sp["clean"]["false_alarm"], sp["clean"]["n"]) if "clean" in sp else "n/a"
        out.append(
            " | ".join(
                [
                    name,
                    str(k),
                    split_cell(sp, "real"),
                    split_cell(sp, "smith"),
                    split_cell(sp, "clean"),
                    fa,
                    (f"{100 * ok / cits:.0f}% ({ok}/{cits} citations)" if cits else "no citations"),
                    f"{100 * s['macro_resolved']:.1f}%",
                    ", ".join(f"^{i} {100 * v:.0f}%" for i, v in ph.items()) or "k=1",
                ]
            )
        )
    live = sum(1 for _, g, _ in items if g["split"] == "live")
    out.append(
        f"LIVE split: N={live} (decisions adopted after 2026-11-22; empty until the daily sync fills it)"
    )
    text = "\n".join(out)
    print(text)
    RESULTS.parent.joinpath("leaderboard.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
