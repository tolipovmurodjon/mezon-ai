"""Stage 01c: local decisions that lex.uz serves only as PDF inside files/<fileid>.zip (design section 3, 1c).

pdftotext cannot open Cyrillic file names, so the PDF bytes are written to an ASCII temp name first."""

import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from research.refinery import config
from research.textnorm import fold

_FURNITURE = re.compile(
    r"e-qaror\.gov\.uz|lex\.uz|https?://|www\.|^\s*\d{1,3}\s*$|^\s*-\s*\d{1,3}\s*-\s*$", re.IGNORECASE
)
_OPERATIVE = re.compile(
    r"q\s*a\s*r\s*o\s*r\s*q\s*i\s*l\s*(?:a\s*m\s*a\s*n|a\s*d\s*i)|"
    r"қ\s*а\s*р\s*о\s*р\s*қ\s*и\s*л\s*(?:а\s*м\s*а\s*н|а\s*д\s*и)|"
    r"п\s*о\s*с\s*т\s*а\s*н\s*о\s*в\s*л\s*я\s*ю",
    re.IGNORECASE,
)
_ANNEX = re.compile(r"(?:^|\s)(\d{1,2})\s*-\s*(?:ilova|илова|приложение)\b", re.IGNORECASE)
_CLAUSE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+\S")
_SIGNATURE = re.compile(
    r"\b(?:tuman|shahar|viloyat)\s+hokimi\b|\bkengashi?\s+raisi\b|^\s*hokim\b|"
    r"ҳокими|раиси|^\s*ҳоким\b",
    re.IGNORECASE,
)
_START_NEW = re.compile(
    r"^\s*(?:\d{1,3}\s*[.)]|[-–—•]\s|[a-zа-я]\)|\d{1,3}\s*-\s*(?:ilova|илова)|qaror\b)", re.IGNORECASE
)


@dataclass
class PdfText:
    key: str
    name: str
    text: str = ""
    pages: int = 0
    scanned: bool = False
    units: list[dict] = field(default_factory=list)
    n_table_lines: int = 0
    error: str = ""


def read_zip_pdfs(path: Path) -> list[tuple[str, bytes]]:
    """(name, bytes) for every PDF in a zip, or the file itself when it is a bare PDF."""
    data = Path(path).read_bytes()
    if not data:
        return []
    if data[:4] == b"%PDF":
        return [(Path(path).name, data)]
    try:
        with zipfile.ZipFile(Path(path)) as z:
            return [(i.filename, z.read(i)) for i in z.infolist() if i.filename.lower().endswith(".pdf")]
    except (zipfile.BadZipFile, OSError):
        return []


def pdftotext_ascii_tmp(data: bytes, timeout: int = 90) -> str:
    """Run pdftotext -enc UTF-8 -layout on the bytes through an ASCII temp name (x.pdf in a fresh directory)."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "x.pdf"
        src.write_bytes(data)
        r = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-layout", str(src), "-"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    return r.stdout.decode("utf-8", "replace")


def drop_page_furniture(pages: list[str]) -> list[str]:
    """Headers and footers: site lines, bare page numbers, and any line (digits removed) on > 30% of >= 3 pages."""

    def key(line: str) -> str:
        return re.sub(r"\d+", "", line).strip().lower()

    counts: dict[str, int] = {}
    if len(pages) >= 3:
        for p in pages:
            for k in {key(line) for line in p.splitlines() if line.strip()}:
                counts[k] = counts.get(k, 0) + 1
    out = []
    for p in pages:
        keep = []
        for line in p.splitlines():
            if _FURNITURE.search(line):
                continue
            if (
                counts
                and len(line.strip()) < 120
                and counts.get(key(line), 0) / len(pages) > 0.30
                and key(line)
            ):
                continue
            keep.append(line)
        out.append("\n".join(keep))
    return out


def _squash(line: str) -> tuple[str, bool]:
    """Column gaps of 3+ spaces: a row of a table when there are two or more, else a plain space."""
    line = line.rstrip()
    gaps = re.findall(r"\S\s{3,}\S", line)
    if len(gaps) >= 2:
        return " | ".join(c.strip() for c in re.split(r"\s{3,}", line.strip()) if c.strip()), True
    return re.sub(r"\s+", " ", line).strip(), False


def rejoin_lines(text: str, vocab: set[str] | None = None) -> tuple[str, int]:
    """Join hard-wrapped lines (a line without .;:!? followed by a lowercase start); undo a trailing hyphen only
    when the joined word is in the corpus vocabulary. Returns (text, number of table-like lines)."""
    paragraphs: list[str] = []
    buf = ""
    tables = 0

    def flush() -> None:
        nonlocal buf
        if buf:
            paragraphs.append(buf)
        buf = ""

    for raw in text.splitlines():
        line, is_row = _squash(raw)
        if not line:
            flush()
            continue
        if is_row:
            tables += 1
            flush()
            paragraphs.append(line)
            continue
        if not buf:
            buf = line
            continue
        wrapped = (
            not re.search(r"[.;:!?»”)]$", buf)
            and re.match(r"[a-zа-яёўқғҳʻʼ(]", line)
            and not _START_NEW.match(line)
        )
        if buf.endswith("-") and re.match(r"[a-zа-яёўқғҳʻʼ]", line) and re.search(r"\w-$", buf):
            head = buf[:-1].rsplit(" ", 1)
            nxt = line.split(" ", 1)
            joined = (head[-1] + nxt[0]).lower()
            if vocab is not None and joined in vocab:
                buf = (head[0] + " " if len(head) > 1 else "") + head[-1] + line
            else:
                buf = buf + line
        elif wrapped:
            buf = f"{buf} {line}"
        else:
            flush()
            buf = line
    flush()
    return "\n".join(paragraphs), tables


def cut_clauses(text: str) -> list[dict]:
    """Unit paths with the grammar of parse.py: pre:K before the operative part, cl:N, annex:A/cl:N. Offsets come
    from the same regexes `textnorm.split_decision` uses, applied to the unfolded paragraph text."""
    units: list[dict] = []
    in_operative = False
    annex = pre = 0
    cur: dict | None = None
    sig_zone = False
    for line in text.splitlines():
        if _SIGNATURE.search(line) and (in_operative or annex == 0) and len(line) < 80:
            sig_zone = True
        if _ANNEX.search(line) and len(line) < 100:
            annex += 1
            cur = None
            sig_zone = False
            continue
        if _OPERATIVE.search(line) and len(line) < 80:
            in_operative = True
            cur = None
            continue
        cm = _CLAUSE.match(line)
        if cm and (in_operative or annex):
            prefix = f"annex:{annex}/" if annex else ""
            cur = {"path": f"{prefix}cl:{cm.group(1)}", "text": line.strip()}
            units.append(cur)
            sig_zone = False
            continue
        if sig_zone:
            units.append({"path": None, "kind": "signature", "text": line.strip()})
            continue
        if cur is not None:
            cur["text"] += " " + line.strip()
        elif not in_operative and not annex:
            pre += 1
            units.append({"path": f"pre:{pre}", "text": line.strip()})
    return units


def extract_pdf(path: Path, key: str, vocab: set[str] | None = None) -> list[PdfText]:
    """One PdfText per PDF in the file. Scanned PDFs (< 200 characters on pages 1-3) carry no text: they go to OCR."""
    out = []
    pdfs = read_zip_pdfs(path)
    for i, (name, data) in enumerate(pdfs):
        pt = PdfText(key=key if len(pdfs) == 1 else f"{key}__{i}", name=name)
        try:
            raw = pdftotext_ascii_tmp(data)
        except (subprocess.TimeoutExpired, OSError) as e:
            pt.error = type(e).__name__
            out.append(pt)
            continue
        pages = raw.split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        pt.pages = len(pages)
        head = "".join(pages[:3])
        if len(re.sub(r"\s+", "", head)) < config.SCAN_CHARS:
            pt.scanned = True
            out.append(pt)
            continue
        text, tables = rejoin_lines("\n\n".join(drop_page_furniture(pages)), vocab)
        pt.text, pt.n_table_lines = text, tables
        pt.units = cut_clauses(text)
        out.append(pt)
    return out


def doc_text(fid: str, root: Path | None = None) -> PdfText | None:
    """Text of the Word/RTF members of `files/<fid>.zip`, extracted earlier by research.doc_text_all into
    data/doctext/<fid>__<member>.txt (catdoc, unrtf, docx XML). Members are joined in file-name order; the result
    goes through the same clean-up as a text PDF (hard-wrapped lines, tables, clause units)."""
    root = root or config.DOCTEXT_DIR
    files = sorted(Path(root).glob(f"{fid}__*.txt")) if Path(root).exists() else []
    parts = [f.read_text(encoding="utf-8", errors="replace") for f in files]
    parts = [p for p in parts if len(re.sub(r"\s+", "", p)) >= 50]
    if not parts:
        return None
    pt = PdfText(key=fid, name=files[0].name, pages=len(parts))
    pt.text, pt.n_table_lines = rejoin_lines("\n\n".join(drop_page_furniture(parts)))
    pt.units = cut_clauses(pt.text)
    return pt


def folded_head(text: str, n: int = 1500) -> str:
    return fold(text[:n])
