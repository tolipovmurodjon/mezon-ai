"""The public list of administrative-court rulings (public.sud.uz), page by page, as the site's own page loads it.

    .venv/Scripts/python.exe -X utf8 -m research.sud_list            # resumable; laptop only (Uzbek IP)

Boss approved calling the list endpoint the public page itself uses (20.11.2026):
adolatapi1.sud.uz/publications/list?size=N&page=P&court_type=ADMINISTRATIVE. List metadata only: court, instance,
case number, category, judges, result, document type, hearing date, and the page's pdf field as given. The ruling PDFs
stay behind the site's "Robot emasman" check and are never fetched or bypassed here. No party names are in the list.
One request every ~1.2 s (research/polite_http.py); every page cached, so a rerun continues. 67,615 rows on 20.11.2026.
Output: data/raw/sud/admin/rows.jsonl (one ruling per line) + data/interim/sud_admin_summary.json (counts).
"""

import collections
import json
import ssl
import sys
import time
from pathlib import Path

import httpx
import truststore

from research.polite_http import CACHE, WRITE_CACHE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "sud" / "admin"
API = "https://adolatapi1.sud.uz/publications/list?size={size}&page={page}&court_type={ct}"


# The court API sends an incomplete certificate chain; Chrome trusts it via the Windows store, so Python does too
# (truststore), with verification ON. Same pacing and cache-first rule as research/polite_http.py.
_client = httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=60,
                       headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
_last = 0.0


def page(n: int, size: int, ct: str) -> dict:
    global _last
    key = f"sud/list/{ct}/s{size}/p{n:05d}.json"
    for root in (CACHE, WRITE_CACHE):
        if (root / key).exists():
            return json.loads((root / key).read_text(encoding="utf-8"))
    for attempt in range(4):
        time.sleep(max(0.0, 1.2 - (time.monotonic() - _last)))
        _last = time.monotonic()
        try:
            r = _client.get(API.format(size=size, page=n, ct=ct))
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            (WRITE_CACHE / key).parent.mkdir(parents=True, exist_ok=True)
            (WRITE_CACHE / key).write_text(r.text, encoding="utf-8")
            return r.json()
        except httpx.HTTPError:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"page {n} failed 4 times")


def main(ct: str = "ADMINISTRATIVE", size: int = 100) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    first = page(0, size, ct)
    total, pages = first.get("totalElements"), first.get("totalPages")
    print(f"{ct}: {total:,} rows, {pages:,} pages of {size}", flush=True)
    rows, seen = [], set()
    for n in range(pages):
        for r in (first if n == 0 else page(n, size, ct)).get("content", []):
            if r.get("id") not in seen:
                seen.add(r.get("id"))
                rows.append(r)
        if n % 50 == 0:
            print(f"  page {n:,}/{pages:,}: {len(rows):,} rows", flush=True)
    with (OUT / "rows.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cat = collections.Counter((c.get("uz") or "")[:90] for r in rows for c in (r.get("categories") or []))
    res = collections.Counter(str(r.get("result")) for r in rows)
    year = collections.Counter((r.get("hearing_date") or "")[:4] for r in rows)
    summary = {"court_type": ct, "stated_total": total, "fetched": len(rows), "results": res.most_common(),
               "top_categories": cat.most_common(15), "by_year": sorted(year.items())}
    (ROOT / "data" / "interim" / f"sud_{ct.lower()}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("stated_total", "fetched", "results")}, ensure_ascii=False))



def stream(ct: str = "ADMINISTRATIVE", size: int = 50, start: int = 0) -> None:
    """Gap pass with no laptop disk: print each page's rows as JSON lines to stdout (piped over ssh to the box).
    A different page size shifts page boundaries, so rows the first pass lost to list movement show up."""
    global _last
    pages = None
    n = int(start)
    while pages is None or n < pages:
        for attempt in range(6):
            time.sleep(max(0.0, 1.2 - (time.monotonic() - _last)))
            _last = time.monotonic()
            try:
                r = _client.get(API.format(size=size, page=n, ct=ct))
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(15 * (attempt + 1))
                    continue
                r.raise_for_status()
                j = r.json()
                break
            except httpx.HTTPError:
                time.sleep(5 * (attempt + 1))
        else:
            print(f"page {n} failed", file=sys.stderr)
            n += 1
            continue
        pages = j.get("totalPages", 0)
        for row in j.get("content", []):
            sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if n % 100 == 0:
            print(f"page {n}/{pages}", file=sys.stderr, flush=True)
        n += 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["stream"]:
        stream(sys.argv[2] if len(sys.argv) > 2 else "ADMINISTRATIVE", 50, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else:
        main(*(sys.argv[1:2] or ["ADMINISTRATIVE"]))
