"""Trust table for MezonBench predictions: accuracy alone hides confident errors (Opus closed book wins by abstaining).

    .venv/Scripts/python.exe -X utf8 -m research.bench_trust name=preds.jsonl [name=preds.jsonl ...]

Per file, on the CLEAN items it answered: right / wrong / noaniq, accuracy, selective accuracy (right / answered),
coverage (answered / N) and the strict score (right * 1 - wrong * 1.5) / N, the strict judge's reward without the
+0.2 for warranted noaniq (v1 has no unanswerable items, so every noaniq scores 0 here).
"""

import json
import sys
from collections import Counter
from pathlib import Path

from research.mezonbench import grade

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench" / "mezonbench_v1.jsonl"
EXCL = set(json.loads((ROOT / "data" / "bench" / "excluded_ids.json").read_text(encoding="utf-8")))


def table(files: dict[str, str]) -> None:
    items = {json.loads(x)["id"]: json.loads(x) for x in BENCH.read_text(encoding="utf-8").split("\n") if x.strip()}
    preds = {k: {json.loads(x)["id"]: json.loads(x).get("answer", "") for x in Path(v).read_text(encoding="utf-8").split("\n")
                 if x.strip()} for k, v in files.items()}
    common = set.intersection(*(set(p) for p in preds.values())) - EXCL
    print(f"same {len(common)} CLEAN items in every file")
    print(f"{'model':28} {'right':>5} {'wrong':>5} {'noaniq':>6} {'acc':>6} {'selective':>9} {'coverage':>8} {'strict':>7}")
    for k, p in preds.items():
        c = Counter(grade(items[i], p[i]) for i in common)
        n, ans = len(common), c["right"] + c["wrong"]
        print(f"{k:28} {c['right']:5d} {c['wrong']:5d} {c['abstain']:6d} {c['right'] / n:6.3f} "
              f"{c['right'] / max(ans, 1):9.3f} {ans / n:8.3f} {(c['right'] - 1.5 * c['wrong']) / n:7.3f}")


if __name__ == "__main__":
    table(dict(a.split("=", 1) for a in sys.argv[1:]))
