"""Polite whole-site crawler for public government sites (gov.uz, my.gov.uz, ombudsman.uz, stat.sud.uz, ...).

    .venv/bin/python -X utf8 -m research.site_crawl govuz        # one site per process -> data/raw/sites/<name>/

Same idea as research/sud_uz_full.py, generalised: robots.txt is obeyed (urllib.robotparser) and its sitemaps seed
the queue; every link that stays on the site's hosts is followed; pages are saved as HTML (pages/<sha1>.html +
index.jsonl), attached files (pdf/doc/xls/zip/ppt) go to files/. Two queues: important pages first, news/press
pages after (they are the bulk and the least useful). One request per `rate` seconds per site, backs off on 429/5xx.
Nothing is submitted: no forms, no logins, no payment pages, no search. Resumable (index.jsonl = done list).
"""

import hashlib
import html
import json
import re
import signal
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Mezon research; polite)"
FILE_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx", ".odt", ".rtf")
SKIP = re.compile(
    r"/(wp-admin|wp-login|wp-json|login|logout|register|signin|auth|oneid|payment|cart|search|feed|print)\b|"
    r"[?&](s|q|search|replytocom|share|print|sort|page_size|lang)=|\.(jpg|jpeg|png|gif|svg|webp|ico|css|js|mp4|mp3|woff2?)(\?|$)",
    re.IGNORECASE,
)
LOW = re.compile(r"/(news|press|yangiliklar|novosti|events|photo|video|gallery|media|interview|article)s?\b", re.IGNORECASE)
HREF = re.compile(r'(?:href|src)="([^"]+)"', re.IGNORECASE)
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")

SITES = {
    "govuz": {"hosts": ["gov.uz"], "start": ["https://gov.uz/oz", "https://gov.uz/uz"], "prefix": ["/oz", "/uz"]},
    "mygovuz": {"hosts": ["my.gov.uz"], "start": ["https://my.gov.uz/uz", "https://my.gov.uz/oz"], "prefix": ["/uz", "/oz"]},
    "ombudsman": {"hosts": ["ombudsman.uz", "www.ombudsman.uz"], "start": ["https://ombudsman.uz/uz"], "prefix": ["/uz", "/oz", "/ru"]},
    "bizombudsman": {"hosts": ["biznesombudsman.uz"], "start": ["https://biznesombudsman.uz/"], "prefix": [""]},
    "senat": {"hosts": ["senat.uz", "www.senat.uz"], "start": ["https://senat.uz/", "https://senat.uz/sitemap.xml"],
              "prefix": [""]},
    "statsud": {"hosts": ["stat.sud.uz"], "start": ["https://stat.sud.uz/"], "prefix": [""]},
    "eqaror_resp": {"hosts": ["e-qaror-respublika.gov.uz"], "start": ["https://e-qaror-respublika.gov.uz/"], "prefix": [""]},
}


def fetch(url: str, rate: float) -> tuple[int, bytes, str]:
    time.sleep(rate)
    q = urllib.parse.quote(url, safe=":/%?=&#+,;@")
    for attempt in range(4):
        _alarm(150)  # hard deadline for the whole request: a slow-drip server can outlive the socket timeout
        try:
            with urllib.request.urlopen(urllib.request.Request(q, headers={"User-Agent": UA}), timeout=90) as r:
                if r.headers.get("Content-Length") and int(r.headers["Content-Length"]) > 300_000_000:
                    return -1, b"", ""
                return r.status, r.read(), r.headers.get("Content-Type", "")
        except Deadline:
            return -2, b"", ""
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            return e.code, b"", ""
        except Exception:  # noqa: BLE001 - network hiccup: retry, then record and move on
            time.sleep(10)
        finally:
            _alarm(0)
    return 0, b"", ""


class Deadline(Exception):
    pass


def _on_alarm(signum, frame):
    raise Deadline


def _alarm(seconds: int) -> None:
    if hasattr(signal, "SIGALRM"):  # Linux (the box); Windows has no SIGALRM
        signal.alarm(seconds)


if hasattr(signal, "SIGALRM"):
    signal.signal(signal.SIGALRM, _on_alarm)


def main() -> None:
    name = sys.argv[1]
    cfg = SITES[name]
    rate = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    out = ROOT / "data" / "raw" / "sites" / name
    (out / "pages").mkdir(parents=True, exist_ok=True)
    (out / "files").mkdir(parents=True, exist_ok=True)
    idx_path = out / "index.jsonl"
    seen, resume = set(), []
    if idx_path.exists():
        for line in idx_path.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("kind") == "sitemap" or r["url"] in cfg["start"]:
                continue  # refetched: they hold the link lists
            seen.add(r["url"])
            if r.get("kind") == "page":
                resume.append((r["url"], r.get("sha")))
    base = f"https://{cfg['hosts'][0]}/"
    robots = urllib.robotparser.RobotFileParser(base + "robots.txt")
    try:
        robots.read()
    except Exception:  # noqa: BLE001 - no robots.txt: everything public is allowed
        robots = None
    high, low = deque(cfg["start"]), deque()
    for sm in (robots.site_maps() or []) if robots else []:
        high.append(sm)
    for u, sha in resume:  # resume: re-read links from pages saved by an earlier run
        f = out / "pages" / f"{sha}.html"
        if sha and f.exists():
            for raw in HREF.findall(f.read_text(encoding="utf-8")):
                v = urllib.parse.urljoin(u, html.unescape(raw.strip()))
                pv = urllib.parse.urlsplit(v)
                v = urllib.parse.urlunsplit((pv.scheme, pv.netloc.lower(), pv.path, pv.query, ""))
                if pv.netloc.lower() in cfg["hosts"] and v not in seen:
                    (low if LOW.search(pv.path) else high).append(v)
    queued = set(high) | set(low) | seen
    external: set[str] = set()
    pages = files = 0

    def allowed(u: str) -> bool:
        p = urllib.parse.urlsplit(u)
        if p.netloc not in cfg["hosts"] or SKIP.search(u):
            return False
        if not (p.path.endswith(".xml") or p.path.lower().endswith(FILE_EXT)) and not any(
            p.path.startswith(x) for x in cfg["prefix"]
        ):
            return False
        return robots is None or robots.can_fetch(UA, u)

    with idx_path.open("a", encoding="utf-8") as idx:
        while high or low:
            url = high.popleft() if high else low.popleft()
            if url in seen:
                continue
            seen.add(url)
            if url not in cfg["start"] and not allowed(url):
                continue  # resume re-seeds raw links: filter them here (prefix, skip list, robots)
            path = urllib.parse.urlsplit(url).path
            if path.lower().endswith(FILE_EXT):
                target = out / "files" / (hashlib.sha1(url.encode()).hexdigest()[:12] + "_" + Path(urllib.parse.unquote(path)).name[-90:])
                status, body, _ = fetch(url, rate)
                if status == 200 and body:
                    target.write_bytes(body)
                    files += 1
                idx.write(json.dumps({"url": url, "kind": "file", "status": status, "bytes": len(body), "path": target.name}, ensure_ascii=False) + "\n")
                idx.flush()
                continue
            status, body, ctype = fetch(url, rate)
            text = body.decode("utf-8", "replace") if body else ""
            kind = "sitemap" if ("xml" in ctype or path.endswith(".xml")) else "page"
            sha = hashlib.sha1(url.encode()).hexdigest()
            if kind == "page" and text:
                (out / "pages" / f"{sha}.html").write_text(text, encoding="utf-8")
                pages += 1
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.DOTALL)
            idx.write(json.dumps({"url": url, "kind": kind, "status": status, "sha": sha,
                                  "title": html.unescape(title.group(1).strip())[:200] if title else ""}, ensure_ascii=False) + "\n")
            idx.flush()
            for raw in LOC.findall(text) if kind == "sitemap" else HREF.findall(text):
                u = urllib.parse.urljoin(url, html.unescape(raw.strip()))
                p = urllib.parse.urlsplit(u)
                if p.scheme not in ("http", "https"):
                    continue
                u = urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, ""))
                if p.netloc.lower() not in cfg["hosts"]:
                    if p.netloc.endswith(".uz"):
                        external.add(f"{p.scheme}://{p.netloc.lower()}/")
                    continue
                if u in queued or not allowed(u):
                    continue
                queued.add(u)
                (low if LOW.search(p.path) else high).append(u)
            if pages % 200 == 0 and kind == "page":
                print(f"{name}: pages {pages} | files {files} | queue {len(high)} + news {len(low)}", flush=True)
                (out / "external_sites.txt").write_text("\n".join(sorted(external)), encoding="utf-8")
    (out / "external_sites.txt").write_text("\n".join(sorted(external)), encoding="utf-8")
    print(f"SITE DONE {name}: pages {pages}, files {files}, other .uz sites {len(external)}", flush=True)


if __name__ == "__main__":
    main()
