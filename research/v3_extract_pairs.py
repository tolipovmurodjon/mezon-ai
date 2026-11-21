"""Run on the GPU box: pairs (original local decision, cancelling decision) where the cancelling act cites an official
trigger (adliya representation, prosecutor protest, court ruling). Output data: pairs.jsonl for mezonbench_v3.

    python3 research/v3_extract_pairs.py ~/mezon /tmp/v3_out
"""

import glob
import gzip
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root))
from research import regnum
from research.label_cancellations import label

c = sqlite3.connect(f"file:{root}/data/raw/lexuz_full/state.sqlite?mode=ro", uri=True)
cat = {
    str(r[0]): r
    for r in c.execute(
        "select lex_id,title,body,adopted,number from catalog where lang='uz_latn' and adopted is not null "
        "and (body like '%hokimining qarori' or body like '%Kengashining qarori' or body like '%Kengashi qarori') "
        "and body not like '%Oliy%'"
    )
}
eff = {
    str(r[0]): r for r in c.execute("select lex_id,effective,obsolete from offline_acts where lang='uz_latn'")
}
texts = {}
for f in sorted(glob.glob(str(root / "data/refinery/full/01_extract/acts/*.gz"))):
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for line in fh:
            j = json.loads(line)
            lid = str(j["lex_id"])
            if lid in cat and j["source_kind"] in ("pdf_text", "html"):
                t = chr(10).join((b.get("text") or "") for b in j["blocks"])
                if len(t) > 300:
                    texts[lid] = t
print(len(cat), "catalog;", len(texts), "with text")
by_num = defaultdict(list)
for lid, r in cat.items():
    by_num[(r[4] or "").strip().lower()].append(lid)
n_pairs = 0
from collections import Counter

dbg = Counter()
with (out / "pairs.jsonl").open("w", encoding="utf-8") as w:
    for lid, r in cat.items():
        if "bekor qil" not in r[1].lower() or lid not in texts:
            continue
        lab, trig, ev = label(r[1], texts[lid])
        dbg["cancel_with_text"] += 1
        dbg[lab] += 1
        if lab != "POSITIVE":
            continue
        for num in regnum.find_all(r[1]):
            key = num["raw"].strip().lower()
            dbg["nums"] += 1
            dbg["in_catalog"] += key in by_num
            dbg["with_text"] += any(x in texts for x in by_num.get(key, []))
            if key == (r[4] or "").strip().lower():
                continue
            cands = [x for x in by_num.get(key, []) if x != lid and x in texts]
            if len(cands) != 1:
                continue
            o = cands[0]
            w.write(
                json.dumps(
                    {
                        "cancelling": {
                            "lex_id": lid,
                            "number": r[4],
                            "adopted": r[3],
                            "title": r[1],
                            "body": r[2],
                            "trigger": trig,
                            "evidence": ev,
                            "text": texts[lid][:8000],
                        },
                        "original": {
                            "lex_id": o,
                            "number": cat[o][4],
                            "adopted": cat[o][3],
                            "title": cat[o][1],
                            "body": cat[o][2],
                            "effective": (eff.get(o) or [None, None])[1],
                            "text": texts[o][:40000],
                        },
                    },
                    ensure_ascii=False,
                )
                + chr(10)
            )
            n_pairs += 1
print(n_pairs, "pairs", dict(dbg))
