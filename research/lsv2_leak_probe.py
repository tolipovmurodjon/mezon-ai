"""Independent leak probe: do any written law rows mention an exam act title together with an exam article number?
usage: python -m research.lsv2_leak_probe   (reads data/bench/_leak_probe.json made from the bench files + the lawschool_v2 shards)"""
import gzip
import json
import re
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "data"
probe = json.loads((D / "bench" / "_leak_probe.json").read_text(encoding="utf-8"))
by_title = {}
for t, a, _ in probe:
    by_title.setdefault(t[:40], set()).add(a)
hits = rows = 0
ex = []
for f in sorted((D / "train" / "lawschool_v2").glob("lawschool_v2-r*.jsonl.gz")):
    for line in gzip.open(f, "rt", encoding="utf-8"):
        r = json.loads(line)
        if r.get("kind") != "law" or r["src"] == "hierarchy":
            continue
        rows += 1
        head = r["text"][:400]
        for t, arts in by_title.items():
            if t in head:
                for a in arts:
                    if re.search(rf"(?<!\d){re.escape(a)}-modda", head):
                        hits += 1
                        ex.append((r["src"], t, a))
print({"law_rows_scanned": rows, "probe_titles": len(by_title), "hits": hits, "examples": ex[:5]})
