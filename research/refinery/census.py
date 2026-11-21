"""Stage 00: walk the cache once, one row per file (kind, key, bytes, lex id, sign, edition date).

    python -X utf8 -m research.refinery.census [--out DIR]

Directory entries are only listed and stat-ed, never read, so a 120 GB cache takes minutes, not hours.
`img/` and the search folders are skipped (no text)."""

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from research.refinery import config
from research.refinery.io import write_jsonl

_DOC = re.compile(r"^(\d+)(?:_([pm]))?\.html$")
_EDITION = re.compile(r"^(\d{2}\.\d{2}\.\d{4})_(\d{2})\.html$")
_FILE = re.compile(r"^(-?\d+)\.(zip|pdf)$")


def _signed(abs_id: str, sign: str | None) -> str | None:
    return None if sign is None else (f"-{abs_id}" if sign == "m" else abs_id)


def parse_key(key: str) -> dict:
    """Kind, signed lex id (None when the cache name carries no sign), sign letter, edition date of a cache key.
    Sign convention: `_p` = id x, `_m` = id -x; legacy names without a suffix have an unknown sign."""
    parts = key.split("/")
    top = parts[0]
    base = parts[-1]
    out = {"kind": top, "lex_id": None, "sign": None, "ondate": None, "legacy": False, "abs_id": None}
    if top == "docs" and len(parts) == 2 and (m := _DOC.match(base)):
        out.update(kind="doc", sign=m[2], legacy=m[2] is None, lex_id=_signed(m[1], m[2]), abs_id=m[1])
    elif top == "editions" and len(parts) == 3:
        d = re.match(r"^(\d+)(?:_([pm]))?$", parts[1])
        e = _EDITION.match(base)
        if d and e:
            out.update(
                kind="edition",
                sign=d[2],
                legacy=d[2] is None,
                lex_id=_signed(d[1], d[2]),
                ondate=f"{e[1]} {e[2]}",
                abs_id=d[1],
            )
    elif top == "actinfo" and len(parts) == 3:
        m = _DOC.match(base)
        if m:
            out.update(
                kind=f"actinfo_{parts[1]}",
                sign=m[2],
                legacy=m[2] is None,
                lex_id=_signed(m[1], m[2]),
                abs_id=m[1],
            )
    elif top == "files" and (m := _FILE.match(base)):
        out.update(kind="file", abs_id=m[1].lstrip("-"))
    elif top == "pdfs":
        out["kind"] = "pdfs"
    return out


def walk_cache(root: Path = config.CACHE, tops=("docs", "editions", "actinfo", "files", "pdfs")):
    for top in tops:
        base = root / top
        if not base.exists():
            continue
        stack = [(base, top)]
        while stack:
            d, rel = stack.pop()
            try:
                with os.scandir(d) as it:
                    entries = sorted(it, key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                key = f"{rel}/{e.name}"
                if e.is_dir(follow_symlinks=False):
                    stack.append((Path(e.path), key))
                else:
                    try:
                        size = e.stat().st_size
                    except OSError:
                        continue
                    yield key, size


def run(out: Path) -> dict:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    rows, sizes, counts, zero = [], Counter(), Counter(), Counter()
    editions_per: Counter = Counter()
    for key, size in walk_cache():
        info = parse_key(key)
        counts[info["kind"]] += 1
        sizes[info["kind"]] += size
        if size == 0:
            zero[info["kind"]] += 1
        if info["kind"] == "edition":
            editions_per[key.split("/")[1]] += 1
        rows.append({"key": key, "bytes": size, **info})
    ocr = {}
    if config.OCR_DIR.exists():
        for d in sorted(os.scandir(config.OCR_DIR), key=lambda e: e.name):
            if d.is_dir():
                pages = [p for p in os.listdir(d.path) if p.endswith(".md")]
                ocr[d.name] = len(pages)
                rows.append(
                    {
                        "key": f"ocr/{d.name}",
                        "bytes": 0,
                        "kind": "ocr",
                        "lex_id": None,
                        "sign": None,
                        "ondate": None,
                        "legacy": False,
                        "abs_id": d.name,
                        "pages": len(pages),
                    }
                )
    hist = Counter(min(n, 10) for n in editions_per.values())
    summary = {
        "seconds": round(time.time() - t0, 1),
        "files": len(rows),
        "by_kind": dict(counts),
        "gigabytes_by_kind": {k: round(v / 1e9, 2) for k, v in sizes.items()},
        "zero_byte_by_kind": dict(zero),
        "acts_with_editions": len(editions_per),
        "editions_per_act_hist_cap10": dict(sorted(hist.items())),
        "ocr_documents": len(ocr),
        "ocr_pages": sum(ocr.values()),
    }
    write_jsonl(out / "census.jsonl.gz", rows)
    (out / "census_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.OUT / "00_census"))
    print(json.dumps(run(Path(ap.parse_args().out)), indent=1))
