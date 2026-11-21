"""OCR every scanned lex.uz PDF (no text layer) with PaddleOCR-VL-1.6 on the L40S. Resumable; newest files first.

    ~/ocr-venv/bin/python -X utf8 research/ocr_scans.py scan            # find scanned PDFs -> data/ocr/scans.jsonl
    ~/ocr-venv/bin/python -X utf8 research/ocr_scans.py run 0/3         # worker 0 of 3 (run 3 in parallel on one GPU)
    ~/ocr-venv/bin/python -X utf8 research/ocr_scans.py status

Input: data/cache/lexuz/files/*.zip|*.pdf (local decisions are a PDF inside a ZIP). A PDF counts as scanned when
pdftotext finds < 200 characters on its first 3 pages (measured 20.11: 45 / 355 = 12.7 % of a random sample).
Output per file: data/ocr/<file>/page-NNN.md (PaddleOCR-VL markdown) and data/ocr/<file>.md (all pages joined, with
"<!-- page N -->" markers); data/ocr/done.jsonl logs file, pages, characters, seconds. A file whose .md exists is
skipped, so a rerun continues. Runs with the OCR venv (paddleocr 3.7), not the project venv; stdlib only otherwise.
Pages are rendered at 200 dpi with pdftoppm (poppler). Nothing leaves the machine.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "data" / "cache" / "lexuz" / "files"
OUT = ROOT / "data" / "ocr"
SCANS = OUT / "scans.jsonl"


def pdfs_in(path: Path) -> list[tuple[str, bytes]]:
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        return [(path.stem, data)]
    if path.suffix.lower() == ".zip":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return []
        names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
        return [(f"{path.stem}__{i}" if len(names) > 1 else path.stem, z.read(n)) for i, n in enumerate(names)]
    return []


def text_chars(pdf: Path) -> int:
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-l", "3", str(pdf), "-"], check=False, capture_output=True)
    return len(r.stdout.decode("utf-8", "replace").strip())


def scan() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set()
    if SCANS.exists():
        seen = {json.loads(line)["file"] for line in SCANS.open(encoding="utf-8")}
    files = sorted((p for p in FILES.iterdir() if p.is_file() and p.stat().st_size > 0 and p.name not in seen),
                   key=lambda p: int("".join(ch for ch in p.stem if ch.isdigit()) or 0), reverse=True)
    n = scanned = 0
    with SCANS.open("a", encoding="utf-8") as out, tempfile.TemporaryDirectory() as tmp:
        for p in files:
            for key, data in pdfs_in(p):
                t = Path(tmp) / "x.pdf"
                t.write_bytes(data)
                chars = text_chars(t)
                out.write(json.dumps({"file": p.name, "key": key, "chars": chars, "scanned": chars < 200}) + "\n")
                scanned += chars < 200
            n += 1
            if n % 1000 == 0:
                out.flush()
                print(f"checked {n:,}/{len(files):,} files, scanned PDFs so far {scanned:,}", flush=True)
    print(f"done: {n:,} files checked this run, {scanned:,} scanned PDFs", flush=True)


def run(shard: str) -> None:
    k, n = (int(x) for x in shard.split("/"))
    from paddleocr import PaddleOCRVL  # the OCR venv only

    todo = []
    for line in SCANS.open(encoding="utf-8"):
        r = json.loads(line)
        if r["scanned"] and not (OUT / f"{r['key']}.md").exists():
            todo.append(r)
    todo = [r for i, r in enumerate(todo) if i % n == k]
    print(f"worker {k}/{n}: {len(todo):,} scanned PDFs to read", flush=True)
    server = os.environ.get("OCR_SERVER")  # e.g. http://127.0.0.1:8118/v1 (scripts/ocr_server_start.sh): much faster
    pipe = (PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="vllm-server", vl_rec_server_url=server) if server
            else PaddleOCRVL(pipeline_version="v1.6"))
    for r in todo:
        if (OUT / f"{r['key']}.md").exists():
            continue
        t0 = time.time()
        pdf = dict(pdfs_in(FILES / r["file"])).get(r["key"])
        if pdf is None:
            continue
        work = OUT / r["key"]
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.pdf"
            src.write_bytes(pdf)
            subprocess.run(["pdftoppm", "-r", "200", "-png", str(src), str(Path(tmp) / "p")], check=False)
            pages = sorted(Path(tmp).glob("p-*.png"))
            for i, png in enumerate(pages, 1):
                md_path = work / f"page-{i:03d}.md"
                if md_path.exists():
                    continue
                pdir = Path(tmp) / f"o{i}"
                md = None
                for attempt in range(6):
                    try:
                        for res in pipe.predict(input=str(png)):
                            res.save_to_markdown(save_path=str(pdir))
                        md = "\n".join(f.read_text(encoding="utf-8") for f in sorted(pdir.glob("**/*.md")))
                        break
                    except Exception as e:  # noqa: BLE001 - one bad page must not stop the run
                        if "onnection" in str(e):  # the OCR server is down: never save the error as text, wait
                            print(f"server unreachable ({attempt + 1}/6), waiting 60 s", flush=True)
                            time.sleep(60)
                            continue
                        md = f"<!-- OCR failed: {str(e)[:200]} -->"
                        break
                if md is None:
                    sys.exit(f"worker {k}: OCR server unreachable for 6 min, stopping (nothing bad saved)")
                md_path.write_text(md, encoding="utf-8")
        parts = [f"<!-- page {i} -->\n" + (work / f"page-{i:03d}.md").read_text(encoding="utf-8")
                 for i in range(1, len(list(work.glob("page-*.md"))) + 1)]
        full = "\n\n".join(parts)
        (OUT / f"{r['key']}.md").write_text(full, encoding="utf-8")
        with (OUT / "done.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": r["key"], "file": r["file"], "pages": len(parts), "chars": len(full),
                                "seconds": round(time.time() - t0, 1), "worker": k}) + "\n")
        print(f"{r['key']}: {len(parts)} pages, {len(full):,} chars, {time.time() - t0:.0f}s", flush=True)


def status() -> None:
    scans = [json.loads(line) for line in SCANS.open(encoding="utf-8")] if SCANS.exists() else []
    done = [json.loads(line) for line in (OUT / "done.jsonl").open(encoding="utf-8")] \
        if (OUT / "done.jsonl").exists() else []
    s = sum(r["scanned"] for r in scans)
    pages, secs = sum(d["pages"] for d in done), sum(d["seconds"] for d in done)
    print(f"PDFs checked {len(scans):,} | scanned {s:,} | OCR done {len(done):,} files, {pages:,} pages"
          f"{f', {secs / max(pages, 1):.1f} s/page per worker' if pages else ''}")


if __name__ == "__main__":
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    {"scan": scan, "run": lambda: run(sys.argv[2] if len(sys.argv) > 2 else "0/1"), "status": status}[sys.argv[1]]()
