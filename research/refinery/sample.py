"""Pilot sampling (design section 11): seeded, stratified from the census and the crawl catalog, never from the network.

Strata: national acts with >= 3 editions (incl. the core acts of the law store), local decisions in PDF (incl. suspected
template copies and the golden pairs), sensitive local decisions (land, housing, guardianship, social support),
OCR documents, Russian and English versions, edge cases. A twin (x and -x) of a chosen id joins it when it is cached."""

import os
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from research.refinery import config
from research.refinery.io import read_jsonl
from research.refinery.leak import load_core
from research.refinery.meta import act_type
from research.refinery.sources import Catalog, file_ids, read_cache, twin_of
from research.textnorm import fold

SENSITIVE = re.compile(
    r"yer uchastka|yer ajrat|uy joy|turar joy|vasiy|homiy|ijtimoiy|nogiron|moddiy yordam|"
    r"kam taminlangan|mulk egasi|boquvchisini|yetim|voyaga yetmagan|oilaviy"
)
QUOTA = {"national": 600, "local_pdf": 700, "sensitive": 200, "ocr": 200, "ru_en": 100, "edge": 200}


def census_index(path: Path):
    doc_bytes: dict[str, int] = {}
    editions: Counter = Counter()
    files: dict[str, int] = {}
    for r in read_jsonl(path):
        k = r["kind"]
        if k == "doc" and r["lex_id"] and r["bytes"] > 0:
            doc_bytes[r["lex_id"]] = r["bytes"]
        elif k == "edition" and r["lex_id"] and r["bytes"] > 0:
            editions[r["lex_id"]] += 1
        elif k == "file" and r["bytes"] > 0:
            files[r["abs_id"]] = r["bytes"]
    return doc_bytes, editions, files


def file_for_doc(lex_id: str, files: dict[str, int]) -> str | None:
    a = lex_id.lstrip("-")
    page = read_cache(f"docs/{a}_{'m' if lex_id.startswith('-') else 'p'}.html")
    if not page:
        return None
    for fid in file_ids(page):
        if fid in files:
            return fid
    return None


def select(census_path: Path, n_total: int = 2000, seed: int = config.SEED) -> list[dict]:
    rng = random.Random(seed)
    cat = Catalog()
    doc_bytes, editions, files = census_index(census_path)
    core = load_core()
    chosen: dict[str, dict] = {}
    counts: Counter = Counter()

    def add(lex_id: str, stratum: str, **kw) -> bool:
        if lex_id in chosen or lex_id not in doc_bytes:
            return False
        chosen[lex_id] = {"lex_id": lex_id, "kind": "html", "stratum": stratum, **kw}
        counts[stratum] += 1
        return True

    def add_pair(lex_id: str, stratum: str, **kw) -> int:
        n = int(add(lex_id, stratum, **kw))
        n += int(add(twin_of(lex_id), stratum, twin=True, **kw))
        return n

    rows = sorted(cat.rows.values(), key=lambda r: r["lex_id"])
    cls: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r["lex_id"] in doc_bytes:
            cls[r["lex_id"]] = act_type(r["badge"] or "", r["title"] or "", r["number"] or "")

    # 1. national acts, >= 3 editions; the law store's core acts first
    for lex_id in sorted(core.values()):
        if lex_id in doc_bytes:
            add_pair(lex_id, "national", core=True)
    pool = [
        r["lex_id"]
        for r in rows
        if r["lex_id"] in cls
        and cls[r["lex_id"]][1] == "national"
        and editions[r["lex_id"]] >= 3
        and r["lang"] in {"uz_latn", "uz_cyrl"}
    ]
    rng.shuffle(pool)
    for lex_id in pool:
        if counts["national"] >= QUOTA["national"]:
            break
        add_pair(lex_id, "national")

    # 2. local decisions as PDF (golden pairs first, then template-looking titles, then random)
    local = [
        r
        for r in rows
        if r["lex_id"] in cls and cls[r["lex_id"]][1] == "local" and r["lang"] in {"uz_latn", "uz_cyrl"}
    ]
    for gid in config.GOLDEN_IDS:
        for lid in (gid, twin_of(gid)):
            if lid in doc_bytes and (fid := file_for_doc(lid, files)):
                add(lid, "local_pdf", file_id=fid, golden=True)
    titles = Counter(fold(r["title"] or "") for r in local)
    template = [r["lex_id"] for r in local if titles[fold(r["title"] or "")] >= 3]
    rng.shuffle(template)
    n_template = 0
    for lex_id in template:
        if n_template >= 60 or counts["local_pdf"] >= QUOTA["local_pdf"]:
            break
        if (fid := file_for_doc(lex_id, files)) and add(lex_id, "local_pdf", file_id=fid, template=True):
            n_template += 1
    rest = [r["lex_id"] for r in local]
    rng.shuffle(rest)
    sens = [r["lex_id"] for r in local if SENSITIVE.search(fold(r["title"] or ""))]
    rng.shuffle(sens)
    for lex_id in sens:
        if counts["sensitive"] >= QUOTA["sensitive"]:
            break
        if fid := file_for_doc(lex_id, files):
            add(lex_id, "sensitive", file_id=fid)
    for lex_id in rest:
        if counts["local_pdf"] >= QUOTA["local_pdf"]:
            break
        if fid := file_for_doc(lex_id, files):
            add(lex_id, "local_pdf", file_id=fid)

    # 3. OCR documents: finished `<file>.md` in data/ocr
    ocr = sorted(
        p[:-3] for p in os.listdir(config.OCR_DIR) if p.endswith(".md") and p[:-3].split("__")[0].isdigit()
    )
    rng.shuffle(ocr)
    for key in ocr[: QUOTA["ocr"]]:
        chosen[f"ocr:{key}"] = {"lex_id": f"ocr:{key}", "kind": "ocr", "stratum": "ocr", "key": key}
        counts["ocr"] += 1

    # 4. Russian and English versions
    ru_en = [r["lex_id"] for r in rows if r["lex_id"] in doc_bytes and r["lang"] in {"ru", "en"}]
    rng.shuffle(ru_en)
    for lex_id in ru_en:
        if counts["ru_en"] >= QUOTA["ru_en"]:
            break
        add(lex_id, "ru_en")

    # 5. edge cases: not yet in force, tiny and huge pages, no lx_elem, pending-amendment banner
    nyf = [r["lex_id"] for r in rows if r["status"] == "n" and r["lex_id"] in doc_bytes]
    rng.shuffle(nyf)
    for lex_id in nyf[:50]:
        add(lex_id, "edge", edge="not_yet_in_force")
    sizes = sorted(doc_bytes.items(), key=lambda kv: (kv[1], kv[0]))
    for lex_id, _ in sizes[:5000][::125][:40]:
        add(lex_id, "edge", edge="tiny")
    for lex_id, _ in sizes[-40:]:
        add(lex_id, "edge", edge="huge")
    scan = [lid for lid in doc_bytes if lid in cls]
    rng.shuffle(scan)
    n_zero = n_banner = 0
    for lid in scan[:6000]:
        if n_zero >= 35 and n_banner >= 35:
            break
        page = read_cache(f"docs/{lid.lstrip('-')}_{'m' if lid.startswith('-') else 'p'}.html")
        if not page:
            continue
        if "lx_elem" not in page and "/uz/files/" not in page and n_zero < 35:
            n_zero += int(add(lid, "edge", edge="zero_units"))
        elif "kiritilmoqda" in page.lower() and n_banner < 35:
            n_banner += int(add(lid, "edge", edge="provisional_banner"))

    out = sorted(chosen.values(), key=lambda t: t["lex_id"])
    # trim to n_total, never dropping golden or core entries
    if len(out) > n_total:
        keep = [t for t in out if t.get("golden") or t.get("core")]
        others = [t for t in out if not (t.get("golden") or t.get("core"))]
        rng.shuffle(others)
        out = sorted(keep + others[: max(n_total - len(keep), 0)], key=lambda t: t["lex_id"])
    for t in out:
        t["pop"] = {"level": cls.get(t["lex_id"], ("", ""))[1], "type": cls.get(t["lex_id"], ("", ""))[0]}
    return out


def population(census_path: Path) -> dict:
    """Population counts from catalog and census for the extrapolation (by level and language)."""
    cat = Catalog()
    doc_bytes, _, _ = census_index(census_path)
    pop: dict[str, Counter] = defaultdict(Counter)
    for r in cat.rows.values():
        if r["lex_id"] in doc_bytes:
            lvl = act_type(r["badge"] or "", r["title"] or "", r["number"] or "")[1]
            pop[lvl][r["lang"]] += 1
    return {k: dict(v) for k, v in pop.items()}
