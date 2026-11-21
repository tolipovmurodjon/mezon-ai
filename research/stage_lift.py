"""Skip rates of E-qaror adoption stages in declared-invalid (bad) vs in-force (control) decisions, with 95% CIs."""

import csv
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "interim" / "eqaror_stages.csv"
Z = 1.959964


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (c - h, c + h)


def risk_ratio(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Ratio of skip rates bad/control with a log-RR CI (0.5 added to every cell when one is zero)."""
    if 0 in (k1, k2, n1 - k1, n2 - k2):
        k1, n1, k2, n2 = k1 + 0.5, n1 + 1, k2 + 0.5, n2 + 1
    rr = (k1 / n1) / (k2 / n2)
    se = math.sqrt(1 / k1 - 1 / n1 + 1 / k2 - 1 / n2)
    return rr, math.exp(math.log(rr) - Z * se), math.exp(math.log(rr) + Z * se)


def load() -> list[dict]:
    with CSV.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r["all_stages_json"]]


def line(rows: list[dict], stage: str, label: str, bad_sets: tuple[str, ...], ctrl_sets: tuple[str, ...]) -> str:
    bad = [r for r in rows if r["set"] in bad_sets and r[stage] in ("0", "1")]
    ctl = [r for r in rows if r["set"] in ctrl_sets and r[stage] in ("0", "1")]
    kb, nb = sum(r[stage] == "0" for r in bad), len(bad)
    kc, nc = sum(r[stage] == "0" for r in ctl), len(ctl)
    if not nb or not nc:
        return f"| {label} | {stage} | {kb}/{nb} | {kc}/{nc} | n/a |"
    lb, ub = wilson(kb, nb)
    lc, uc = wilson(kc, nc)
    rr, lo, hi = risk_ratio(kb, nb, kc, nc)
    return (f"| {label} | {stage.replace('_done', '')} skipped | {kb}/{nb} = {kb/nb:.0%} [{lb:.0%}-{ub:.0%}] | "
            f"{kc}/{nc} = {kc/nc:.0%} [{lc:.0%}-{uc:.0%}] | {rr:.2f} [{lo:.2f}-{hi:.2f}] |")


def main() -> None:
    rows = load()
    print("rows with a stage tracker:", Counter(r["set"] for r in rows))
    print("bad by asos_kind:", Counter(r["asos_kind"] or "none" for r in rows if r["set"] == "bad"))
    print()
    print("| comparison | stage | bad: skipped/N [95% CI] | control: skipped/N [95% CI] | lift (RR) [95% CI] |")
    print("|---|---|---|---|---|")
    groups = [
        ("all bad vs all controls", ("bad",), ("ctrl_norm", "ctrl_nonnorm")),
        ("normative bad vs normative ctrl", ("bad_n",), ("ctrl_norm",)),
        ("non-normative bad vs non-normative ctrl", ("bad_nn",), ("ctrl_nonnorm",)),
    ]
    for r in rows:
        if r["set"] == "bad":
            r2 = dict(r, set="bad_n" if r["is_normative"] == "1" else "bad_nn")
            rows.append(r2)
    for label, b, c in groups:
        for stage in ("discussion_done", "expertise_done", "lawyer_done"):
            print(line(rows, stage, label, b, c))
    for yrs, lab in (({"2021", "2022"}, "2021-22"), ({"2023", "2024", "2025", "2026"}, "2023-26")):
        sub = [r for r in rows if r["year"] in yrs]
        for stage in ("expertise_done",):
            print(line(sub, stage, f"non-normative {lab}", ("bad_nn",), ("ctrl_nonnorm",)))


if __name__ == "__main__":
    main()
