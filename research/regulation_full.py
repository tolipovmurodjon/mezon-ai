"""Download every regulation.gov.uz draft page (ids 1..--max) and the text PDF of each draft, cache-first and polite.

    MEZON_SHARD=0/4 .venv/bin/python -X utf8 -m research.regulation_full --max 118400     # on the L40S, 4 shards

Pages: data/cache/regulation/d<id>.html; PDFs d<id>_<pdf>.pdf (+ .txt via pdftotext); parsed records appended to
data/raw/regulation/drafts_<k>.jsonl. Resumable: cached ids are not fetched again. 1.2 s between requests per worker
(research/polite_http.py), 4 workers = ~3.3 requests per second. Boss listed regulation.gov.uz for full download.
"""

import argparse
import json
import os
import time

from research.polite_http import ROOT
from research.regulation_window import draft_text, page

OUT = ROOT / "data" / "raw" / "regulation"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=118400)
    a = ap.parse_args()
    k, n = (int(x) for x in os.environ.get("MEZON_SHARD", "0/1").split("/"))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"drafts_{k}.jsonl"
    done = set()
    for prev in OUT.glob("drafts_*.jsonl"):  # every shard file and the merged list: re-sharding never refetches
        done |= {json.loads(line)["id"] for line in prev.open(encoding="utf-8")}
    if (OUT / "_done_before_reshard.jsonl").exists():
        done |= {json.loads(line)["id"] for line in (OUT / "_done_before_reshard.jsonl").open(encoding="utf-8")}
    t0, got = time.time(), 0
    with out.open("a", encoding="utf-8") as f:
        for i in range(a.max, 0, -1):  # newest first
            if i % n != k or i in done:
                continue
            try:
                rec = page(i)
            except Exception as e:  # noqa: BLE001 - a bad id must not stop the run
                print(f"{i}: {e}", flush=True)
                continue
            if not rec:
                f.write(json.dumps({"id": i, "missing": True}) + "\n")
                continue
            if rec.get("pdf_ids"):
                try:
                    rec["text_chars"] = len(draft_text(rec))
                except Exception as e:  # noqa: BLE001
                    rec["text_error"] = str(e)[:120]
            rec["id"] = i
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            got += 1
            if got % 200 == 0:
                f.flush()
                print(f"shard {k}/{n}: {got} drafts this run, at id {i}, {time.time() - t0:.0f}s", flush=True)
    print(f"REGULATION DONE shard {k}/{n}", flush=True)


if __name__ == "__main__":
    main()
