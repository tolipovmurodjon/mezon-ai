"""Is every act in the law store complete? Compare each lex.uz page with what the store holds for its current edition.

    .venv/Scripts/python.exe -X utf8 -m research.law_completeness

Per act: characters of act text on the page vs in the store (coverage), images inside the act body (annex tables or
forms published as pictures, which the text parser cannot read), tables, and a PDF-only marker. Reads cached pages
only (research/polite_http is cache-first), so a re-run makes no new requests. Writes data/interim/law_completeness.csv.
"""

import csv
import html
import re
import sqlite3
from pathlib import Path

from mezon.config import LAW_DB
from mezon.lawstore import fetch as lx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "interim" / "law_completeness.csv"
_BODY = re.compile(r'<div[^>]+class="[^"]*\b(?:docBody|ACT_TEXT|lx_text)\b[^"]*"', re.IGNORECASE)
_IMG = re.compile(r"<img\b[^>]*\bsrc=\"([^\"]+)\"", re.IGNORECASE)
_PDF_ONLY = re.compile(r"PDF shaklida berilgan|в формате PDF", re.IGNORECASE)


def _text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _body(page: str) -> str:
    """The act's own text: from the first clause-level element to the page footer, without site chrome."""
    m = _BODY.search(page)
    start = m.start() if m else 0
    first = re.search(r'id="-?\d{5,}"', page[start:])
    start = start + first.start() if first else start
    end = page.find("<footer", start)
    return page[start: end if end > 0 else len(page)]


def main() -> None:
    con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
    out = []
    for key, lex_id, title in con.execute("SELECT act_key, lex_id, title FROM acts ORDER BY act_key"):
        try:
            page = lx.doc_page(lex_id)
        except Exception as e:  # noqa: BLE001 - report the act, keep auditing the rest
            out.append({"act_key": key, "lex_id": lex_id, "page_chars": "", "store_chars": "", "coverage": "",
                        "images": "", "tables": "", "pdf_only": "", "note": f"page not available: {e}"[:120]})
            continue
        body = _body(page)
        imgs = [s for s in _IMG.findall(body) if not re.search(r"(?i)logo|icon|flag|gerb|\.svg", s)]
        page_chars = len(_text(body))
        store_chars = con.execute(
            "SELECT coalesce(sum(length(text)),0) FROM units WHERE act_key=? AND valid_to IS NULL "
            "AND path NOT LIKE '%/%'", (key,)).fetchone()[0]
        # Top-level units already contain their parts, so their text length is the act's stored length.
        out.append({
            "act_key": key, "lex_id": lex_id, "page_chars": page_chars, "store_chars": store_chars,
            "coverage": f"{store_chars / page_chars:.0%}" if page_chars else "",
            "images": len(imgs), "tables": len(re.findall(r"(?i)<table\b", body)),
            "pdf_only": "yes" if _PDF_ONLY.search(page) else "", "note": " ".join(imgs[:3])[:200],
        })
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(f"{r['act_key']:18s} coverage {r['coverage']:>5s} | images {r['images']!s:>3s} | tables "
              f"{r['tables']!s:>3s} {'| PDF only' if r['pdf_only'] else ''} {r['note'][:70]}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
