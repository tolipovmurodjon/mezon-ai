"""prokuratura.uz (General Prosecutor's Office): public content through the page's own read-only list endpoints.

    .venv/bin/python -X utf8 -m research.prokuratura_get        # on the L40S -> data/raw/sites/prokuratura/

The site is a Vue app; its pages call GET endpoints under https://www.prokuratura.uz/api/ (seen in the browser's
network log and in the app bundle). Only read endpoints are used: documents links, open-card documents, open data,
leadership, regional prosecutors, news list pages and each news item's detail. Never the write ones
(save-murojaat, confirm-murojaat, post-survey, error-notes, visit/create, blogs create). One request every 1.5 s,
resumable (existing files are skipped). Attached files listed by the documents endpoints are fetched from /api/download/.
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "sites" / "prokuratura"
API = "https://www.prokuratura.uz/api/"
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)", "Accept": "application/json"}
STATIC = ["categories/all", "documents-links-for-web-page", "category-for-open-card-documents",
          "category-for-open-card-all-for-web", "open-data-for-web/", "open-data-score", "rahbariyats-for-web",
          "reg-prosecutor-for-web", "all-regions", "murojaat-stats-for-web-page", "ijro-intizomi-for-web-page/1"]


def get(path: str) -> bytes | None:
    time.sleep(0.5)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + path, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(30 * (attempt + 1))
                continue
            return None
        except Exception:  # noqa: BLE001 - network hiccup: retry
            time.sleep(10)
    return None


def save(rel: str, path: str) -> bytes | None:
    f = OUT / rel
    if f.exists() and f.stat().st_size:
        return f.read_bytes()
    body = get(path)
    if body:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    return body


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = set()
    for p in STATIC:
        body = save("static/" + re.sub(r"[^A-Za-z0-9_-]", "_", p.strip("/")) + ".json", p)
        if body:
            files |= set(re.findall(r"\b(\d{6,12}\.(?:pdf|docx?|xlsx?|zip|pptx?))\b", body.decode("utf-8", "replace")))
    print(f"static endpoints done; attached files listed: {len(files)}", flush=True)
    for name in sorted(files):
        save("files/" + name, "download/" + name)
    # news: per category, the app's own paging (news/page/category/<id>?page=N); last-news ignores page=
    cats = json.loads((OUT / "static" / "categories_all.json").read_text(encoding="utf-8"))
    ids = []
    for c in cats:
        k, pages = 0, 1
        while k < pages:
            body = save(f"news/cat{c['id']}_p{k:04d}.json", f"news/page/category/{c['id']}?page={k}")
            if not body:
                break
            d = json.loads(body)
            pages = d.get("totalPages", 0)
            ids += [x["id"] for x in d.get("content", [])]
            k += 1
    ids = list(dict.fromkeys(ids))
    print(f"news list: {len(ids)} unique items in {len(cats)} categories", flush=True)
    for n, i in enumerate(ids, 1):
        save(f"news/detail/{i}.json", f"news/detail/{i}")
        if n % 500 == 0:
            print(f"news details {n}/{len(ids)}", flush=True)
    print(f"PROKURATURA DONE: files {len(files)}, news {len(ids)}", flush=True)


if __name__ == "__main__":
    main()
