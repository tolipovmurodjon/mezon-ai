"""Download all public.sud.uz PDFs using a browser auth token — no CAPTCHA needed after once.

HOW TO GET THE TOKEN (one-time, ~2 minutes):
1. Open https://public.sud.uz/report/CIVIL in your browser
2. Click any PDF button → tick "Robot emasman" once
3. Open DevTools (F12) → Network tab → find the request to:
     download_as_buffer/XXXXXXXX
4. Click that request → Headers tab → copy the value of:
     X-AUTH-TOKEN: <paste-this-value>
5. Set env var:  SUD_TOKEN="<value>"
   Or pass CLI:  python sud_pdf_cookie.py --token "eyJhbGciOi..."

The scraper sends that token for all 7.6M+ downloads — no more checkboxes.
Run from the box (public.sud.uz is globally accessible — no UZ ISP needed for PDFs).

Usage:
  SUD_TOKEN="eyJ..." python -X utf8 research/sud_pdf_cookie.py
  python -X utf8 research/sud_pdf_cookie.py --token "eyJ..." --workers 30
  python -X utf8 research/sud_pdf_cookie.py --build-index   # rebuild index from JSON chunks
  python -X utf8 research/sud_pdf_cookie.py --status        # show counts only

Input:  ~/mezon/data/raw/sud/full/  (JSON chunks already downloaded)
Output: ~/mezon/data/raw/sud/pdfs/<file_id>.pdf
"""

import argparse
import asyncio
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

BOX_DATA = Path(os.environ.get("BOX_DATA", Path.home() / "mezon/data/raw/sud/full"))
BASE     = "https://public.sud.uz"
API_DL   = BASE + "/api/cabinet/case/download_as_buffer/{file_id}"
UA       = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PDF_DIR  = Path(os.environ.get("MEZON_PDF_DIR", Path.home() / "mezon/data/raw/sud/pdfs"))
GAP      = 0.1   # seconds between requests per worker
RETRY    = 5


def _safe(s: str) -> str:
    return re.sub(r"[^\w\-]", "_", str(s))[:80]


def build_index() -> list[int]:
    """Scan all downloaded JSON chunks and extract fileData.id values."""
    file_ids = []
    sections = [d for d in BOX_DATA.iterdir() if d.is_dir()]
    for section in sorted(sections):
        chunks = sorted(section.glob("chunk_*.jsonl.gz"))
        section_ids = 0
        for chunk in chunks:
            try:
                with gzip.open(chunk, "rb") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            fd = rec.get("fileData")
                            if fd and fd.get("id"):
                                file_ids.append(int(fd["id"]))
                                section_ids += 1
                        except Exception:
                            pass
            except Exception as e:
                print(f"  skip {chunk}: {e}", flush=True)
        if section_ids:
            print(f"  {section.name}: {section_ids:,} file IDs", flush=True)
    print(f"Total file IDs: {len(file_ids):,}", flush=True)
    return file_ids


def load_file_ids() -> list[int]:
    cache = PDF_DIR.parent / "pdf_index.txt"
    if cache.exists():
        ids = [int(x) for x in cache.read_text().splitlines() if x.strip().isdigit()]
        print(f"Loaded {len(ids):,} file IDs from cache {cache}", flush=True)
        return ids
    print("Building index from JSON chunks (first run only)...", flush=True)
    ids = build_index()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(str(i) for i in ids))
    print(f"Cached to {cache}", flush=True)
    return ids


async def download_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    file_id: int,
    dest: Path,
    token_expired: list,
) -> bool:
    if dest.exists() and dest.stat().st_size > 300:
        return True
    if token_expired:
        return False

    for attempt in range(RETRY):
        async with sem:
            await asyncio.sleep(GAP)
            try:
                url = API_DL.format(file_id=file_id)
                r = await client.get(url)

                if r.status_code == 401:
                    if not token_expired:
                        token_expired.append(True)
                        print("\nERROR: 401 Unauthorized — X-AUTH-TOKEN expired or wrong.", flush=True)
                        print("  Get a fresh token: F12 → Network → download_as_buffer request → X-AUTH-TOKEN header", flush=True)
                    return False

                if r.status_code == 404:
                    return False   # file genuinely absent

                if r.status_code == 429 or r.status_code >= 500:
                    await asyncio.sleep(10 * (attempt + 1))
                    continue

                ct = r.headers.get("content-type", "")
                if "pdf" in ct or r.content[:4] == b"%PDF":
                    dest.write_bytes(r.content)
                    return True

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt == RETRY - 1:
                    print(f"ERR {file_id}: {e}", flush=True)
                    return False
                await asyncio.sleep(2 ** attempt)

    return False


async def run(token: str, workers: int) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    file_ids = load_file_ids()

    todo = [fid for fid in file_ids
            if not (PDF_DIR / f"{fid}.pdf").exists()]
    already = len(file_ids) - len(todo)

    print(f"Total: {len(file_ids):,} | Already done: {already:,} | To download: {len(todo):,}", flush=True)
    if not todo:
        print("All done!")
        return

    headers = {
        "User-Agent": UA,
        "X-AUTH-TOKEN": token,
        "Referer": BASE,
        "Accept": "application/pdf,*/*",
    }

    sem           = asyncio.Semaphore(workers)
    token_expired = []
    done = 0
    fail = 0
    t0   = time.time()

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
        verify=False,
        limits=httpx.Limits(max_connections=workers + 8, max_keepalive_connections=workers),
    ) as client:

        async def task(file_id: int) -> None:
            nonlocal done, fail
            dest = PDF_DIR / f"{file_id}.pdf"
            ok = await download_one(client, sem, file_id, dest, token_expired)
            if ok:
                done += 1
                if done % 1000 == 0:
                    el = time.time() - t0
                    rate = done / max(el, 1)
                    print(f"  {done:,} done  {rate:.1f}/s  "
                          f"~{(len(todo)-done)/max(rate,0.1)/3600:.1f}h left", flush=True)
            else:
                fail += 1

        await asyncio.gather(*[task(fid) for fid in todo])

    elapsed = time.time() - t0
    print(f"\nDone: {done:,} PDFs → {PDF_DIR}  ({fail:,} failed)  {elapsed/3600:.1f}h", flush=True)


def status() -> None:
    file_ids = load_file_ids()
    done = sum(1 for fid in file_ids if (PDF_DIR / f"{fid}.pdf").exists())
    print(f"Done: {done:,} / {len(file_ids):,}  ({100*done/max(len(file_ids),1):.1f}%)")
    print(f"PDF dir: {PDF_DIR}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Download public.sud.uz PDFs via X-AUTH-TOKEN")
    p.add_argument("--token", default=os.environ.get("SUD_TOKEN", ""),
                   help="X-AUTH-TOKEN from browser DevTools network request")
    p.add_argument("--workers", type=int, default=30)
    p.add_argument("--build-index", action="store_true", help="Rebuild file ID index from JSON chunks")
    p.add_argument("--status", action="store_true")
    args = p.parse_args()

    if args.build_index:
        ids = build_index()
        cache = PDF_DIR.parent / "pdf_index.txt"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\n".join(str(i) for i in ids))
        print(f"Wrote {len(ids):,} IDs to {cache}", flush=True)
        sys.exit(0)

    if args.status:
        status()
        sys.exit(0)

    if not args.token:
        print(__doc__)
        print("\nERROR: --token required (or set SUD_TOKEN env var).")
        sys.exit(1)

    print(f"Starting {args.workers} workers → {PDF_DIR}", flush=True)
    asyncio.run(run(args.token, args.workers))
