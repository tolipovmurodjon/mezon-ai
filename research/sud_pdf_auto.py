#!/usr/bin/env python3
"""
sud.uz PDF pipeline — PoW captcha → download → text extract → JSONL → delete.

ARCHITECTURE (expert mode):
  • Never keep raw PDFs:  download bytes → extract text → write JSONL → discard bytes
  • Storage: ~840GB raw → ~20GB text JSONL (gzip)
  • 100 async workers; PoW solved in parallel on all CPU cores
  • Scanned PDFs (< MIN_CHARS text) queued to ~/mezon/data/raw/sud/ocr_queue/
    for PaddleOCR GPU pass (run separately: sud_ocr_gpu.py)
  • Hash-sharded temp dirs avoid ext4 slowdown (never >50K files per dir)

OUTPUT FORMAT (per JSONL record):
  {file_id, section, case_number, court, judge, claimant, defendant,
   result, hearing_date, text, page_count, char_count, extraction}

HOW IT WORKS (reverse-engineered from scripts.79b8ce1da5f99f001e92.js):
  1. POST recaptcha.sud.uz/api/v1/captcha/pow/challenge → {challenge, difficulty}
  2. Find nonce: SHA256(challenge+str(nonce)) has ≥ difficulty leading zero bits
  3. POST recaptcha.sud.uz/api/v1/captcha/analyze with PoW+signals → {token: uuid}
  4. GET adolatapi1.sud.uz/api/cabinet/case/download_as_buffer/{fileId}
       X-AUTH-TOKEN: {uuid} → base64-or-binary PDF bytes

RUN:
  python3 -X utf8 sud_pdf_auto.py                     # start (waits for captcha server)
  python3 -X utf8 sud_pdf_auto.py --workers 150        # more workers
  python3 -X utf8 sud_pdf_auto.py --no-wait            # fail fast if captcha server down
  python3 -X utf8 sud_pdf_auto.py --build-index        # rebuild file ID index
  python3 -X utf8 sud_pdf_auto.py --status             # show counts
"""

import argparse, asyncio, base64, gzip, hashlib, io, json, os, random
import subprocess, sys, tempfile, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import httpx

# ── Config ────────────────────────────────────────────────────────────────────

CAPTCHA_BASE = "https://recaptcha.sud.uz"
API_BASE     = "https://adolatapi1.sud.uz"
SITE_KEY     = "site_1842e42b6e31fb21ac22c681def0e326"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")

ROOT         = Path(os.environ.get("MEZON_ROOT", Path.home() / "mezon"))
BOX_DATA     = ROOT / "data/raw/sud/full"
TEXT_DIR     = ROOT / "data/raw/sud/text"       # extracted JSONL output
OCR_QUEUE    = ROOT / "data/raw/sud/ocr_queue"  # scanned PDFs needing GPU OCR
INDEX_TXT    = ROOT / "data/raw/sud/pdf_index.txt"
DONE_TXT     = ROOT / "data/raw/sud/pdf_done.txt"   # one file_id per line
LOG_FILE     = ROOT / "logs/pdf_auto.log"

WORKERS      = 100
RETRY        = 4
MIN_CHARS    = 100   # below this → scanned PDF, queue for OCR
TEXT_CHUNK   = 5000  # records per output JSONL.gz file


# ── PoW (runs in process pool for CPU parallelism) ────────────────────────────

def _solve_pow_sync(challenge: str, difficulty: int) -> tuple[str, int]:
    nonce = 0
    t0 = time.monotonic()
    while True:
        h = hashlib.sha256((challenge + str(nonce)).encode()).digest()
        # count leading zero bits
        cnt = 0
        for byte in h:
            if byte == 0:
                cnt += 8
            else:
                b = byte
                while b & 0x80 == 0:
                    cnt += 1
                    b <<= 1
                break
        if cnt >= difficulty:
            return str(nonce), int((time.monotonic() - t0) * 1000)
        nonce += 1


_pool: ProcessPoolExecutor | None = None

async def solve_pow(challenge: str, difficulty: int) -> tuple[str, int]:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor()
    return await asyncio.get_event_loop().run_in_executor(
        _pool, _solve_pow_sync, challenge, difficulty)


# ── Fake human signals ────────────────────────────────────────────────────────

def _signals(pow_result: dict) -> dict:
    return {
        "siteKey":   SITE_KEY,
        "action":    "widget_click",
        "timestamp": int(time.time() * 1000),
        "signals": {
            "mouse": {
                "moveCount": random.randint(25, 90),
                "avgSpeed":  round(random.uniform(0.3, 1.5), 2),
                "maxSpeed":  round(random.uniform(2.0, 6.0), 2),
                "curvatureVariance":  round(random.uniform(0.001, 0.05), 3),
                "straightLineRatio":  round(random.uniform(0.5, 0.9), 2),
                "clickCount": 1,
            },
            "keyboard": {"keystrokeCount": 0, "avgInterval": 0, "holdDurationVariance": 0},
            "scroll": {
                "count": random.randint(1, 6),
                "directionChanges": random.randint(0, 3),
                "smoothRatio": round(random.uniform(0.5, 0.9), 2),
            },
            "touch": {"eventCount": 0, "gestureTypes": [], "multiTouch": False},
            "timing": {
                "pageLoadToFirstInteraction":    random.randint(1500, 9000),
                "pageLoadToTokenRequest":        random.randint(5000, 25000),
                "firstInteractionToTokenRequest": random.randint(800, 6000),
            },
            "fingerprint": {
                "screenResolution": "1920x1080",
                "colorDepth":       24,
                "timezone":         "Asia/Tashkent",
                "language":         "uz-UZ",
                "platform":         "Win32",
                "pluginCount":      3,
                "doNotTrack":       None,
                "hardwareConcurrency": 8,
                "deviceMemory":     8,
                "canvasHash":       "a1b2c3d4",
                "webglRenderer":    "ANGLE (Intel, Intel(R) UHD Graphics 630, OpenGL 4.6)",
                "hash":             "e5f6a7b8",
            },
            "botFlags": {
                "webdriver": False, "selenium": False, "nightmare": False,
                "phantom": False, "chromeObjectMissing": False,
                "zeroPlugins": False, "headlessUserAgent": False,
                "zeroOuterDimensions": False,
            },
            "honeypotFilled": False,
            "pow": pow_result,
        }
    }


# ── Captcha token ─────────────────────────────────────────────────────────────

async def get_token(client: httpx.AsyncClient) -> str | None:
    try:
        r = await client.post(
            f"{CAPTCHA_BASE}/api/v1/captcha/pow/challenge",
            json={"siteKey": SITE_KEY},
            timeout=10.0
        )
        if r.status_code != 200:
            return None
        d = r.json()
        nonce, ms = await solve_pow(d["challenge"], d["difficulty"])
        pow_result = {"challenge": d["challenge"], "nonce": nonce, "solveTimeMs": ms, "solved": True}

        r2 = await client.post(
            f"{CAPTCHA_BASE}/api/v1/captcha/analyze",
            json=_signals(pow_result),
            timeout=15.0
        )
        if r2.status_code != 200:
            return None
        d2 = r2.json()
        if d2.get("challengeRequired"):
            return None   # math puzzle — skip, re-queue
        return d2.get("token")
    except Exception:
        return None


async def captcha_alive(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.post(
            f"{CAPTCHA_BASE}/api/v1/captcha/pow/challenge",
            json={"siteKey": SITE_KEY},
            timeout=8.0
        )
        return r.status_code == 200
    except Exception:
        return False


# ── PDF → text ────────────────────────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes) -> tuple[str, int, str]:
    """Return (text, page_count, method).  method in {pdftotext, pdfminer, ocr_queued}."""
    # Try pdftotext first (fastest)
    try:
        r = subprocess.run(
            ["pdftotext", "-q", "-", "-"],
            input=pdf_bytes, capture_output=True, timeout=30
        )
        if r.returncode == 0:
            text = r.stdout.decode("utf-8", errors="ignore").strip()
            # Estimate pages via form feed
            pages = text.count("\x0c") + 1
            if len(text) >= MIN_CHARS:
                return text, pages, "pdftotext"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: pdfminer
    try:
        from pdfminer.high_level import extract_text as pm_extract
        from pdfminer.pdfpage import PDFPage
        text = pm_extract(io.BytesIO(pdf_bytes)).strip()
        pages = sum(1 for _ in PDFPage.get_pages(io.BytesIO(pdf_bytes)))
        if len(text) >= MIN_CHARS:
            return text, pages, "pdfminer"
    except Exception:
        pass

    # No text — scanned document
    return "", 0, "ocr_queued"


# ── PDF bytes from response (base64 JSON or raw) ──────────────────────────────

def _parse_pdf_response(content: bytes, content_type: str) -> bytes | None:
    # Raw PDF
    if content[:4] == b"%PDF":
        return content

    # JSON with base64 field
    if b"{" in content[:20]:
        try:
            d = json.loads(content)
            for key in ("data", "content", "file", "buffer", "base64"):
                v = d.get(key)
                if isinstance(v, str) and len(v) > 100:
                    try:
                        b = base64.b64decode(v)
                        if b[:4] == b"%PDF":
                            return b
                    except Exception:
                        pass
        except Exception:
            pass

    # Maybe the whole body is base64
    if len(content) > 100:
        try:
            b = base64.b64decode(content)
            if b[:4] == b"%PDF":
                return b
        except Exception:
            pass

    return None


# ── Index ─────────────────────────────────────────────────────────────────────

def build_index() -> list[dict]:
    """Scan JSON chunks → list of {file_id, section, case_number, court, ...}."""
    records = []
    if not BOX_DATA.exists():
        print(f"BOX_DATA not found: {BOX_DATA}", flush=True)
        return records

    for section_dir in sorted(BOX_DATA.iterdir()):
        if not section_dir.is_dir():
            continue
        section = section_dir.name
        cnt = 0

        def _iter_lines(chunk):
            if chunk.suffix == ".gz":
                with gzip.open(chunk, "rb") as f:
                    yield from f
            else:
                with open(chunk, encoding="utf-8", errors="ignore") as f:
                    yield from f

        for chunk in sorted(section_dir.glob("chunk_*.jsonl*")):
            try:
                for line in _iter_lines(chunk):
                    try:
                        rec = json.loads(line)
                        fd = rec.get("fileData")
                        if fd and fd.get("id"):
                            records.append({
                                "file_id":     int(fd["id"]),
                                "section":     section,
                                "case_number": rec.get("caseNumber", ""),
                                "court":       rec.get("dbName", ""),
                                "judge":       rec.get("judge", ""),
                                "claimant":    rec.get("claimant", ""),
                                "defendant":   rec.get("defendant", ""),
                                "result":      rec.get("result", ""),
                                "hearing_date": rec.get("hearingDate", 0),
                                "category":    rec.get("category", ""),
                            })
                            cnt += 1
                    except Exception:
                        pass
            except Exception as e:
                print(f"  skip {chunk}: {e}", flush=True)
        if cnt:
            print(f"  {section}: {cnt:,}", flush=True)
    print(f"Total: {len(records):,}", flush=True)
    return records


def save_index(records: list[dict]):
    INDEX_TXT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(str(INDEX_TXT) + ".gz", "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # Also plain list of IDs for quick done-check
    INDEX_TXT.write_text("\n".join(str(r["file_id"]) for r in records))
    print(f"Saved index: {len(records):,} records → {INDEX_TXT}.gz", flush=True)


def load_index() -> list[dict]:
    gz = Path(str(INDEX_TXT) + ".gz")
    if gz.exists():
        recs = []
        with gzip.open(gz, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
        print(f"Loaded {len(recs):,} records from {gz}", flush=True)
        return recs
    # Fall back to plain ID list (older format)
    if INDEX_TXT.exists():
        ids = [int(x) for x in INDEX_TXT.read_text().splitlines() if x.strip().isdigit()]
        print(f"Loaded {len(ids):,} IDs (plain) from {INDEX_TXT}", flush=True)
        return [{"file_id": i, "section": "UNKNOWN"} for i in ids]
    # Build from scratch
    print("Building index from JSON chunks...", flush=True)
    recs = build_index()
    save_index(recs)
    return recs


def load_done() -> set[int]:
    if DONE_TXT.exists():
        return {int(x) for x in DONE_TXT.read_text().splitlines() if x.strip().isdigit()}
    # Also scan text dir for already-extracted records
    done = set()
    if TEXT_DIR.exists():
        for chunk in TEXT_DIR.rglob("*.jsonl.gz"):
            try:
                with gzip.open(chunk, "rt", encoding="utf-8") as f:
                    for line in f:
                        try:
                            done.add(int(json.loads(line)["file_id"]))
                        except Exception:
                            pass
            except Exception:
                pass
    return done


# ── JSONL writer (thread-safe) ────────────────────────────────────────────────

class TextWriter:
    def __init__(self):
        self._lock    = asyncio.Lock()
        self._buf:    list[dict] = []
        self._chunk   = 0
        self._written = 0
        TEXT_DIR.mkdir(parents=True, exist_ok=True)

    async def write(self, record: dict):
        async with self._lock:
            self._buf.append(record)
            if len(self._buf) >= TEXT_CHUNK:
                await asyncio.to_thread(self._flush)

    def _flush(self):
        if not self._buf:
            return
        path = TEXT_DIR / f"chunk_{self._chunk:05d}.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as f:
            for r in self._buf:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self._written += len(self._buf)
        self._chunk   += 1
        self._buf.clear()

    async def flush_final(self):
        async with self._lock:
            await asyncio.to_thread(self._flush)

    @property
    def written(self):
        return self._written + len(self._buf)


# ── Done tracker (periodic flush) ────────────────────────────────────────────

class DoneTracker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._buf: list[int] = []

    async def mark(self, file_id: int):
        async with self._lock:
            self._buf.append(file_id)
            if len(self._buf) >= 500:
                await asyncio.to_thread(self._flush)

    def _flush(self):
        if not self._buf:
            return
        with open(DONE_TXT, "a") as f:
            for fid in self._buf:
                f.write(f"{fid}\n")
        self._buf.clear()

    async def flush_final(self):
        async with self._lock:
            await asyncio.to_thread(self._flush)


# ── OCR queue ─────────────────────────────────────────────────────────────────

def _ocr_subdir(file_id: int) -> Path:
    s = str(file_id)
    return OCR_QUEUE / s[-2:] / s[-4:-2]

async def queue_for_ocr(file_id: int, pdf_bytes: bytes, meta: dict):
    subdir = _ocr_subdir(file_id)
    await asyncio.to_thread(subdir.mkdir, parents=True, exist_ok=True)
    pdf_path  = subdir / f"{file_id}.pdf"
    meta_path = subdir / f"{file_id}.json"
    await asyncio.to_thread(pdf_path.write_bytes, pdf_bytes)
    await asyncio.to_thread(meta_path.write_text, json.dumps(meta, ensure_ascii=False))


# ── Single download worker ────────────────────────────────────────────────────

async def process_one(
    client_dl:  httpx.AsyncClient,
    client_cap: httpx.AsyncClient,
    sem:        asyncio.Semaphore,
    rec:        dict,
    writer:     TextWriter,
    done_tracker: DoneTracker,
    counters:   dict,
):
    file_id = rec["file_id"]

    for attempt in range(RETRY):
        async with sem:
            try:
                token = await get_token(client_cap)
                if token is None:
                    counters["captcha_fail"] += 1
                    await asyncio.sleep(5 + attempt * 10)
                    continue

                url = f"{API_BASE}/api/cabinet/case/download_as_buffer/{file_id}"
                r = await client_dl.get(url, headers={"X-AUTH-TOKEN": token}, timeout=60.0)

                if r.status_code == 404:
                    counters["no_file"] += 1
                    await done_tracker.mark(file_id)
                    return

                if r.status_code == 401:
                    counters["token_reject"] += 1
                    await asyncio.sleep(1)
                    continue

                if r.status_code >= 500:
                    await asyncio.sleep(10 * (attempt + 1))
                    continue

                if r.status_code != 200:
                    continue

                # Parse response (base64 JSON or raw PDF)
                pdf_bytes = _parse_pdf_response(r.content, r.headers.get("content-type", ""))
                if pdf_bytes is None:
                    counters["parse_fail"] += 1
                    return

                # Extract text
                text, pages, method = await asyncio.to_thread(_extract_text, pdf_bytes)

                if method == "ocr_queued":
                    await queue_for_ocr(file_id, pdf_bytes, rec)
                    counters["ocr_queued"] += 1
                    await done_tracker.mark(file_id)
                    return

                # Write to JSONL
                out = {**rec, "text": text, "page_count": pages,
                       "char_count": len(text), "extraction": method}
                await writer.write(out)
                await done_tracker.mark(file_id)
                counters["done"] += 1

                if counters["done"] % 1000 == 0:
                    el = counters.get("_t0", 0)
                    if el:
                        rate = counters["done"] / max(time.time() - el, 1)
                        total = counters.get("_total", 0)
                        left_h = (total - counters["done"]) / max(rate, 0.1) / 3600
                        print(
                            f"  {counters['done']:,} done  {rate:.1f}/s  ~{left_h:.1f}h left"
                            f"  ocr_q={counters['ocr_queued']}  no_file={counters['no_file']}"
                            f"  cap_fail={counters['captcha_fail']}",
                            flush=True
                        )
                return

            except Exception:
                await asyncio.sleep(2 ** attempt)

    counters["fail"] += 1


# ── Main run ──────────────────────────────────────────────────────────────────

async def run(workers: int, wait: bool):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    DONE_TXT.parent.mkdir(parents=True, exist_ok=True)

    index = load_index()
    done  = load_done()
    todo  = [r for r in index if r["file_id"] not in done]
    print(f"Total: {len(index):,}  Done: {len(done):,}  Todo: {len(todo):,}", flush=True)
    if not todo:
        print("All done!")
        return

    cap_hdrs = {"User-Agent": UA, "Referer": "https://public.sud.uz/",
                "Origin": "https://public.sud.uz", "Content-Type": "application/json"}
    dl_hdrs  = {"User-Agent": UA, "Referer": "https://public.sud.uz/report/CIVIL",
                "Accept": "application/pdf,*/*,application/json"}

    async with httpx.AsyncClient(
        headers=cap_hdrs, verify=False,
        limits=httpx.Limits(max_connections=workers + 10),
    ) as client_cap:

        if wait:
            print("Waiting for recaptcha.sud.uz...", flush=True)
            while not await captcha_alive(client_cap):
                print(f"  still down {time.strftime('%H:%M:%S')} — retry in 60s", flush=True)
                await asyncio.sleep(60)
            print("recaptcha.sud.uz is UP → starting downloads", flush=True)
        else:
            if not await captcha_alive(client_cap):
                print("ERROR: recaptcha.sud.uz is unreachable. Use --wait to poll.", flush=True)
                return

        async with httpx.AsyncClient(
            headers=dl_hdrs, verify=False,
            limits=httpx.Limits(max_connections=workers + 20),
        ) as client_dl:

            sem     = asyncio.Semaphore(workers)
            writer  = TextWriter()
            tracker = DoneTracker()
            counters = {
                "done": 0, "fail": 0, "captcha_fail": 0, "token_reject": 0,
                "no_file": 0, "ocr_queued": 0, "parse_fail": 0,
                "_t0": time.time(), "_total": len(todo),
            }

            await asyncio.gather(*[
                process_one(client_dl, client_cap, sem, rec, writer, tracker, counters)
                for rec in todo
            ])

            await writer.flush_final()
            await tracker.flush_final()

    el = time.time() - counters["_t0"]
    print(
        f"\nDone: {counters['done']:,}  OCR queue: {counters['ocr_queued']:,}"
        f"  No file: {counters['no_file']:,}  Failed: {counters['fail']:,}"
        f"  Time: {el/3600:.1f}h  "
        f"  Text output: {TEXT_DIR}",
        flush=True
    )


# ── Status ────────────────────────────────────────────────────────────────────

def status():
    index = load_index()
    done  = load_done()
    ocr_q = sum(1 for _ in OCR_QUEUE.rglob("*.pdf")) if OCR_QUEUE.exists() else 0
    text_recs = sum(1 for _ in TEXT_DIR.rglob("*.jsonl.gz")) * TEXT_CHUNK if TEXT_DIR.exists() else 0
    print(f"Index:     {len(index):,} records")
    print(f"Done:      {len(done):,} ({100*len(done)/max(len(index),1):.1f}%)")
    print(f"OCR queue: {ocr_q:,} PDFs")
    print(f"Text out:  ~{text_recs:,} records in {TEXT_DIR}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="sud.uz PDF pipeline: download → text → JSONL")
    p.add_argument("--workers",     type=int,  default=WORKERS)
    p.add_argument("--wait",        action="store_true", default=True,
                   help="Poll until recaptcha.sud.uz recovers (default: on)")
    p.add_argument("--no-wait",     action="store_true",
                   help="Fail immediately if captcha server is down")
    p.add_argument("--build-index", action="store_true")
    p.add_argument("--status",      action="store_true")
    args = p.parse_args()

    if args.build_index:
        recs = build_index()
        save_index(recs)
        sys.exit(0)

    if args.status:
        status()
        sys.exit(0)

    wait = args.wait and not args.no_wait
    asyncio.run(run(args.workers, wait))
