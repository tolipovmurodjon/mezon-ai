"""Download every public.sud.uz administrative ruling PDF — all 61,049.

The 'Robot emasman' gate is a plain HTML <form> with a checkbox (no CAPTCHA):
  GET detail_page → parse <form> → POST with checkbox=1 + hidden fields → PDF arrives.
No Playwright needed. Pure httpx.

Usage (box, ~/10_projects/mezon/):
  .venv/bin/python -X utf8 research/pdf_all.py            # 8 workers, saves to ~/mezon_pdfs/
  MEZON_PDF_DIR=/mnt/fast .venv/bin/python ... pdf_all.py --workers 16

Resumes on restart: skips already-saved PDFs.
Reads existing index from data/interim/publicsud_index.csv if present;
otherwise fetches the full list from the site's own list API first.
"""

import asyncio
import csv
import html as html_lib
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

# ── paths ──────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).resolve().parents[1]
PDF_DIR = Path(os.environ.get("MEZON_PDF_DIR", Path.home() / "mezon_pdfs"))
INDEX  = ROOT / "data" / "interim" / "publicsud_index.csv"

# ── constants ──────────────────────────────────────────────────────────────
BASE  = "https://public.sud.uz"
UA    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
GAP   = 0.4          # seconds between requests PER WORKER (8 workers → ~20 req/s total)
RETRY = 4


# ══════════════════════════════════════════════════════════════════════════
#  STEP 1 — build the full index (if not already on disk)
# ══════════════════════════════════════════════════════════════════════════

def _parse_list_response(data) -> list[dict]:
    """Extract rows from whatever the list API returns (JSON array or list key)."""
    if isinstance(data, list):
        return data
    for key in ("data", "result", "items", "rows", "content", "list"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def _extract_rows_html(html: str) -> list[dict]:
    """Fallback: parse <tr> rows from an HTML page."""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        texts = [re.sub(r"<[^>]+>", " ", c).strip() for c in cells]
        if len(texts) < 2:
            continue
        url = ""
        for a in re.finditer(r'href="([^"]+)"', row):
            href = a.group(1)
            if any(x in href for x in ("/case/", "/doc/", "/view/", "/decision/", ".pdf")):
                url = href if href.startswith("http") else BASE + href
                break
        rows.append({"case_number": texts[0], "date": texts[1] if len(texts) > 1 else "",
                     "court": texts[2] if len(texts) > 2 else "", "url": url})
    return rows


async def build_index(client: httpx.AsyncClient) -> list[dict]:
    """Fetch the full list from public.sud.uz — tries the XHR/JSON API first, falls back to HTML paging."""
    all_rows: list[dict] = []

    # ── probe the list API ─────────────────────────────────────────────────
    # The site's own network requests use one of these patterns; we try all.
    api_candidates = [
        # JSON API variants (observed pattern from other session)
        f"{BASE}/api/decisions?category=ADMINISTRATIVE_NEW&page={{page}}&size=100",
        f"{BASE}/api/report/ADMINISTRATIVE_NEW?page={{page}}&size=100",
        f"{BASE}/report/ADMINISTRATIVE_NEW/data?page={{page}}&size=100",
        f"{BASE}/report/api?type=ADMINISTRATIVE_NEW&page={{page}}&size=100",
    ]

    working_template: str | None = None
    for tmpl in api_candidates:
        try:
            url = tmpl.format(page=1)
            r = await client.get(url, headers={"Accept": "application/json, text/plain, */*",
                                               "X-Requested-With": "XMLHttpRequest"})
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    data = r.json()
                    rows = _parse_list_response(data)
                    if rows:
                        working_template = tmpl
                        print(f"List API found: {tmpl.format(page='N')}", flush=True)
                        all_rows.extend(rows)
                        break
        except Exception:
            pass

    # ── paginate via working API ───────────────────────────────────────────
    if working_template:
        page = 2
        while True:
            await asyncio.sleep(GAP)
            try:
                r = await client.get(working_template.format(page=page),
                                     headers={"Accept": "application/json",
                                              "X-Requested-With": "XMLHttpRequest"})
                r.raise_for_status()
                data = r.json()
                rows = _parse_list_response(data)
                if not rows:
                    break
                all_rows.extend(rows)
                if page % 50 == 0:
                    print(f"  list page {page}: {len(all_rows)} rows so far", flush=True)
                page += 1
                # Safety: stop at 70 K (more than the known 61,049)
                if len(all_rows) >= 70_000:
                    break
            except Exception as e:
                print(f"  list page {page} error: {e}", flush=True)
                break

    # ── fallback: HTML paging ──────────────────────────────────────────────
    if not all_rows:
        print("JSON API not found, falling back to HTML paging …", flush=True)
        page = 1
        while True:
            await asyncio.sleep(GAP)
            try:
                r = await client.get(f"{BASE}/report/ADMINISTRATIVE_NEW?page={page}")
                r.raise_for_status()
                rows = _extract_rows_html(r.text)
                if not rows:
                    break
                all_rows.extend(rows)
                if page % 20 == 0:
                    print(f"  html page {page}: {len(all_rows)} rows", flush=True)
                page += 1
                if len(all_rows) >= 70_000:
                    break
            except Exception as e:
                print(f"  html page {page} error: {e}", flush=True)
                break

    print(f"Index built: {len(all_rows)} rows", flush=True)
    return all_rows


def save_index(rows: list[dict]) -> None:
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = list(rows[0].keys())
    for key in ("url", "detail_url", "pdf_url"):
        if key not in fields:
            fields.append(key)
    with INDEX.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Index saved → {INDEX}", flush=True)


def load_index() -> list[dict]:
    rows = []
    with INDEX.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {INDEX}", flush=True)
    return rows


# ══════════════════════════════════════════════════════════════════════════
#  STEP 2 — download each PDF, handling the robot form
# ══════════════════════════════════════════════════════════════════════════

def _parse_form(html: str) -> tuple[str, dict]:
    """Return (action_url, {field: value}). Checkbox fields are set to '1'."""
    action_m = re.search(r'<form[^>]+action="([^"]*)"', html, re.IGNORECASE)
    action = html_lib.unescape(action_m.group(1)) if action_m else ""

    fields: dict[str, str] = {}
    for m in re.finditer(r'<input([^>]*)>', html, re.IGNORECASE):
        attrs = m.group(1)
        name  = re.search(r'name="([^"]*)"',  attrs, re.IGNORECASE)
        value = re.search(r'value="([^"]*)"', attrs, re.IGNORECASE)
        typ   = re.search(r'type="([^"]*)"',  attrs, re.IGNORECASE)
        if not name:
            continue
        n = html_lib.unescape(name.group(1))
        v = html_lib.unescape(value.group(1)) if value else ""
        t = (typ.group(1) if typ else "text").lower()
        if t in ("submit", "reset", "button", "image"):
            continue
        fields[n] = "1" if t == "checkbox" else v

    # <select> → first <option>
    for sm in re.finditer(r'<select[^>]+name="([^"]*)"[^>]*>(.*?)</select>', html,
                          re.DOTALL | re.IGNORECASE):
        n = html_lib.unescape(sm.group(1))
        om = re.search(r'<option[^>]+value="([^"]*)"', sm.group(2), re.IGNORECASE)
        fields[n] = html_lib.unescape(om.group(1)) if om else ""

    return action, fields


def _find_pdf_url(html: str) -> str:
    """Find any PDF href/src in an HTML page."""
    for pat in (r'href="([^"]*\.pdf[^"]*)"', r'src="([^"]*\.pdf[^"]*)"',
                r'href="([^"]*download[^"]*)"', r'href="([^"]*file[^"]*)"'):
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            u = html_lib.unescape(m.group(1))
            return u if u.startswith("http") else BASE + u
    return ""


def _safe_name(s: str) -> str:
    return re.sub(r"[^\w\-]", "_", str(s))[:80]


async def download_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    row: dict,
    idx: int,
) -> bool:
    # Find the best URL to start from
    url = (row.get("url") or row.get("detail_url") or row.get("pdf_url") or "").strip()
    if not url:
        return False
    if not url.startswith("http"):
        url = BASE + url

    case_id = _safe_name(row.get("id") or row.get("case_number") or row.get("case_id") or f"row{idx}")
    dest = PDF_DIR / f"{case_id}.pdf"
    if dest.exists() and dest.stat().st_size > 300:
        return True

    for attempt in range(RETRY):
        async with sem:
            await asyncio.sleep(GAP)
            try:
                # ── GET the page ──────────────────────────────────────────
                r = await client.get(url)
                if r.status_code == 404:
                    return False
                if r.status_code in (429, 503) or r.status_code >= 500:
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                r.raise_for_status()

                # Already a PDF?
                ct = r.headers.get("content-type", "")
                if "pdf" in ct or r.content[:4] == b"%PDF":
                    dest.write_bytes(r.content)
                    return True

                html = r.text

                # ── Handle robot form (or any form) ───────────────────────
                if "<form" in html.lower():
                    action, fields = _parse_form(html)
                    post_url = (action if action.startswith("http")
                                else (BASE + action if action.startswith("/")
                                      else url))
                    await asyncio.sleep(GAP)
                    r2 = await client.post(post_url, data=fields)
                    r2.raise_for_status()

                    ct2 = r2.headers.get("content-type", "")
                    if "pdf" in ct2 or r2.content[:4] == b"%PDF":
                        dest.write_bytes(r2.content)
                        return True

                    # POST returned HTML — look for PDF link inside
                    pdf_url = _find_pdf_url(r2.text)
                    if pdf_url:
                        await asyncio.sleep(GAP)
                        r3 = await client.get(pdf_url)
                        if r3.content[:4] == b"%PDF":
                            dest.write_bytes(r3.content)
                            return True

                else:
                    # No form — look for direct PDF link in the page
                    pdf_url = _find_pdf_url(html)
                    if pdf_url:
                        await asyncio.sleep(GAP)
                        r2 = await client.get(pdf_url)
                        if r2.content[:4] == b"%PDF":
                            dest.write_bytes(r2.content)
                            return True

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                if attempt == RETRY - 1:
                    print(f"ERR {case_id}: {e}", flush=True)
                    return False
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                print(f"ERR {case_id}: {type(e).__name__}: {e}", flush=True)
                return False

    return False


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

async def run(workers: int) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        headers={"User-Agent": UA},
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=workers + 8, max_keepalive_connections=workers),
    ) as client:

        # ── Step 1: index ──────────────────────────────────────────────────
        if INDEX.exists():
            rows = load_index()
        else:
            print("No index found — fetching full list from public.sud.uz …", flush=True)
            rows = await build_index(client)
            save_index(rows)

        if not rows:
            print("No rows to process. Exiting.")
            return

        already = sum(1 for r in rows
                      if (PDF_DIR / f"{_safe_name(r.get('id') or r.get('case_number') or '')}.pdf").exists())
        print(f"Total: {len(rows)} | Already done: {already} | Left: {len(rows) - already}", flush=True)

        # ── Step 2: download ───────────────────────────────────────────────
        sem  = asyncio.Semaphore(workers)
        done = 0
        fail = 0
        t0   = time.time()

        async def task(i: int, row: dict) -> None:
            nonlocal done, fail
            ok = await download_one(client, sem, row, i)
            if ok:
                done += 1
                if done % 500 == 0:
                    el = time.time() - t0
                    print(f"  ✓ {done} PDFs  {el/3600:.1f}h  {done/el:.1f}/s", flush=True)
            else:
                fail += 1

        await asyncio.gather(*[task(i, r) for i, r in enumerate(rows)])

    elapsed = time.time() - t0
    print(f"\n✓ {done} PDFs saved to {PDF_DIR}  ({fail} failed)  {elapsed/3600:.1f}h", flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Download all public.sud.uz PDFs")
    p.add_argument("--workers", type=int, default=8, help="concurrent downloads (default 8)")
    args = p.parse_args()
    print(f"Starting {args.workers} workers → {PDF_DIR}", flush=True)
    asyncio.run(run(args.workers))
