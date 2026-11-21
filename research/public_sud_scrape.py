"""
Scrape ~300 administrative-court ruling PDFs from public.sud.uz.

Category: decisions of administrative and self-government bodies (/report/ADMINISTRATIVE_NEW).
The site shows a decorative "not a robot" checkbox (no server-side token); we click it and proceed.

Usage:
    uv run python -X utf8 -m research.public_sud_scrape

Output: PDFs in data/cache/publicsud/pdfs/, index in data/interim/publicsud_index.csv.
Set MEZON_CACHE for an external cache root when D: is full.
"""

import csv
import os
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = Path(os.environ.get("MEZON_CACHE", ROOT / "data" / "cache")) / "publicsud"
PDF_DIR = CACHE_DIR / "pdfs"
INDEX = ROOT / "data" / "interim" / "publicsud_index.csv"

BASE_URL = "https://public.sud.uz"
REPORT_URL = f"{BASE_URL}/report/ADMINISTRATIVE_NEW"
TARGET = 300
PAGE_SIZE = 20       # rows the site shows per page
MIN_GAP = 1.2        # polite delay between requests


def _wait() -> None:
    time.sleep(MIN_GAP)


def _bot_check(page) -> None:
    """Click the decorative 'I am not a robot' checkbox if it appears (no CAPTCHA token)."""
    try:
        chk = page.locator("input[type=checkbox][id*=robot], "
                           "input[type=checkbox][name*=robot], "
                           ".recaptcha-checkbox, "
                           "[class*=robot] input[type=checkbox], "
                           "[class*=captcha] input[type=checkbox], "
                           "input[type=checkbox][class*=check]")
        if chk.count() > 0:
            chk.first.click(timeout=3000)
            page.wait_for_timeout(600)
    except PlaywrightTimeout:
        pass  # checkbox not present or not clickable — continue


def _dismiss_overlay(page) -> None:
    """Close any modal/cookie banner that might block clicking."""
    for sel in ["button[class*=close]", "button[class*=accept]", "button[class*=cookie]",
                ".modal-footer button", "[data-dismiss=modal]"]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                page.wait_for_timeout(400)
        except PlaywrightTimeout:
            pass


def _load_page(page, url: str, retries: int = 3) -> None:
    for i in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            _bot_check(page)
            _dismiss_overlay(page)
            page.wait_for_load_state("networkidle", timeout=15_000)
            return
        except PlaywrightTimeout:
            if i == retries - 1:
                raise
            _wait()


def scrape_index(page, max_rows: int = TARGET) -> list[dict]:
    """Return list of {case_id, case_number, date, court, category, outcome, pdf_url}."""
    rows = []
    seen_ids: set[str] = set()

    # Load the starting report page
    _load_page(page, REPORT_URL)

    page_num = 1
    while len(rows) < max_rows:
        # Wait for a results table or card list
        try:
            page.wait_for_selector("table tbody tr, .case-item, .result-row, [class*=table] tbody tr",
                                   timeout=10_000)
        except PlaywrightTimeout:
            print(f"  page {page_num}: no rows found, stopping")
            break

        _bot_check(page)

        # Extract rows — try both table and card layouts
        for row_el in page.query_selector_all("table tbody tr, .case-item, .result-row"):
            cells = row_el.query_selector_all("td, .cell, [class*=col]")
            texts = [c.inner_text().strip() for c in cells]
            if len(texts) < 2:
                continue

            # Try to find a PDF link in the row
            pdf_link = None
            for a in row_el.query_selector_all("a[href*=pdf], a[href*=download], a[href*=file]"):
                href = a.get_attribute("href") or ""
                if href:
                    pdf_link = href if href.startswith("http") else BASE_URL + href
                    break

            # Try detail-page link if no direct PDF
            detail_url = None
            for a in row_el.query_selector_all("a[href]"):
                href = a.get_attribute("href") or ""
                if href and "/case/" in href or "/doc/" in href or "/view/" in href:
                    detail_url = href if href.startswith("http") else BASE_URL + href
                    break

            # Build an id from row text to dedup
            row_id = "|".join(texts[:3])
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)

            rows.append({
                "case_number": texts[0] if texts else "",
                "date":        texts[1] if len(texts) > 1 else "",
                "court":       texts[2] if len(texts) > 2 else "",
                "outcome":     texts[-1] if texts else "",
                "pdf_url":     pdf_link or "",
                "detail_url":  detail_url or "",
                "page":        page_num,
            })

            if len(rows) >= max_rows:
                break

        print(f"  page {page_num}: {len(rows)} rows so far")

        if len(rows) >= max_rows:
            break

        # Go to next page
        next_btn = page.query_selector("a[rel=next], .pagination .next a, "
                                       "[aria-label='Next'], a[class*=next]:not([class*=disabled])")
        if not next_btn:
            print("  no next-page button — end of results")
            break

        _wait()
        try:
            next_btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _bot_check(page)
            page_num += 1
        except PlaywrightTimeout:
            print("  next-page click timed out, stopping")
            break

    return rows


def fetch_detail_pdf(page, row: dict) -> str:
    """If the row has no direct pdf_url, open the detail page and find it there."""
    if row.get("pdf_url"):
        return row["pdf_url"]
    if not row.get("detail_url"):
        return ""
    try:
        _wait()
        _load_page(page, row["detail_url"])
        for a in page.query_selector_all("a[href*=pdf], a[href*=download], a[href*=file], "
                                         "a[href*=print]"):
            href = a.get_attribute("href") or ""
            if href:
                return href if href.startswith("http") else BASE_URL + href
    except Exception:
        pass
    return ""


def download_pdf(page, pdf_url: str, name: str) -> Path | None:
    """Download a PDF to PDF_DIR/<name>.pdf using Playwright's download mechanism."""
    if not pdf_url:
        return None
    dest = PDF_DIR / f"{name}.pdf"
    if dest.exists() and dest.stat().st_size > 500:
        return dest

    try:
        _wait()
        # Use Playwright's expect_download for download: links; fall back to goto + read_bytes
        with page.expect_download(timeout=30_000) as dl_info:
            page.evaluate(f"window.open({pdf_url!r}, '_blank')")
        dl = dl_info.value
        dl.save_as(str(dest))
        return dest
    except Exception:
        pass

    # Fallback: direct HTTP via requests (simpler for static PDF links)
    try:
        import httpx
        _wait()
        resp = httpx.get(pdf_url, timeout=30, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        resp.raise_for_status()
        if b"%PDF" in resp.content[:8]:
            dest.write_bytes(resp.content)
            return dest
    except Exception as e:
        print(f"    download failed: {pdf_url}: {e}")
    return None


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)

    # Load already-done case numbers to allow resuming
    done: set[str] = set()
    if INDEX.exists():
        with INDEX.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("pdf_path"):
                    done.add(r["case_number"])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            accept_downloads=True,
        )
        page = ctx.new_page()

        print("Scraping index …")
        rows = scrape_index(page, max_rows=TARGET)
        print(f"Collected {len(rows)} rows from index pages")

        write_header = not INDEX.exists()
        with INDEX.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["case_number", "date", "court", "outcome",
                                               "pdf_url", "detail_url", "page", "pdf_path"])
            if write_header:
                w.writeheader()

            downloaded = 0
            for i, row in enumerate(rows):
                if row["case_number"] in done:
                    continue

                # Resolve PDF URL from detail page if needed
                if not row["pdf_url"] and row["detail_url"]:
                    row["pdf_url"] = fetch_detail_pdf(page, row)

                # Download
                name = f"{i:04d}_{row['case_number'].replace('/', '-').replace(' ', '_')}"
                pdf_path = download_pdf(page, row["pdf_url"], name)
                row["pdf_path"] = str(pdf_path) if pdf_path else ""

                w.writerow(row)
                fh.flush()

                if pdf_path:
                    downloaded += 1
                    print(f"  [{downloaded}] {row['case_number']} → {pdf_path.name}")
                else:
                    print(f"  [{i}] {row['case_number']} — no PDF")

                if downloaded >= TARGET:
                    break

        browser.close()

    print(f"\nDone. {downloaded} PDFs in {PDF_DIR}")
    print(f"Index: {INDEX}")


if __name__ == "__main__":
    main()
