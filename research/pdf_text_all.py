"""Fast text for every lex.uz PDF that HAS a text layer (16,647 of 18,721): pdftotext -layout, no OCR needed.

    nice -n 15 .venv/bin/python -X utf8 -m research.pdf_text_all 0/3     # 3 shards in parallel on the L40S

Reads data/ocr/scans.jsonl (which PDFs have text), writes data/pdftext/<key>.txt (UTF-8). Scanned PDFs are skipped:
OCR handles them (data/ocr/). ASCII temp names (pdftotext can't open Cyrillic paths on some systems). Resumable.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from research.ocr_scans import FILES, SCANS, pdfs_in

OUT = Path(__file__).resolve().parents[1] / "data" / "pdftext"


def main() -> None:
    k, n = (int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "0/1").split("/"))
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [json.loads(line) for line in SCANS.open(encoding="utf-8")]
    todo = [r for i, r in enumerate(todo) if not r["scanned"] and i % n == k and not (OUT / f"{r['key']}.txt").exists()]
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for r in todo:
            pdf = dict(pdfs_in(FILES / r["file"])).get(r["key"])
            if pdf is None:
                continue
            src, dst = Path(tmp) / "x.pdf", Path(tmp) / "x.txt"
            src.write_bytes(pdf)
            subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(src), str(dst)], check=False)
            if dst.exists():
                (OUT / f"{r['key']}.txt").write_text(dst.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                dst.unlink()
            done += 1
            if done % 1000 == 0:
                print(f"shard {k}/{n}: {done}/{len(todo)}", flush=True)
    print(f"PDFTEXT DONE shard {k}/{n}: {done}", flush=True)


if __name__ == "__main__":
    main()
