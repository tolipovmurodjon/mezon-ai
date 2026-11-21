"""Recompute the headline closed-book table from the committed answer files (anyone can verify it).

    python -X utf8 -m research.headline
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.mezonbench_v2 import grade

B = ROOT / "data" / "bench"
RUNS = {"Qwen3.8-27B base": B / "v21_base_closed20.jsonl", "+ law school": B / "v21_law_closed20.jsonl",
        "Mezon-LM (+ internship)": B / "v21_chain_closed20.jsonl",
        "Claude Opus 5.5": B / "frontier" / "opus55_v21_closed.jsonl"}


def load(p: Path) -> dict:
    return {json.loads(x)["id"]: json.loads(x).get("answer", "") for x in p.open(encoding="utf-8") if x.strip()}


def main() -> None:
    items = {json.loads(x)["id"]: json.loads(x) for x in (B / "mezonbench_v2_2.jsonl").open(encoding="utf-8") if x.strip()}
    ans = {k: load(v) for k, v in RUNS.items()}
    ids = sorted(set(items).intersection(*map(set, ans.values())))
    n = len(ids)
    print(f"MezonBench v2.2, closed book, the same {n} questions for every model")
    g = {}
    for k, a in ans.items():
        g[k] = {i: grade(items[i], a[i]) for i in ids}
        c = Counter(g[k].values())
        print(f"{k:25} right {c['right']:3} ({c['right'] / n:5.1%})  wrong {c['wrong']:3}  noaniq {c['abstain']:3}  "
              f"strict {(c['right'] - 1.5 * c['wrong']) / n:+.3f}")
    a, o = g["Mezon-LM (+ internship)"], g["Claude Opus 5.5"]
    b = sum(a[i] == "right" and o[i] != "right" for i in ids)
    c = sum(a[i] != "right" and o[i] == "right" for i in ids)
    z = (abs(b - c) - 1) / math.sqrt(b + c) if b + c else 0.0
    print(f"McNemar (right answers), Mezon-LM vs Opus: {b} vs {c} discordant, z = {z:.2f}")


if __name__ == "__main__":
    main()
