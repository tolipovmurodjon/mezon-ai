"""L40S: one status line (lex.uz pass 2 progress, speed, ETA, errors; OCR progress)."""
import json
import sqlite3
from pathlib import Path

c = sqlite3.connect("data/raw/lexuz_full/state.sqlite", timeout=60)
s = dict(c.execute("select status, count(*) from acts group by 1").fetchall())
r = c.execute("select count(*) from acts where status='done' and done_at > datetime('now','-5 minutes')").fetchone()[0]
left = s.get("done1", 0)
eta = left / r * 5 / 60 if r else 0
done = Path("data/ocr/done.jsonl")
d = [json.loads(x) for x in done.open(encoding="utf-8")] if done.exists() else []
failed = sum(1 for p in Path("data/ocr").glob("*/page-*.md") if "OCR failed" in p.read_text(encoding="utf-8", errors="replace"))
print(f"lex.uz fully done {s.get('done', 0):,} | pass-2 left {left:,} | +{r} in 5 min | ETA {eta:.1f} h | "
      f"errors {s.get('error', 0)} | OCR {len(d)}/2,074 docs, {sum(x['pages'] for x in d):,} pages, failed pages {failed}")
