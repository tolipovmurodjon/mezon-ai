"""Run on the GPU box: for lex.uz local decisions that have extracted text (data/pdftext) and a lex.uz metadata
entry-into-force date (offline_acts.effective), dump the first business-burden clause found by the rule engine,
the entry-into-force sentence, and the dates. Output: one CSV for mezonbench_v3 (three_month, defect_spot).

    python3 research/v3_extract_text.py ~/mezon /tmp/v3_out
"""

import csv
import sqlite3
import sys
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(root))
from mezon.rules import business as b
from mezon.rules.procedure import is_budget_allocation
from research.regulation_window import entry_into_force
from research.textnorm import fold

c = sqlite3.connect(f"file:{root}/data/raw/lexuz_full/state.sqlite?mode=ro", uri=True)
cat = {
    str(r[0]): r
    for r in c.execute(
        "select lex_id,title,body,adopted,number from catalog where lang='uz_latn' and adopted is not null "
        "and (body like '%hokimining qarori' or body like '%Kengashining qarori' or body like '%Kengashi qarori') "
        "and body not like '%Oliy%'"
    )
}
eff = {}
for r in c.execute("select lex_id,effective,obsolete,number from offline_acts where lang='uz_latn'"):
    eff[str(r[0])] = r
print(len(cat), "catalog local;", len(eff), "offline_acts")
import glob
import gzip
import json

n_text = 0
w = csv.writer((out / "lex_local_text.csv").open("w", encoding="utf-8", newline=""))
w.writerow(
    [
        "lex_id",
        "number",
        "title",
        "body",
        "adopted",
        "effective",
        "obsolete",
        "clause_no",
        "clause",
        "burden_money",
        "burden_obl",
        "business",
        "quota_or_tax",
        "budget_alloc",
        "eif_kind",
        "eif_sentence",
        "source_kind",
        "n_chars",
    ]
)
for f in sorted(glob.glob(str(root / "data/refinery/full/01_extract/acts/*.gz"))):
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        for line in fh:
            j = json.loads(line)
            lid = str(j["lex_id"])
            if lid not in cat:
                continue
            if lid not in eff or j["source_kind"] not in ("pdf_text", "html"):
                continue
            text = chr(10).join((blk.get("text") or "") for blk in j["blocks"])
            if len(text) < 300:
                continue
            n_text += 1
            fnd = b.burden_clause(text)
            if not fnd:
                continue
            n, cl, bd = fnd
            t = cat[lid]
            e = entry_into_force(text)
            qt = bool(b.JOB_QUOTA.search(fold(t[1]))) or bool(b.TAX_RATE.search(fold(t[1])))
            w.writerow(
                [
                    lid,
                    t[4],
                    t[1],
                    t[2],
                    t[3],
                    eff[lid][1],
                    eff[lid][2],
                    n,
                    cl[:900],
                    int(bd["money"]),
                    int(bd["obligation"]),
                    int(bd["business"]),
                    int(qt),
                    int(is_budget_allocation(t[1])),
                    e["kind"],
                    e["sentence"][:300],
                    j["source_kind"],
                    len(text),
                ]
            )
print(n_text, "with text and metadata")
