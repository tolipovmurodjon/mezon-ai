"""L40S: what are the lex.uz error rows? Group by reason; check the document page (pass-1 content) is cached."""
import re
import sqlite3
from collections import Counter
from pathlib import Path

c = sqlite3.connect("data/raw/lexuz_full/state.sqlite", timeout=60)
rows = c.execute("select lex_id, prio, title from acts where status='error'").fetchall()
why = Counter()
for lex_id, prio, msg in rows:
    m = re.search(r"/uz/([a-z]+)(?:/([a-z0-9]+))?[^ ]*?(\?type=pdf)?: .*?'(\d{3}) ([A-Za-z ]+)'", msg or "")
    why[(m.group(1) + ("/" + m.group(2) if m.group(2) and m.group(1) == "actinfo" else "") + (" ?type=pdf" if m.group(3) else ""), m.group(4)) if m else ("other", (msg or "")[:40])] += 1
print("by reason:", why.most_common(8))
print("by priority (0 core, 1 local decisions, 2 national/other):", Counter(p for _, p, _ in rows))
docs = Path("data/cache/lexuz/docs")
have = sum((docs / f"{i.lstrip('-')}_{'m' if i.startswith('-') else 'p'}.html").exists() for i, _, _ in rows)
print(f"main text page cached for {have} of {len(rows)} error rows")
