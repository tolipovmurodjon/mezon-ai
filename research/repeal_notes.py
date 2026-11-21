"""lex.uz's own note on each repealed article ("25-modda ... O'RQ-976-sonli Qonuniga asosan o'z kuchini yo'qotgan").

    .venv/Scripts/python.exe -X utf8 -m research.repeal_notes

Reads the latest cached edition of every act in the law store (cache-first: the build already fetched them) and writes
data/knowledge/repeal_notes.json: {act_key: {article number: {"note", "url"}}}. The article-level basis check shows
the note as evidence, so an expert sees lex.uz's own words that the cited article is gone.
"""

import html
import json
import re
import sqlite3
from pathlib import Path

from mezon.config import LAW_DB
from mezon.lawstore import fetch as lx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "knowledge" / "repeal_notes.json"
NOTE = re.compile(r"(?<![\d-])(\d+(?:-\d+)?)-modda\s+(.{0,200}?(?:o[ʻ‘’']?z kuchini yo[ʻ‘’']?qotgan|chiqarib tashlangan"
                  r"|chiqarilgan)[^.]{0,80})")


def main() -> None:
    con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
    out: dict[str, dict] = {}
    for key, lex_id in con.execute("SELECT act_key, lex_id FROM acts"):
        row = con.execute("SELECT ondate FROM editions WHERE act_key=? ORDER BY valid_from DESC LIMIT 1",
                          (key,)).fetchone()
        try:
            page = lx.edition_page(lex_id, row[0]) if row else lx.doc_page(lex_id)
        except Exception:  # noqa: BLE001, S112 - an act we cannot read just has no notes
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
        notes = {}
        for m in NOTE.finditer(text):
            notes.setdefault(m[1], {"note": f"{m[1]}-modda {m[2].strip()}",
                                    "url": f"{lx.BASE}/uz/docs/{lex_id}"})
        if notes:
            out[key] = notes
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(len(v) for v in out.values())} repealed-article notes in {len(out)} acts -> {OUT}")
    for key in ("lsp", "budgetcode"):
        for num in ("25", "144", "146"):
            if num in out.get(key, {}):
                print(f"  {key} {num}: {out[key][num]['note'][:120]}")


if __name__ == "__main__":
    main()
