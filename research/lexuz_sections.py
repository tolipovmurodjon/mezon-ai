"""Every public reference section of lex.uz beyond the documents, in all four language versions (box only).

    python -X utf8 -m research.lexuz_sections          # resumable (cache-first); prints pages and files per section

Sections (from the site menu, 20.11.2026): legal explanations, the constitutional-law encyclopedic dictionary, the
classifier of legislation branches, the Collection of Legislation, the Collection of international treaties, the
library, report forms, accounting standards (BHMS), guides, state symbols, the legal-analysis card, news, about.
Breadth-first inside each section's own path (and its paging links), plus every file it links (pdf/zip/doc/xls).
Document pages (/docs/) found here are queued for the document crawl instead of fetched twice. Same spacing and
back-off as research/polite_http.py; never logs in (/login is skipped), never leaves lex.uz.
"""

import hashlib
import re
import sqlite3
from collections import deque
from urllib.parse import urljoin, urlparse

from research.lexuz_full import DIR, add, connect
from research.polite_http import fetch

BASE = "https://lex.uz"
SECTIONS = ["explanation", "dictionary", "klassifkator", "law_collection", "pact_collection", "library", "forms",
            "nsbu", "qollanma", "symbols", "card", "news", "lexuz", "user_guide", "axborot", "about", "publication",
            "catalog"]
LANGS = ["uz", "oz", "ru", "en"]
MAX_PAGES_PER_SECTION = 20000
HREF = re.compile(r'href="([^"#]+)"')
FILE = re.compile(r"\.(pdf|zip|rar|docx?|xlsx?|rtf|pptx?)(\?|$)", re.IGNORECASE)
DOC = re.compile(r"/(?:uz|ru|oz|en)/docs/(-?\d+)")


def _key(url: str) -> str:
    u = urlparse(url)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (u.path + ("_" + u.query if u.query else "")).strip("/"))[:150]
    return f"sections/{slug}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def walk(con: sqlite3.Connection, lang: str, section: str) -> tuple[int, int]:
    root = f"/{lang}/{section}"
    q, seen, pages, files, docs = deque([BASE + root]), set(), 0, 0, set()
    while q and pages < MAX_PAGES_PER_SECTION:
        url = q.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            body = fetch(url, "lexuz", key=_key(url))
        except RuntimeError as e:
            print("skip", url, e, flush=True)
            continue
        if FILE.search(urlparse(url).path):
            files += 1
            continue
        pages += 1
        page = body.decode("utf-8", "replace")
        for href in HREF.findall(page):
            full = urljoin(url, href.replace("&amp;", "&"))
            u = urlparse(full)
            if u.netloc not in ("lex.uz", "www.lex.uz") or "/login" in u.path:
                continue
            if m := DOC.search(u.path):
                docs.add(m.group(1))
            elif u.path.startswith(root) or (FILE.search(u.path) and "/files/" in u.path):
                q.append(full.replace("www.lex.uz", "lex.uz"))
    add(con, sorted(docs), 3, twins=False)
    con.commit()
    return pages, files


def main() -> None:
    con = connect()
    con.execute("CREATE TABLE IF NOT EXISTS sections(name TEXT PRIMARY KEY, pages INTEGER, files INTEGER)")
    for section in SECTIONS:
        for lang in LANGS:
            name = f"{lang}/{section}"
            if con.execute("SELECT 1 FROM sections WHERE name=?", (name,)).fetchone():
                continue
            pages, files = walk(con, lang, section)
            con.execute("INSERT OR REPLACE INTO sections VALUES(?,?,?)", (name, pages, files))
            con.commit()
            print(f"{name}: {pages} pages, {files} files", flush=True)
    print("sections done; state", DIR)


if __name__ == "__main__":
    main()
