"""Supreme Court site (sud.uz): plenum resolutions and court-practice reviews, polite.

    .venv/bin/python -X utf8 -m research.sud_uz      # on the L40S -> data/raw/sud_uz/

Reads 8 public list pages (4 plenum categories, 4 practice-review categories), keeps each page's HTML, a JSON list
of its links (lex.uz or a file on sud.uz) and downloads every file hosted on sud.uz (PDF/DOC/DOCX/ZIP under
/wp-content/uploads/). Links to lex.uz are only listed: those texts are already in our lex.uz crawl.
robots.txt (checked 21.11.2026) only disallows /wp-admin/. One request every 2 s, no forms. Resumable.
"""

import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "sud_uz"
PAGES = {
    "plenum_criminal": "https://sud.uz/plenum/documents-criminal/",
    "plenum_civil": "https://sud.uz/plenum/documents-civil/",
    "plenum_administrative": "https://sud.uz/plenum/documents-administrative/",
    "plenum_economic": "https://sud.uz/plenum/documents-economical/",
    "review_criminal": "https://sud.uz/court-experiments/crime-court-experiments/",
    "review_civil": "https://sud.uz/court-experiments/civil-court-experiments/",
    "review_administrative": "https://sud.uz/court-experiments/administrative-court-experiments/",
    "review_economic": "https://sud.uz/court-experiments/economical-court-experiments/",
}
LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)"}


def get(url: str) -> bytes:
    time.sleep(2.0)
    url = urllib.parse.quote(url, safe=":/%?=&#")  # file names carry Cyrillic and ‘ characters
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, url in PAGES.items():
        page = get(url).decode("utf-8", "replace")
        (OUT / f"{name}.html").write_text(page, encoding="utf-8")
        rows = []
        for href, text in LINK.findall(page):
            href = html.unescape(href)
            if "lex.uz/docs" in href or "/wp-content/uploads/" in href:
                label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text))).strip()
                rows.append({"href": href, "label": label})
        (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        files = OUT / "files" / name
        files.mkdir(parents=True, exist_ok=True)
        for r in rows:
            if "/wp-content/uploads/" not in r["href"]:
                continue
            target = files / urllib.parse.unquote(r["href"].rsplit("/", 1)[-1])
            if target.exists() and target.stat().st_size > 0:
                continue
            try:
                target.write_bytes(get(urllib.parse.urljoin(url, r["href"])))
                total += 1
            except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
                print(f"{name}: {r['href']}: {e}", flush=True)
        print(f"{name}: {len(rows)} links ({sum('lex.uz' in r['href'] for r in rows)} to lex.uz)", flush=True)
    print(f"SUD_UZ DONE: {total} files downloaded this run", flush=True)


if __name__ == "__main__":
    main()
