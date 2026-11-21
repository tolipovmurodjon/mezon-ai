"""L40S: why did 'missing' jump? Columns, latest rows and reasons for missing / error."""
import sqlite3
c = sqlite3.connect("data/raw/lexuz_full/state.sqlite", timeout=60)
cols = [r[1] for r in c.execute("pragma table_info(acts)")]
print("columns:", cols)
for st in ("missing", "error"):
    print(st, "latest:", c.execute(f"select * from acts where status='{st}' order by rowid desc limit 3").fetchall())
    for col in cols:
        if col in ("lex_id", "status", "title", "url"):
            continue
        top = c.execute(f"select substr(cast({col} as text),1,50), count(*) from acts where status='{st}' group by 1 order by 2 desc limit 4").fetchall()
        if len(top) < 4 or top[0][1] > 50:
            print(f"  {st}.{col}:", top)
