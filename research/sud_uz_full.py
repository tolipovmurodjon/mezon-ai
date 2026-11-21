"""Whole sud.uz (Supreme Court site): every public page and every attached file, polite and resumable.

    .venv/bin/python -X utf8 -m research.sud_uz_full          # on the L40S -> data/raw/sud_uz_full/

How: start from robots.txt's sitemap(s) (all pages the site lists itself) + the home page, then follow every link
that stays on sud.uz (breadth first). Pages are saved as HTML (pages/<sha1>.html + index.jsonl with url, title,
status); files from /wp-content/uploads/ (pdf, doc, docx, xls, xlsx, zip, ppt) go to files/. Skipped: /wp-admin/
(robots.txt), login/search/feed/comment URLs, query-string duplicates, other domains (they are listed in
external_links.txt for later). One request per second. Nothing is submitted; no forms, no logins.
"""

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "sud_uz_full"
BASE = "https://sud.uz/"
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)"}
FILE_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx")
SKIP = re.compile(r"/wp-admin|/wp-login|/wp-json|/feed|/comments|[?&](s|replytocom|share|print)=|/xmlrpc|#")
HREF = re.compile(r'(?:href|src)="([^"]+)"', re.IGNORECASE)
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def get(url: str) -> tuple[int, bytes, str]:
    time.sleep(0.5)
    q = urllib.parse.quote(url, safe=":/%?=&#+,;@")
    try:
        with urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=90) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except Exception:  # noqa: BLE001 - network hiccup: record and move on
        return 0, b"", ""


def norm(u: str, base: str) -> str | None:
    u = urllib.parse.urljoin(base, html.unescape(u.strip()))
    p = urllib.parse.urlsplit(u)
    if p.scheme not in ("http", "https"):
        return None
    u = urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, ""))
    return u


def main() -> None:
    (OUT / "pages").mkdir(parents=True, exist_ok=True)
    (OUT / "files").mkdir(parents=True, exist_ok=True)
    idx_path = OUT / "index.jsonl"
    seen, resume_pages = set(), []
    if idx_path.exists():
        for line in idx_path.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("kind") == "sitemap" or r["url"] == BASE:
                continue  # sitemaps and the home page are refetched: they hold the link lists
            seen.add(r["url"])
            if r.get("kind") == "page":
                resume_pages.append(r["url"])
    external = set()
    queue = deque([BASE])
    for u in resume_pages:  # resume: re-read links from pages saved by an earlier run
        f = OUT / "pages" / (hashlib.sha1(u.encode()).hexdigest() + ".html")
        if f.exists():
            for raw in HREF.findall(f.read_text(encoding="utf-8")):
                v = norm(raw, u)
                if v and not SKIP.search(v) and urllib.parse.urlsplit(v).netloc in ("sud.uz", "www.sud.uz") and v not in seen:
                    queue.append(v)
    _, robots, _ = get(BASE + "robots.txt")
    for sm in re.findall(r"(?im)^sitemap:\s*(\S+)", robots.decode("utf-8", "replace")):
        queue.append(sm)
    queued = set(queue) | seen
    pages = files = 0
    with idx_path.open("a", encoding="utf-8") as idx:
        while queue:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            path = urllib.parse.urlsplit(url).path.lower()
            is_file = path.endswith(FILE_EXT)
            if is_file:
                name = urllib.parse.unquote(path).rsplit("/", 1)[-1]
                target = OUT / "files" / (hashlib.sha1(url.encode()).hexdigest()[:12] + "_" + name[-90:])  # <255 bytes
                if not target.exists():
                    status, body, ctype = get(url)
                    if status == 200 and body:
                        target.write_bytes(body)
                        files += 1
                    idx.write(json.dumps({"url": url, "kind": "file", "status": status, "bytes": len(body)}) + "\n")
                continue
            status, body, ctype = get(url)
            text = body.decode("utf-8", "replace") if body else ""
            kind = "sitemap" if ("xml" in ctype or url.endswith(".xml")) else "page"
            if kind == "page" and text:
                (OUT / "pages" / (hashlib.sha1(url.encode()).hexdigest() + ".html")).write_text(text, encoding="utf-8")
                pages += 1
            title = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
            idx.write(json.dumps({"url": url, "kind": kind, "status": status,
                                  "title": html.unescape(title.group(1).strip())[:200] if title else ""},
                                 ensure_ascii=False) + "\n")
            idx.flush()
            links = LOC.findall(text) if kind == "sitemap" else [m for m in HREF.findall(text)]
            for raw in links:
                u = norm(raw, url)
                if not u or SKIP.search(u):
                    continue
                host = urllib.parse.urlsplit(u).netloc
                if host not in ("sud.uz", "www.sud.uz"):
                    if host.endswith("sud.uz") or "lex.uz" in host:
                        external.add(u.split("?")[0])
                    continue
                if u not in queued:
                    queued.add(u)
                    queue.append(u)
            if pages and pages % 200 == 0:
                print(f"pages {pages} | files {files} | queue {len(queue)}", flush=True)
                (OUT / "external_links.txt").write_text("\n".join(sorted(external)), encoding="utf-8")
    (OUT / "external_links.txt").write_text("\n".join(sorted(external)), encoding="utf-8")
    print(f"SUD_UZ_FULL DONE: pages {pages}, files {files}, other court/lex links {len(external)}", flush=True)


if __name__ == "__main__":
    main()
