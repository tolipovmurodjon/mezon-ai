"""Stage 01d: OCR markdown (PaddleOCR-VL pages under data/ocr/<key>/page-NNN.md) -> clean text.

Pages marked `OCR failed` count against the document; HTML tables become pipe rows; image placeholders and markdown
emphasis go; page furniture is removed with the PDF logic."""

import html
import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path

from research.refinery import config
from research.refinery.extract_pdf import cut_clauses, drop_page_furniture, rejoin_lines


@dataclass
class OcrText:
    key: str
    text: str = ""
    pages: int = 0
    failed_pages: int = 0
    units: list[dict] = field(default_factory=list)
    ocr_partial: bool = False


_COMMENT = re.compile(r"<!--\s*page\s*\d+\s*-->", re.IGNORECASE)
_FAILED = re.compile(r"<!--\s*OCR failed", re.IGNORECASE)
_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.IGNORECASE)


def _html_table(m: re.Match) -> str:
    rows = []
    for tr in re.findall(r"<tr\b.*?</tr>", m.group(0), re.DOTALL | re.IGNORECASE):
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
            for c in re.findall(r"<t[dh]\b.*?</t[dh]>", tr, re.DOTALL | re.IGNORECASE)
        ]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n" + "\n".join(rows) + "\n"


_LATEX = re.compile(r"\\(?:mathrm|mathbf|mathit|underline|text|textbf|boldsymbol)\s*\{([^{}]*)\}")
# PaddleOCR-VL reads Uzbek Cyrillic with Russian habits: the special letters come out as plain ones (карори for
# қарори) or as look-alikes (ӯ ү for ў, ы for и). Each pair maps a wrong letter to the letters it may stand for.
_OCR_FIX = {
    "к": "қ",
    "г": "ғ",
    "х": "ҳ",
    "у": "ў",
    "ӯ": "ў",
    "ү": "ў",
    "ӱ": "ў",
    "ұ": "ў",
    "ъ": "ў",
    "ф": "ғ",
    "ы": "и",
    "ӣ": "и",
    "ҝ": "қ",
    "ҡ": "қ",
}
_WORD = re.compile(r"[^\W\d_]{3,}")


_LATEX_ARG = re.compile(r"\\[A-Za-z]+\s*\{([^{}]*)\}")
_LATEX_BARE = re.compile(r"\\[A-Za-z]+")


def strip_markup(text: str) -> str:
    """HTML entities (&quot;, even double-escaped) and the LaTeX the OCR model leaks into the markdown: a command with
    an argument keeps the argument (\\mathrm{K} -> K, \\frac{a}{b} -> a b), a bare command (\\circ, \\quad, \\lim) goes."""
    for _ in range(3):
        new = html.unescape(text)
        if new == text:
            break
        text = new
    for _ in range(4):
        new = _LATEX_ARG.sub(r" \1 ", _LATEX.sub(r"\1", text))
        if new == text:
            break
        text = new
    text = _LATEX_BARE.sub(" ", text)
    return text.replace("$", "").replace("{", " ").replace("}", " ")


def ocr_correct(text: str, vocab: set[str], max_slots: int = 6) -> tuple[str, int]:
    """Replace an out-of-vocabulary Cyrillic word by the variant (wrong letter -> special letter) that the vocabulary
    knows. Only words with at most `max_slots` ambiguous letters are tried; the first match in a fixed order wins, so
    the result is deterministic. Returns (text, number of words corrected)."""
    fixed = 0
    cache: dict[str, str] = {}

    def fix(m: re.Match) -> str:
        nonlocal fixed
        w = m.group(0)
        low = w.lower()
        if low in vocab or not re.search("[Ѐ-ӿ]", w):
            return w
        if low in cache:
            new = cache[low]
        else:
            slots = [i for i, ch in enumerate(low) if ch in _OCR_FIX]
            new = ""
            if 0 < len(slots) <= max_slots:
                for mask in itertools.product((0, 1), repeat=len(slots)):
                    if not any(mask):
                        continue
                    cand = list(low)
                    for use, i in zip(mask, slots, strict=True):
                        if use:
                            cand[i] = _OCR_FIX[low[i]]
                    c = "".join(cand)
                    if c in vocab:
                        new = c
                        break
            cache[low] = new
        if not new:
            return w
        fixed += 1
        return "".join(n.upper() if o.isupper() else n for o, n in zip(w, new, strict=True))

    return _WORD.sub(fix, text), fixed


def clean_md(md: str) -> str:
    t = _COMMENT.sub("", md)
    t = re.sub(r"<table\b.*?</table>", _html_table, t, flags=re.DOTALL | re.IGNORECASE)
    t = _IMG.sub("", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = strip_markup(t)
    t = re.sub(r"(\*\*|__|\*|`)", "", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    return t


def extract_ocr(key: str, root: Path = config.OCR_DIR, vocab: set[str] | None = None) -> OcrText | None:
    """Joined markdown `<key>.md` (finished documents only; None while OCR is still running on it)."""
    f = root / f"{key}.md"
    if not f.exists():
        return None
    md = f.read_text(encoding="utf-8", errors="replace")
    pages_md = [p for p in re.split(r"<!--\s*page\s*\d+\s*-->", md)[1:]] or [md]
    res = OcrText(key=key, pages=len(pages_md))
    good = []
    for page in pages_md:
        if _FAILED.search(page):
            res.failed_pages += 1
            continue
        good.append(clean_md(page))
    res.ocr_partial = res.pages == 0 or (res.pages - res.failed_pages) / res.pages < config.OCR_GOOD_PAGES
    text, _ = rejoin_lines("\n\n".join(drop_page_furniture(good)), vocab)
    res.text = text
    res.units = cut_clauses(text)
    return res


def ocr_quality(text: str, vocab: set[str]) -> dict:
    """Out-of-vocabulary rate against a vocabulary built from clean HTML acts, and the non-alphanumeric share."""
    words = [w.lower() for w in re.findall(r"[^\W\d_]{3,}", text)]
    oov = sum(1 for w in words if w not in vocab) / len(words) if words else 1.0
    nonalnum = sum(1 for c in text if not (c.isalnum() or c.isspace())) / max(len(text), 1)
    return {"oov_rate": round(oov, 4), "nonalnum_share": round(nonalnum, 4), "n_words": len(words)}
