"""Text for the lex.uz files that hold Word/RTF/Excel instead of a PDF (~2,986 of 27,275): no OCR needed.

    .venv/bin/python -X utf8 -m research.doc_text_all      # on the L40S -> data/doctext/<file stem>__<member>.txt

.doc -> catdoc (8-bit Word files are read as Windows-1251 Cyrillic), .rtf -> unrtf --text, .docx -> word/document.xml paragraphs, .xls -> xls2csv (catdoc
package). Members of ZIPs and bare files alike; nested ZIPs are opened one level down. ASCII temp names.
Resumable: an existing output is skipped. Prints a count per kind at the end.
"""

import collections
import io
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from research.ocr_scans import FILES, pdfs_in

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "doctext"
TOOLS = {"doc": ["catdoc", "-s", "cp1251", "-d", "utf-8"], "dot": ["catdoc", "-s", "cp1251", "-d", "utf-8"], "xls": ["xls2csv", "-s", "cp1251", "-d", "utf-8"]}


def docx_text(data: bytes) -> str:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8", "replace")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.DOTALL)
    return "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras)


def convert(kind: str, data: bytes, tmp: Path) -> str:
    if kind in ("docx", "pptx") or (kind == "doc" and data[:2] == b"PK"):
        return docx_text(data)
    src = tmp / f"x.{kind}"
    src.write_bytes(data)
    if kind == "rtf":
        cmd = ["unrtf", "--text", str(src)]
    elif kind in TOOLS:
        cmd = [*TOOLS[kind], str(src)]
    else:
        return ""
    r = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    text = r.stdout.decode("utf-8", "replace")
    if kind == "rtf":  # drop unrtf's header block
        text = text.split("-----------------", 1)[-1]
    return text


def members(path: Path):
    data = path.read_bytes()
    if zipfile.is_zipfile(path) and path.suffix.lower() == ".zip":
        z = zipfile.ZipFile(path)
        for n in z.namelist():
            if n.endswith("/"):
                continue
            inner = z.read(n)
            if n.lower().endswith(".zip"):
                try:
                    z2 = zipfile.ZipFile(io.BytesIO(inner))
                    for n2 in z2.namelist():
                        if not n2.endswith("/"):
                            yield f"{n}/{n2}", z2.read(n2)
                except zipfile.BadZipFile:
                    continue
            else:
                yield n, inner
    else:
        yield path.name, data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    count = collections.Counter()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for path in sorted(FILES.iterdir()):
            if not path.is_file() or not path.stat().st_size or pdfs_in(path):
                continue
            try:
                for name, data in members(path):
                    kind = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:]
                    target = OUT / f"{path.stem}__{safe}.txt"
                    if target.exists():
                        count["skipped (done)"] += 1
                        continue
                    try:
                        text = convert(kind, data, tmp)
                    except Exception:  # noqa: BLE001 - one broken file must not stop the run
                        text = ""
                    body = re.sub(r"\s", "", text)
                    if body and sum(c in "@;>=:<?" for c in body) / len(body) > 0.12:
                        count[f"garbled {kind} (kept out)"] += 1
                        continue
                    if len(text.strip()) >= 50:
                        target.write_text(text, encoding="utf-8")
                        count[f"ok {kind}"] += 1
                    else:
                        count[f"empty/unsupported {kind}"] += 1
            except zipfile.BadZipFile:
                count["bad zip"] += 1
    for k, n in count.most_common():
        print(f"{n:6d}  {k}")
    print("DOCTEXT DONE", flush=True)


if __name__ == "__main__":
    main()
