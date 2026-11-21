"""Paired comparison of two MezonBench prediction files on the same items (the test the v2 decision rule needs).

    .venv/Scripts/python.exe -X utf8 -m research.bench_compare data/bench/preds_base.jsonl data/bench/preds_cpt_v11.jsonl

Only items present in both files and not in data/bench/excluded_ids.json (the CLEAN set). Per family and overall:
accuracy of each, the gap, and McNemar's exact test (two-sided binomial on the items where exactly one is right).
"""

import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

from research.mezonbench import OUT, grade


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: b = only A right, c = only B right."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * p)


def load(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    return {json.loads(x)["id"]: json.loads(x).get("answer", "") for x in text.split("\n") if x.strip()}


def compare(path_a: str, path_b: str) -> dict:
    items = {json.loads(x)["id"]: json.loads(x) for x in OUT.read_text(encoding="utf-8").split("\n") if x.strip()}
    excl_f = OUT.parent / "excluded_ids.json"
    excl = set(json.loads(excl_f.read_text(encoding="utf-8"))) if excl_f.exists() else set()
    a, b = load(path_a), load(path_b)
    cells = defaultdict(lambda: [0, 0, 0, 0])  # both right, only A, only B, both not right
    for iid in sorted(set(a) & set(b) - excl):
        it = items.get(iid)
        if not it:
            continue
        ra, rb = grade(it, a[iid]) == "right", grade(it, b[iid]) == "right"
        k = 0 if ra and rb else 1 if ra else 2 if rb else 3
        for fam in (it["family"], "ALL"):
            cells[fam][k] += 1
    out = {}
    print(f"A = {path_a}\nB = {path_b}\n{'family':10s} {'N':>4s} {'acc A':>7s} {'acc B':>7s} {'gap':>7s} "
          f"{'onlyA':>6s} {'onlyB':>6s} {'McNemar p':>10s}")
    for fam in sorted(cells, key=lambda f: (f == "ALL", f)):
        both, oa, ob, none = cells[fam]
        n = both + oa + ob + none
        acc_a, acc_b = (both + oa) / n, (both + ob) / n
        p = mcnemar_exact(oa, ob)
        out[fam] = {"n": n, "acc_a": round(acc_a, 3), "acc_b": round(acc_b, 3), "only_a": oa, "only_b": ob, "p": p}
        print(f"{fam:10s} {n:4d} {acc_a:7.3f} {acc_b:7.3f} {acc_b - acc_a:+7.3f} {oa:6d} {ob:6d} {p:10.4f}")
    return out


if __name__ == "__main__":
    compare(sys.argv[1], sys.argv[2])
