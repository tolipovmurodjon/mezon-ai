"""Run under the Mezon venv: audit every lex.uz decision with text once; write tmp_real/audit_all.json."""
import json
import sys
import time

sys.path.insert(0, r"D:\10_projects\mezon")
from mezon.decisions.store import DecisionStore  # noqa: E402
from mezon.rules.run import audit, load_law  # noqa: E402

OUT = r"D:\10_projects\mezon_platform_original\tmp_real\audit_all.json"
ds = DecisionStore()
law = load_law()
rows = ds.con.execute(
    "SELECT id, reg_number, title, body, adopted, url, length(text) AS n, type, region, district, role, source FROM decisions "
    "WHERE role IN ('adopted','cancelling') AND length(text)>300 ORDER BY adopted DESC").fetchall()
res, t0 = {}, time.time()
for i, r in enumerate(rows):
    try:
        rep = audit(r["id"], law, ds)
        flags = len(rep.flags)
        verdict = rep.verdict
        n_unclear = sum(1 for f in rep.flags if f.status == "unclear_needs_expert")
        n_high = flags - n_unclear
        checks = sorted({f.check for f in rep.flags})
    except Exception as e:  # noqa: BLE001
        flags, verdict, n_high, n_unclear, checks = -1, "error", 0, 0, []
    key = r["reg_number"] or r["id"]
    cur = res.get(key)
    if cur is None or r["n"] > cur["len"]:
        res[key] = {"id": r["id"], "reg": r["reg_number"], "title": r["title"], "body": r["body"], "adopted": r["adopted"], "url": r["url"],
                    "len": r["n"], "type": r["type"], "region": r["region"], "district": r["district"], "role": r["role"],
                    "flags": flags, "verdict": verdict, "n_high": n_high, "n_unclear": n_unclear, "checks": checks}
    if i % 50 == 0:
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
        print(i, len(rows), round(time.time() - t0), flush=True)
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("done", len(res), round(time.time() - t0), flush=True)
