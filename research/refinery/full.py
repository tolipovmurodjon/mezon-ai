"""Full-corpus refinery run in batches (memory-safe, resumable). Same stages and decisions as `pilot.py`, but split so
that no step ever holds the whole corpus:

    P1  extract      per batch   01_extract/ + word counts for the OCR dictionary
    G1  vocabulary   global      merges the word counts (count >= 5 in >= 3 documents)
    P2  normalise    per batch   03_norm/, OCR letter restoration, MinHash signatures, exact hashes, clause hashes
    G2  global       global      twins, families, exact groups, near-duplicate clusters (signatures only),
                                 boilerplate clauses, capitalised-token frequencies, eval flags, golden families
    P3  train        per batch   filters, citizen masking, leak control, export of the training shards

Global steps read only light per-document rows (a few KB each), never texts, so a batch can be any size and the
result is the same for any batching (tests/test_refinery.py checks this). Every phase of every batch writes a
`_DONE` marker last; a re-run skips finished work and removes the half-written files of an interrupted batch.

    nice -n 19 python -X utf8 -m research.refinery.full run --out data/refinery/full --batch-size 10000 --workers 4
    python -X utf8 -m research.refinery.full run --ids FILE      # restrict to the lex ids of a JSONL (kind=html rows)
    python -X utf8 -m research.refinery.full report --out data/refinery/full

Documents whose PDF is scanned and whose OCR is not finished yet are written to `ocr_pending.jsonl` and dropped as
`ocr_pending`; once their OCR exists, delete the `_DONE` markers of the batch that holds them and run again."""

import argparse
import base64
import gzip
import hashlib
import json
import multiprocessing as mp
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np

from research.mezonbench import unseen
from research.refinery import config, dedup, export, extract, extract_ocr, filters, leak, pii
from research.refinery.io import read_jsonl
from research.refinery.normalize import detect_lang, normalise, script_counts
from research.refinery.pilot import UnionFind, _body
from research.refinery.sample import SENSITIVE
from research.refinery.sources import Catalog, twin_of
from research.textnorm import fold

BATCH_DOCS = 10_000
WINDOW = 192  # documents handed to the worker pool at once (bounds the memory of a batch)
ROWS_PER_PART = {
    "cpt_docs": 5000,
    "cpt_original_edition": 5000,
    "amendment_docs": 20000,
    "status_docs": 20000,
    "lesson_inputs": 50000,
}
_EXPECT_SCRIPT = {"uz_latn": "Latn", "uz_cyrl": "Cyrl", "ru": "Cyrl", "en": "Latn"}
_WORD = re.compile(r"[^\W\d_]{2,}")

# globals shared with the forked workers (read-only)
VOCAB: set[str] = set()
DF: "CommonCaps | None" = None
NET: leak.LeakNet | None = None
FLAGS: dict[str, dict] = {}
CORE_REV: dict[str, str] = {}


# ------------------------------------------------------------------ small io helpers


class Rotating:
    """Deterministic gzip JSONL writer that starts a new part file after `n` rows: <dir>/<prefix>-<part>.jsonl.gz."""

    def __init__(self, dirpath: Path, prefix: str, n: int = 5000):
        self.dir, self.prefix, self.n = Path(dirpath), prefix, n
        self.dir.mkdir(parents=True, exist_ok=True)
        self.part = -1
        self.rows = 0
        self.total = 0
        self._raw = None
        self._gz = None
        self.files: list[Path] = []

    def _open(self) -> None:
        self.close_file()
        self.part += 1
        p = self.dir / f"{self.prefix}-{self.part:03d}.jsonl.gz"
        self._raw = open(p, "wb")  # noqa: SIM115
        self._gz = gzip.GzipFile(filename="", mode="wb", fileobj=self._raw, mtime=0)
        self.files.append(p)
        self.rows = 0

    def write(self, row: dict) -> None:
        if self._gz is None or self.rows >= self.n:
            self._open()
        self._gz.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        self.rows += 1
        self.total += 1

    def close_file(self) -> None:
        if self._gz is not None:
            self._gz.close()
            self._raw.close()
            self._gz = self._raw = None

    def close(self) -> int:
        if self.part == -1:
            self._open()
        self.close_file()
        return self.total


def _done(root: Path, phase: str, b: str) -> bool:
    return (root / "markers" / f"{phase}_{b}._DONE").exists()


def _mark(root: Path, phase: str, b: str) -> None:
    (root / "markers").mkdir(exist_ok=True)
    (root / "markers" / f"{phase}_{b}._DONE").write_text("ok")


def _read_all(path: Path) -> Iterator[dict]:
    yield from read_jsonl(path)


def _bname(i: int) -> str:
    return f"b{i:03d}"


def _clean_prefix(root: Path, sub: str, b: str) -> None:
    d = root / sub
    if d.exists():
        for p in d.glob(f"{b}-*"):
            p.unlink()
        for p in d.glob(f"{b}.*"):
            p.unlink()


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ batches


def make_tasks(ids: Iterable[str] | None = None) -> list[dict]:
    cat = Catalog()
    lids = sorted(ids if ids is not None else cat.rows, key=lambda x: (int(x.lstrip("-")), x.startswith("-")))
    return [{"lex_id": lid, "kind": "html", "stratum": "full"} for lid in lids]


def make_batches(tasks: list[dict], size: int) -> list[list[dict]]:
    """Consecutive tasks, cut only between different absolute ids, so that x and -x (the twins) share a batch."""
    out, cur = [], []
    for t in tasks:
        if len(cur) >= size and t["lex_id"].lstrip("-") != cur[-1]["lex_id"].lstrip("-"):
            out.append(cur)
            cur = []
        cur.append(t)
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ P1 extract


def _vocab_counts(texts: Iterable[str]) -> dict[str, list[int]]:
    cnt: Counter = Counter()
    dfc: Counter = Counter()
    for t in texts:
        w = [x.lower() for x in _WORD.findall(t)]
        cnt.update(w)
        dfc.update(set(w))
    return {w: [c, dfc[w]] for w, c in cnt.items()}


def phase1(root: Path, b: str, tasks: list[dict], workers: int) -> dict:
    t0 = time.time()
    d = root / "01_extract"
    d.mkdir(parents=True, exist_ok=True)
    acts = Rotating(d / "acts", b, 10**9)
    unitv = Rotating(d / "unit_versions", b, 10**9)
    errors: Counter = Counter()
    kinds: Counter = Counter()
    pending = []
    counts: Counter = Counter()
    dfc: Counter = Counter()
    n_ok = n_units = 0
    ctx = mp.get_context("fork")
    with ctx.Pool(workers) as pool:
        for rec in pool.imap(extract.extract_task, tasks, chunksize=4):
            if rec.get("error"):
                errors[rec["error"]] += 1
                continue
            rows = rec.pop("unit_rows", [])
            if rec.get("scanned") and "ocr" not in rec:
                rec["ocr_pending"] = True
                pending.append({"lex_id": rec["lex_id"]})
            acts.write(rec)
            for u in rows:
                unitv.write({"lex_id": rec["lex_id"], **u})
            n_ok += 1
            n_units += len(rows)
            kinds[rec["source_kind"]] += 1
            if (rec["source_kind"] == "html" and rec["meta"]["level"] == "national") or rec[
                "source_kind"
            ] == "pdf_text":
                w = [x.lower() for x in _WORD.findall(_body(rec["blocks"]))]
                counts.update(w)
                dfc.update(set(w))
    acts.close()
    unitv.close()
    (root / "vocab").mkdir(exist_ok=True)
    with gzip.open(root / "vocab" / f"{b}.tsv.gz", "wt", encoding="utf-8") as f:
        for w in sorted(counts):
            f.write(f"{w}\t{counts[w]}\t{dfc[w]}\n")
    if pending:
        with open(root / "ocr_pending.jsonl", "a", encoding="utf-8") as f:
            for p in pending:
                f.write(json.dumps({"batch": b, **p}) + "\n")
    st = {
        "tasks": len(tasks),
        "ok": n_ok,
        "errors": dict(errors),
        "source_kinds": dict(kinds),
        "unit_rows": n_units,
        "ocr_pending": len(pending),
        "seconds": round(time.time() - t0, 1),
    }
    (root / "stats").mkdir(exist_ok=True)
    (root / "stats" / f"{b}_p1.json").write_text(json.dumps(st), encoding="utf-8")
    _mark(root, "p1", b)
    return st


# ------------------------------------------------------------------ G1 vocabulary


def global_vocab(root: Path) -> int:
    cnt: Counter = Counter()
    dfc: Counter = Counter()
    for f in sorted((root / "vocab").glob("b*.tsv.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                w, c, n = line.rstrip("\n").split("\t")
                cnt[w] += int(c)
                dfc[w] += int(n)
    vocab = sorted(w for w, c in cnt.items() if c >= 5 and dfc[w] >= 3)
    with gzip.open(root / "global" / "vocab.txt.gz", "wt", encoding="utf-8") as f:
        f.write("\n".join(vocab))
    return len(vocab)


def load_vocab(root: Path) -> set[str]:
    with gzip.open(root / "global" / "vocab.txt.gz", "rt", encoding="utf-8") as f:
        return set(f.read().split("\n"))


# ------------------------------------------------------------------ P2 normalise


_CAP = re.compile(pii.CAP)
_MH = None


def _hasher() -> dedup.MinHasher:
    global _MH
    if _MH is None:
        _MH = dedup.MinHasher()
    return _MH


def norm_doc(r: dict) -> dict:
    """Stage 02/03 for one extraction record: OCR letters, normalisation, language, hashes. Pure function."""
    m = r["meta"]
    ocr_fixed = 0
    if r["source_kind"] == "ocr":
        for blk in r["blocks"]:
            blk["text"], n = extract_ocr.ocr_correct(blk["text"], VOCAB)
            ocr_fixed += n
    raw = _body(r["blocks"])
    d = detect_lang(raw)
    lat, cyr = script_counts(raw)
    norm_blocks, mixed_fixed = [], 0
    for b in r["blocks"]:
        t, st = normalise(b["text"], latin=lat >= cyr)
        mixed_fixed += st["homoglyph_fixed"]
        norm_blocks.append({**{k: b[k] for k in ("kind", "path", "art")}, "text": t})
    norm_blocks = [b for b in norm_blocks if b["text"]]
    text = _body(norm_blocks)
    ls = f"{d['lang']}-{d['script']}"
    folded = fold(text)
    sig = _hasher().signature_np(dedup.shingle_set(text))
    clauses = []
    if m["level"] == "local":
        for b in norm_blocks:
            if (
                b["path"]
                and b["path"].startswith("cl:")
                and len(b["text"].split()) >= config.BOILERPLATE_MIN_WORDS
            ):
                clauses.append([hashlib.sha1(fold(b["text"]).encode()).hexdigest()[:12], b["path"]])
    caps = sorted(set(_CAP.findall(text))) if (m["level"] == "local" or r["source_kind"] == "ocr") else []
    index = {
        "lex_id": r["lex_id"],
        "abs_id": m["abs_id"],
        "number": m.get("number"),
        "adopted": m.get("adopted"),
        "level": m["level"],
        "act_type": m["act_type"],
        "reg_number": m.get("reg_number"),
        "ls": ls,
        "lang": d["lang"],
        "script": d["script"],
        "stratum": f"{m['act_type']}|{(m.get('adopted') or '0000')[:4]}|{ls}",
        "hash": hashlib.sha1(folded.encode()).hexdigest(),
        "sig": base64.b64encode(sig.astype("<u8").tobytes()).decode(),
        "source_kind": r["source_kind"],
        "n_chars": len(text),
        "golden": leak.golden_flag(r["lex_id"], m.get("reg_number")),
        "time_cut": (m.get("adopted") or "") >= config.TIME_CUT,
    }
    return {
        "norm": {"lex_id": r["lex_id"], "lang": d, "blocks": norm_blocks, "homoglyph_fixed": mixed_fixed},
        "index": index,
        "clauses": clauses,
        "caps": caps,
        "twin": (folded[:3000] + " " + folded[-3000:]) if text else "",
        "ocr_fixed": ocr_fixed,
    }


def phase2(root: Path, b: str, workers: int) -> dict:
    t0 = time.time()
    norm = Rotating(root / "03_norm", b, 10**9)
    index = Rotating(root / "index", b, 10**9)
    clause_w = Rotating(root / "clauses", b, 10**9)
    twins_w = Rotating(root / "twins", b, 10**9)
    caps_df: Counter = Counter()
    samples: dict[str, str] = {}
    ocr_fixed = homog = n = 0
    recs = _read_all(root / "01_extract" / "acts" / f"{b}-000.jsonl.gz")
    ctx = mp.get_context("fork")
    with ctx.Pool(workers) as pool:
        while True:
            window = [r for _, r in zip(range(WINDOW), recs, strict=False)]
            if not window:
                break
            for out in pool.map(norm_doc, window, chunksize=4):
                norm.write(out["norm"])
                index.write(out["index"])
                if out["clauses"]:
                    clause_w.write({"lex_id": out["index"]["lex_id"], "h": out["clauses"]})
                caps_df.update(out["caps"])
                samples[out["index"]["lex_id"]] = out["twin"]
                ocr_fixed += out["ocr_fixed"]
                homog += out["norm"]["homoglyph_fixed"]
                n += 1
    for lid in sorted(samples):
        o = twin_of(lid)
        if lid.startswith("-") and o in samples:
            verdict, sim = dedup.twin_from_samples(samples[lid], samples[o])
            twins_w.write({"lex_id": lid, "twin_id": o, "sim": sim, "verdict": verdict})
    for w in (norm, index, clause_w, twins_w):
        w.close()
    (root / "df").mkdir(exist_ok=True)
    with gzip.open(root / "df" / f"{b}.tsv.gz", "wt", encoding="utf-8") as f:
        for w in sorted(caps_df):
            f.write(f"{w}\t{caps_df[w]}\n")
    st = {
        "docs": n,
        "ocr_words_corrected": ocr_fixed,
        "homoglyph_fixed_words": homog,
        "seconds": round(time.time() - t0, 1),
    }
    (root / "stats" / f"{b}_p2.json").write_text(json.dumps(st), encoding="utf-8")
    _mark(root, "p2", b)
    return st


# ------------------------------------------------------------------ G2 global


class CommonCaps:
    """Stands in for the capitalised-token document-frequency Counter: only 'is it seen in 30 or more documents'
    matters to the masker (rare surnames), so only the common tokens are stored."""

    def __init__(self, common: set[str]):
        self.common = common

    def get(self, key: str, default: int = 0) -> int:
        return 30 if key in self.common else default


def _decode_sig(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype="<u8")


def global_step(root: Path, batches: list[str]) -> dict:
    t0 = time.time()
    g = root / "global"
    g.mkdir(parents=True, exist_ok=True)
    idx: dict[str, dict] = {}
    for b in batches:
        for r in _read_all(root / "index" / f"{b}-000.jsonl.gz"):
            idx[r["lex_id"]] = r
    # --- twins and families
    uf = UnionFind()
    twin_of_id: dict[str, str] = {}
    verdicts: Counter = Counter()
    n_pairs = 0
    for b in batches:
        for t in _read_all(root / "twins" / f"{b}-000.jsonl.gz"):
            n_pairs += 1
            verdicts[t["verdict"]] += 1
            if t["verdict"] == "twin":
                twin_of_id[t["lex_id"]], twin_of_id[t["twin_id"]] = t["twin_id"], t["lex_id"]
                uf.union(t["lex_id"], t["twin_id"])
    for lid, r in sorted(idx.items()):
        if r["number"] and r["adopted"]:
            uf.union(lid, "k:" + f"{r['number']}|{r['adopted']}|{r['level']}".lower())
    members: dict[str, list[int]] = defaultdict(list)
    for lid in idx:
        members[uf.find(lid)].append(idx[lid]["abs_id"])
    family = {lid: min(members[uf.find(lid)]) for lid in idx}
    # --- exact duplicates (inside one language-script)
    by_hash: dict[str, list[str]] = defaultdict(list)
    for lid in sorted(idx):
        by_hash[f"{idx[lid]['ls']}:{idx[lid]['hash']}"].append(lid)
    ex_groups = {h: m for h, m in by_hash.items() if len(m) > 1}
    exact_drop = {other: min(m) for m in ex_groups.values() for other in sorted(m)[1:]}
    # --- near duplicates from signatures
    items = [
        {"id": lid, "stratum": r["stratum"], "sig": _decode_sig(r["sig"]), "adopted": r["adopted"]}
        for lid, r in sorted(idx.items())
        if lid not in exact_drop
    ]
    clusters = dedup.cluster_signatures(items)
    del items
    cl_by_id = {c["id"]: c for c in clusters}
    # --- eval flags (same order as the pilot)
    bench, core = leak.load_bench(), leak.load_core()
    net = leak.build_net(bench, core, unseen)
    ev = {lid: r["golden"] for lid, r in idx.items()}
    golden_fams = {family[lid] for lid, f in ev.items() if f != "none"}
    cluster_gold = {c["cluster"] for c in clusters if ev[c["id"]] in {"golden", "cancelling_act"}}
    for lid, r in idx.items():
        if ev[lid] == "none" and family[lid] in golden_fams:
            ev[lid] = "golden"
        if ev[lid] == "none" and lid in cl_by_id and cl_by_id[lid]["cluster"] in cluster_gold:
            ev[lid] = "golden"
        if ev[lid] == "none" and r["time_cut"]:
            ev[lid] = "time_cut"
        if ev[lid] == "none" and str(r["abs_id"]) in net.blocklist:
            ev[lid] = "bench_family"
    # --- boilerplate clauses (local decisions)
    count: Counter = Counter()
    for b in batches:
        for r in _read_all(root / "clauses" / f"{b}-000.jsonl.gz"):
            count.update({h for h, _ in r["h"]})
    common = {h for h, c in count.items() if c > config.BOILERPLATE_DF}
    del count
    occ: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for b in batches:
        for r in _read_all(root / "clauses" / f"{b}-000.jsonl.gz"):
            for h, p in r["h"]:
                if h in common:
                    occ[h].append((r["lex_id"], p))
    boiler: dict[str, list[str]] = defaultdict(list)
    for h, o in occ.items():
        keep_docs = sorted({d for d, _ in o})[:3]
        for d, p in o:
            if d not in keep_docs:
                boiler[d].append(p)
    # --- capitalised-token frequencies
    df: Counter = Counter()
    for b in batches:
        with gzip.open(root / "df" / f"{b}.tsv.gz", "rt", encoding="utf-8") as fh:
            for line in fh:
                w, c = line.rstrip("\n").split("\t")
                df[w] += int(c)
    caps_common = sorted(w for w, c in df.items() if c >= 30)
    n_caps = len(df)
    del df
    with gzip.open(g / "caps_common.txt.gz", "wt", encoding="utf-8") as f:
        f.write("\n".join(caps_common))
    with open(g / "flags.jsonl.gz", "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            for lid in sorted(idx):
                c = cl_by_id.get(lid)
                row = {
                    "lex_id": lid,
                    "family_id": family[lid],
                    "twin_id": twin_of_id.get(lid),
                    "exact_drop": exact_drop.get(lid),
                    "cluster": c["cluster"] if c else None,
                    "keep": c["keep"] if c else True,
                    "dup_count": c["dup_count"] if c else 1,
                    "eval_flag": ev[lid],
                    "boiler": sorted(boiler.get(lid, [])),
                }
                gz.write((json.dumps(row, sort_keys=True) + "\n").encode())
    for name, rows in (
        ("exact", [{"group": h, "members": m} for h, m in sorted(ex_groups.items())]),
        ("minhash_clusters", clusters),
    ):
        with (
            open(g / f"{name}.jsonl.gz", "wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz,
        ):
            for r in rows:
                gz.write((json.dumps(r, sort_keys=True) + "\n").encode())
    st = {
        "docs": len(idx),
        "twin_pairs": n_pairs,
        "twin_verdicts": dict(verdicts),
        "families": len(set(family.values())),
        "exact_groups": len(ex_groups),
        "exact_dropped": len(exact_drop),
        "clusters": len({c["cluster"] for c in clusters}),
        "cluster_members": len(clusters),
        "cluster_dropped": sum(1 for c in clusters if not c["keep"]),
        "boilerplate_clause_hashes": len(common),
        "boilerplate_clauses_dropped": sum(len(v) for v in boiler.values()),
        "capitalised_tokens": n_caps,
        "capitalised_common": len(caps_common),
        "eval_flags": dict(Counter(ev.values())),
        "seconds": round(time.time() - t0, 1),
    }
    (g / "stats.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
    (g / "_DONE").write_text("ok")
    return st


# ------------------------------------------------------------------ P3 train


def train_doc(item: tuple) -> dict:
    """Stages 07-10 for one document (port of the pilot's per-document code)."""
    r, nd, unit_rows = item
    lid = r["lex_id"]
    m = r["meta"]
    fl = FLAGS[lid]
    d_lang = nd["lang"]
    blocks = nd["blocks"]
    text = _body(blocks)
    out: dict = {"lex_id": lid, "cpt": [], "a0": [], "amend": [], "status": [], "lessons": [], "held": None}
    expected = _EXPECT_SCRIPT.get(m.get("catalog_lang", ""))
    # ---- filters
    sig = filters.signals(
        text,
        r["source_kind"],
        {"script": expected} if expected else None,
        d_lang,
        VOCAB,
        r.get("n_table_chars", 0),
        r.get("table_numeric_share", 0.0),
    )
    decision, reason = filters.decide(sig, r["source_kind"], bool(r.get("ocr_partial")))
    if r.get("ocr_pending"):
        decision, reason = "drop", "ocr_pending"
    flags_ = filters.flags(sig)
    tier = filters.tier(r["source_kind"], m["level"], flags_)
    out["sig_row"] = {
        "lex_id": lid,
        "source_kind": r["source_kind"],
        **sig,
        "decision": decision,
        "reason": reason,
        "flags": flags_,
        "tier": tier,
    }
    # ---- masking
    lvl = "national" if (m["level"] == "national" and r["source_kind"] != "ocr") else "local"
    names: dict[str, int] = {}
    sens = bool(SENSITIVE.search(fold(m.get("title", ""))))
    counts: Counter = Counter()
    new_blocks = []
    for blk in blocks:
        t, c = pii.mask(blk["text"], lvl, DF, names=names, sensitive=sens)
        counts.update(c)
        new_blocks.append({**blk, "text": t})
    masked = "\n".join(b["text"] for b in new_blocks)
    sp = pii.second_pass(masked, lvl, m.get("title", ""), DF)
    counts = dict(counts)
    out["pii_row"] = {
        "lex_id": lid,
        "level": lvl,
        "counts": counts,
        "guardianship": sp["guardianship"],
        "residual_after_second_pass": sp["residual"],
        "exclude": sp["exclude"],
    }
    out["pii_counts"] = counts
    out["pii_contexts"] = pii.context_samples("", masked, 2) if lvl == "local" and counts else []
    # ---- leak control
    res = leak.clean_blocks(new_blocks, NET, str(m["abs_id"]))
    blocks = res["blocks"]
    out["leak_row"] = {
        "lex_id": lid,
        "removed_units": res["removed_units"],
        "removed_sentences": res["removed_sentences"],
        "events": res["events"][:50],
    }
    out["leak_events"] = Counter(e["type"] for e in res["events"])
    out["leak_totals"] = {
        "removed_units": res["removed_units"],
        "removed_sentences": res["removed_sentences"],
    }
    # ---- decision
    why = None
    if fl["exact_drop"]:
        why = "exact_duplicate"
    elif decision == "drop":
        why = reason
    elif fl["cluster"] and not fl["keep"]:
        why = "near_duplicate"
    elif sp["exclude"]:
        why = "pii_guardianship"
    elif fl["eval_flag"] in {"golden", "cancelling_act", "time_cut"}:
        out["held"] = {
            "lex_id": lid,
            "abs_id": m["abs_id"],
            "eval_flag": fl["eval_flag"],
            "reg_number": m.get("reg_number"),
            "sha1_raw": r.get("sha1_raw"),
        }
        out["drop"] = "held_out_" + fl["eval_flag"]
        return out
    if why:
        out["drop"] = why
        out["drop_sample"] = {"lex_id": lid, "reason": why, "n_chars": sig["n_chars"]}
        return out
    out["drop"] = None
    tag = (d_lang["lang"], d_lang["script"])
    status_key = "provisional" if m.get("provisional") else m["status"]
    eds = r.get("editions") or []
    v_from = eds[-1]["valid_from"] if eds else m.get("adopted")
    hdr = export.header(m, *tag, v_from, None, status_key)
    drop_units = set(fl["boiler"])
    kept_blocks = [b for b in blocks if b["path"] not in drop_units]
    dup = fl["dup_count"]
    for ch in export.chunk_by_article(kept_blocks, hdr):
        out["cpt"].append(
            {
                "doc_id": f"{lid}:{ch['chunk']}",
                "lex_id": lid,
                "family_id": fl["family_id"],
                "twin_id": fl["twin_id"],
                "lang": tag[0],
                "script": tag[1],
                "act_type": m["act_type"],
                "level": m["level"],
                "number": m.get("number"),
                "adopted": m.get("adopted"),
                "valid_from": v_from,
                "valid_to": None,
                "status": m["status"],
                "tier": tier,
                "source_kind": r["source_kind"],
                "source_url": m["source_url"],
                "dup_count": dup,
                "pii": counts,
                "eval_flag": fl["eval_flag"],
                "header_chars": ch["header_chars"],
                "text": ch["text"],
                "n_chars": len(ch["text"]),
                "n_words": ch["n_words"],
            }
        )
    latest_text = _body(blocks)
    orig = r.get("original")
    if orig and (orig["valid_from"] or "") < config.TIME_CUT:
        ob = [{**b, "text": normalise(b["text"], latin=tag[1] == "Latn")[0]} for b in orig["blocks"]]
        ob = [b for b in ob if b["text"]]
        ob = leak.clean_blocks(ob, NET, str(m["abs_id"]))["blocks"]
        differs, sim = export.original_differs(latest_text, _body(ob))
        if differs and ob:
            ohdr = export.header(m, *tag, orig["valid_from"], orig["valid_to"], "original")
            for ch in export.chunk_by_article(ob, ohdr):
                out["a0"].append(
                    {
                        "doc_id": f"{lid}:orig:{ch['chunk']}",
                        "lex_id": lid,
                        "family_id": fl["family_id"],
                        "tier": "A0",
                        "similarity_to_latest": sim,
                        "act_type": m["act_type"],
                        "lang": tag[0],
                        "script": tag[1],
                        "valid_from": orig["valid_from"],
                        "valid_to": orig["valid_to"],
                        "text": ch["text"],
                        "n_words": ch["n_words"],
                        "eval_flag": fl["eval_flag"],
                    }
                )
    if r["source_kind"] == "html":
        block_paths = NET.blocklist.get(str(m["abs_id"]), set())
        rows = [
            u
            for u in unit_rows
            if not leak.blocked(NET, str(m["abs_id"]), u["path"], u["path"].split("/part:")[0])
        ]
        for a in export.amendment_docs(m, rows, *tag):
            cleaned = leak.clean_blocks(
                [{"kind": "text", "text": ln, "path": None, "art": None} for ln in a["text"].split("\n")],
                NET,
                "none",
                protected_kinds=(),
            )
            txt = "\n".join(b["text"] for b in cleaned["blocks"])
            if txt.count("\n") >= 1:
                out["amend"].append(
                    {
                        "doc_id": f"{lid}:chg:{a['date']}:{a['part']}",
                        "lex_id": lid,
                        "family_id": fl["family_id"],
                        "tier": "B",
                        "act_type": m["act_type"],
                        "lang": tag[0],
                        "script": tag[1],
                        "date": a["date"],
                        "text": txt,
                        "n_words": len(txt.split()),
                        "eval_flag": fl["eval_flag"],
                    }
                )
        sd = export.status_doc(m, *tag)
        if sd:
            out["status"].append(
                {
                    "doc_id": f"{lid}:status",
                    "lex_id": lid,
                    "tier": "B",
                    "lang": tag[0],
                    "script": tag[1],
                    **sd,
                    "eval_flag": fl["eval_flag"],
                }
            )
        li = export.lesson_inputs(m, rows, CORE_REV.get(lid) or lid, block_paths)
        out["lessons"] = [x for x in li if not leak.scan_segments([x["text"]], NET)[0]]
    elif r["source_kind"] in {"pdf_text", "ocr"}:
        units = [
            {
                "act_key": lid,
                "path": b["path"],
                "heading": "",
                "text": b["text"],
                "valid_from": m.get("adopted"),
                "valid_to": None,
                "act_type": m["act_type"],
                "type": export.LESSON_TYPE.get(m["act_type"], "other"),
                "title": m.get("title", ""),
                "number": m.get("number", ""),
                "prev_text": None,
                "lex_id": lid,
            }
            for b in kept_blocks
            if b["path"]
            and b["path"].startswith(("cl:", "annex:"))
            and len(b["text"]) >= 80
            and (m.get("adopted") or "") < config.TIME_CUT
        ]
        out["lessons"] = [x for x in units if not leak.scan_segments([x["text"]], NET)[0]]
    return out


def _group_units(path: Path) -> Iterator[tuple[str, list[dict]]]:
    cur, rows = None, []
    for u in _read_all(path):
        lid = u.pop("lex_id")
        if lid != cur and cur is not None:
            yield cur, rows
            rows = []
        cur = lid
        rows.append(u)
    if cur is not None:
        yield cur, rows


def phase3(root: Path, b: str, workers: int) -> dict:
    t0 = time.time()
    writers = {name: Rotating(root / "07_train" / name, b, n) for name, n in ROWS_PER_PART.items()}
    sig_w = Rotating(root / "05_filter", b, 10**9)
    pii_w = Rotating(root / "06_safe" / "pii_report", b, 10**9)
    leak_w = Rotating(root / "06_safe" / "leak_report", b, 10**9)
    held_w = Rotating(root / "07_train" / "held_out", b, 10**9)
    drop_w = Rotating(root / "07_train" / "drop_samples", b, 10**9)
    tot: dict[str, Counter] = defaultdict(Counter)
    contexts: list[str] = []
    n_drop_samples = 0
    acts = _read_all(root / "01_extract" / "acts" / f"{b}-000.jsonl.gz")
    norms = _read_all(root / "03_norm" / f"{b}-000.jsonl.gz")
    unitg = _group_units(root / "01_extract" / "unit_versions" / f"{b}-000.jsonl.gz")
    pend_u = next(unitg, None)

    def stream() -> Iterator[tuple]:
        nonlocal pend_u
        for r in acts:
            nd = next(norms)
            assert nd["lex_id"] == r["lex_id"], (nd["lex_id"], r["lex_id"])
            rows = []
            while pend_u is not None and pend_u[0] != r["lex_id"] and _before(pend_u[0], r["lex_id"]):
                pend_u = next(unitg, None)
            if pend_u is not None and pend_u[0] == r["lex_id"]:
                rows = pend_u[1]
                pend_u = next(unitg, None)
            yield r, nd, rows

    ctx = mp.get_context("fork")
    it = stream()
    n = 0
    with ctx.Pool(workers) as pool:
        while True:
            window = [x for _, x in zip(range(WINDOW), it, strict=False)]
            if not window:
                break
            for o in pool.map(train_doc, window, chunksize=2):
                n += 1
                sig_w.write(o["sig_row"])
                pii_w.write(o["pii_row"])
                leak_w.write(o["leak_row"])
                tot["docs"]["extracted"] += 1
                sr = o["sig_row"]
                tot["pii_totals"].update(o["pii_counts"])
                if o["pii_counts"]:
                    tot["docs_with_masks"][o["pii_row"]["level"]] += 1
                tot["leak_events"].update(o["leak_events"])
                tot["leak_totals"].update(o["leak_totals"])
                if len(contexts) < 150:
                    contexts.extend(o["pii_contexts"])
                if o["held"]:
                    held_w.write(o["held"])
                if o.get("drop_sample") and n_drop_samples < 60:
                    drop_w.write(o["drop_sample"])
                    n_drop_samples += 1
                tot["drops"][o["drop"] or "kept"] += 1
                for name, key in (
                    ("cpt_docs", "cpt"),
                    ("cpt_original_edition", "a0"),
                    ("amendment_docs", "amend"),
                    ("status_docs", "status"),
                    ("lesson_inputs", "lessons"),
                ):
                    for row in o[key]:
                        writers[name].write(row)
                for c in o["cpt"]:
                    k = f"{c['lang']}-{c['script']}"
                    tot["cpt_chunks"][k] += 1
                    tot["cpt_words"][k] += c["n_words"]
                    tot["cpt_chars"][k] += c["n_chars"]
                    tot["cpt_words_tier"][c["tier"]] += c["n_words"]
                    tot["cpt_words_type"][c["act_type"]] += c["n_words"]
                if o["cpt"]:
                    c0 = o["cpt"][0]
                    tot["kept_docs_type_script"][f"{c0['act_type']}|{c0['lang']}-{c0['script']}"] += 1
                    tot["kept_docs_script"][f"{c0['lang']}-{c0['script']}"] += 1
                    tot["kept_docs_type"][c0["act_type"]] += 1
                tot["a0_words"][f"{o['a0'][0]['lang']}-{o['a0'][0]['script']}" if o["a0"] else "none"] += sum(
                    x["n_words"] for x in o["a0"]
                )
                tot["amend_words"]["all"] += sum(x["n_words"] for x in o["amend"])
                tot["lesson_rows"]["all"] += len(o["lessons"])
                tot["source_kind"][sr["source_kind"]] += 1
    for w in (*writers.values(), sig_w, pii_w, leak_w, held_w, drop_w):
        w.close()
    (root / "06_safe").mkdir(exist_ok=True)
    (root / "06_safe" / f"{b}_pii_contexts.txt").write_text("\n".join(contexts), encoding="utf-8")
    st = {k: dict(v) for k, v in tot.items()}
    st["docs_processed"] = n
    st["files"] = {name: w.total for name, w in writers.items()}
    st["seconds"] = round(time.time() - t0, 1)
    (root / "stats" / f"{b}_p3.json").write_text(json.dumps(st), encoding="utf-8")
    _mark(root, "p3", b)
    return st


def _before(a: str, b: str) -> bool:
    ka = (int(a.lstrip("-")), a.startswith("-"))
    kb = (int(b.lstrip("-")), b.startswith("-"))
    return ka < kb


# ------------------------------------------------------------------ report


def merge_stats(root: Path, batches: list[str]) -> dict:
    tot: dict[str, Counter] = defaultdict(Counter)
    secs = Counter()
    for b in batches:
        p1 = json.loads((root / "stats" / f"{b}_p1.json").read_text())
        p2 = json.loads((root / "stats" / f"{b}_p2.json").read_text())
        p3 = json.loads((root / "stats" / f"{b}_p3.json").read_text())
        tot["p1"].update({k: v for k, v in p1.items() if isinstance(v, int)})
        tot["p1_errors"].update(p1["errors"])
        tot["p1_kinds"].update(p1["source_kinds"])
        tot["p2"].update({k: v for k, v in p2.items() if isinstance(v, int)})
        for k, v in p3.items():
            if isinstance(v, dict):
                tot[k].update(v)
        secs["p1"] += p1["seconds"]
        secs["p2"] += p2["seconds"]
        secs["p3"] += p3["seconds"]
    out = {k: dict(v) for k, v in tot.items()}
    out["seconds"] = dict(secs)
    out["global"] = json.loads((root / "global" / "stats.json").read_text())
    return out


# ------------------------------------------------------------------ driver


def run(a: argparse.Namespace) -> None:
    global VOCAB, DF, NET, FLAGS, CORE_REV
    root = Path(a.out)
    root.mkdir(parents=True, exist_ok=True)
    (root / "global").mkdir(exist_ok=True)
    (root / "stats").mkdir(exist_ok=True)
    ids = None
    if a.ids:
        ids = [r["lex_id"] for r in read_jsonl(Path(a.ids)) if r.get("kind", "html") == "html"]
    tasks = make_tasks(ids)
    batches = make_batches(tasks, a.batch_size)
    names = [_bname(i) for i in range(len(batches))]
    sel = range(len(batches))
    if a.only:
        lo, hi = (int(x) for x in a.only.split("-"))
        sel = range(lo, hi + 1)
    meta = {
        "n_tasks": len(tasks),
        "batches": len(batches),
        "batch_size": a.batch_size,
        "first_ids": [b[0]["lex_id"] for b in batches],
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (root / "plan.json").write_text(json.dumps(meta), encoding="utf-8")
    _log(f"{len(tasks)} tasks, {len(batches)} batches of ~{a.batch_size}")
    extract.CATALOG = Catalog()
    phases = set(a.phases.split(","))
    # ---- P1
    if "1" in phases:
        for i in sel:
            b = names[i]
            if _done(root, "p1", b):
                continue
            for sub in ("01_extract/acts", "01_extract/unit_versions", "vocab", "stats"):
                _clean_prefix(root, sub, b)
            st = phase1(root, b, batches[i], a.workers)
            _log(f"P1 {b}: {st}")
    if "2" not in phases and "3" not in phases:
        return
    # ---- G1
    if not (root / "global" / "vocab.txt.gz").exists() or a.redo_global:
        n = global_vocab(root)
        _log(f"G1 vocabulary: {n} words")
    VOCAB = load_vocab(root)
    # ---- P2
    if "2" in phases:
        for i in sel:
            b = names[i]
            if _done(root, "p2", b):
                continue
            for sub in ("03_norm", "index", "clauses", "twins", "df"):
                _clean_prefix(root, sub, b)
            st = phase2(root, b, a.workers)
            _log(f"P2 {b}: {st}")
    if "3" not in phases:
        return
    # ---- G2
    done_batches = [b for b in names if _done(root, "p2", b)]
    if len(done_batches) < len(names):
        _log("not every batch has finished P2; stopping before the global step")
        return
    if not (root / "global" / "_DONE").exists() or a.redo_global:
        st = global_step(root, names)
        _log(f"G2: {st}")
    # ---- P3
    with gzip.open(root / "global" / "caps_common.txt.gz", "rt", encoding="utf-8") as f:
        DF = CommonCaps(set(f.read().split("\n")))
    bench, core = leak.load_bench(), leak.load_core()
    NET = leak.build_net(bench, core, unseen)
    CORE_REV = {v: k for k, v in core.items() if v}
    canary = leak.canary_test(NET, bench, unseen)
    (root / "06_safe" / "canary.json").parent.mkdir(exist_ok=True)
    (root / "06_safe" / "canary.json").write_text(json.dumps(canary, indent=1), encoding="utf-8")
    if not canary["passed"]:
        raise SystemExit("canary failed: the leak net did not remove every injected document")
    FLAGS = {}
    for r in _read_all(root / "global" / "flags.jsonl.gz"):
        FLAGS[r["lex_id"]] = r
    for i in sel:
        b = names[i]
        if _done(root, "p3", b):
            continue
        for sub in (
            "05_filter",
            "06_safe/pii_report",
            "06_safe/leak_report",
            "07_train/cpt_docs",
            "07_train/cpt_original_edition",
            "07_train/amendment_docs",
            "07_train/status_docs",
            "07_train/lesson_inputs",
            "07_train/held_out",
            "07_train/drop_samples",
        ):
            _clean_prefix(root, sub, b)
        st = phase3(root, b, a.workers)
        _log(f"P3 {b}: docs {st['docs_processed']} drops {st.get('drops')} ({st['seconds']} s)")
    if all(_done(root, "p3", b) for b in names):
        rep = merge_stats(root, names)
        rep["canary"] = {
            k: canary[k]
            for k in ("n", "failed", "passed", "short_unseen_answers_not_coverable_by_13gram", "unseen_items")
        }
        (root / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
        (root / "_DONE").write_text("ok")
        _log("all batches finished; report.json written")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--out", default=str(config.OUT / "full"))
    ap.add_argument("--batch-size", type=int, default=BATCH_DOCS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--ids", default="")
    ap.add_argument("--only", default="", help="batch range, e.g. 0-0 (all phases for those batches only)")
    ap.add_argument("--phases", default="1,2,3")
    ap.add_argument("--redo-global", action="store_true")
    a = ap.parse_args()
    if a.workers > 4:
        sys.exit("at most 4 worker processes (the box is shared)")
    if a.cmd == "run":
        run(a)
    else:
        root = Path(a.out)
        names = sorted({p.name.split("_")[0] for p in (root / "stats").glob("b*_p1.json")})
        print(json.dumps(merge_stats(root, names), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
