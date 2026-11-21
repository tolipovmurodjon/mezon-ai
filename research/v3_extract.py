"""Run on the GPU box: dump (1) local regulation.gov.uz drafts with discussion dates, (2) lex.uz local decisions
(body, adopted date, number, title) from the crawl catalog, as two small CSVs for mezonbench_v3 to join.

    python3 research/v3_extract.py ~/mezon /tmp/v3_out
"""

import csv
import sys
from multiprocessing import Pool
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
sys.path.insert(0, str(root))
from research.regulation_window import is_local, parse_page


def one(p):
    try:
        if p.stat().st_size < 20000:
            return None
        r = parse_page(p.read_text(encoding="utf-8", errors="replace"))
        return r if r and is_local(r["creator"]) else None
    except OSError:
        return None


if __name__ == "__main__":
    out.mkdir(exist_ok=True)
    files = sorted((root / "data/cache/regulation").glob("d*.html"))
    with Pool(12) as pool:
        rows = [r for r in pool.imap_unordered(one, files, chunksize=200) if r]
    with (out / "reg_drafts_local.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "creator", "title", "start", "end", "proposals"])
        for r in sorted(rows, key=lambda r: r["id"]):
            w.writerow([r["id"], r["creator"], r["title"], r["start"], r["end"], r["proposals"]])
    import sqlite3

    c = sqlite3.connect(f"file:{root}/data/raw/lexuz_full/state.sqlite?mode=ro", uri=True)
    q = (
        "select lex_id,title,badge,body,adopted,number from catalog where lang='uz_latn' and adopted is not null "
        "and (body like '%hokimining qarori' or body like '%Kengashining qarori' or body like '%Kengashi qarori')"
    )
    with (out / "lex_local_catalog.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lex_id", "title", "badge", "body", "adopted", "number"])
        n = 0
        for r in c.execute(q):
            w.writerow(r)
            n += 1
    print(len(files), "files;", len(rows), "local drafts;", n, "catalog decisions")
