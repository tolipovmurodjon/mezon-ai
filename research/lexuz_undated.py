"""Find the documents lex.uz lists without an adoption date (date-window discovery cannot see them).

    .venv/Scripts/python.exe -X utf8 -m research.lexuz_undated 4      # lang 4 = Uzbek Latin; writes data/interim/

Measured 20.11.2026: Uzbek Latin with no date filter = 55,444, every dated search = 55,441, so 3 documents have no
date. This pages the undated search (the page's own "Keyingisi" post, ~1.2 s per page) and writes every id it sees
to data/interim/lexuz_all_ids_lang<N>.txt; compare with the catalogue on the box to get the missing ids.
"""

import sys
from pathlib import Path

from research.lexuz_crawl import search_url

ROOT = Path(__file__).resolve().parents[1]


def main(lang: str) -> None:
    stated, hits = search_url(f"https://lex.uz/uz/search/all?lang={lang}", f"discover/nodate_lang{lang}", max_pages=4000)
    out = ROOT / "data" / "interim" / f"lexuz_all_ids_lang{lang}.txt"
    out.write_text("\n".join(h["id"] + "\t" + (h["date"] or "") + "\t" + h["title"][:120] for h in hits) + "\n",
                   encoding="utf-8")
    undated = [h for h in hits if not h["date"]]
    print(f"lang {lang}: stated {stated}, listed {len(hits)}, without a date in the badge {len(undated)} -> {out}")
    for h in undated[:20]:
        print("  ", h["id"], h["title"][:90])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "4")
