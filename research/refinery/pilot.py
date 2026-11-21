"""End-to-end refinery run on a sample (design sections 10-11): extraction, metadata, normalisation, twins and
dedup, filters, citizen-only masking, leak control, export. Every stage writes its own shards under OUT and is
deterministic (sorted inputs, fixed seeds).

    python -X utf8 -m research.refinery.pilot --n 2000 --out data/refinery/pilot [--ids FILE] [--workers 4]

Run it under `nice -n 19`; at most 4 worker processes."""

import argparse
import hashlib
import json
import multiprocessing as mp
import time
from collections import Counter, defaultdict
from pathlib import Path

from research.mezonbench import unseen
from research.refinery import config, dedup, export, extract, extract_ocr, filters, leak, pii
from research.refinery.io import read_jsonl, sha1_file, write_jsonl
from research.refinery.normalize import detect_lang, normalise, script_counts
from research.refinery.sample import SENSITIVE, population, select
from research.refinery.sources import Catalog, twin_of
from research.textnorm import fold

_EXPECT_SCRIPT = {"uz_latn": "Latn", "uz_cyrl": "Cyrl", "ru": "Cyrl", "en": "Latn"}


def _write_shards(dirpath: Path, rows: list[dict], name: str = "part") -> int:
    n = 0
    for i in range(0, max(len(rows), 1), config.SHARD_DOCS):
        chunk = rows[i : i + config.SHARD_DOCS]
        write_jsonl(dirpath / f"{name}-{i // config.SHARD_DOCS:05d}.jsonl.gz", chunk)
        (dirpath / f"{name}-{i // config.SHARD_DOCS:05d}._DONE").write_text("ok")
        n += len(chunk)
    return n


def _body(blocks: list[dict]) -> str:
    out: list[str] = []
    for b in blocks:
        if b["kind"] in {"article", "heading", "annex"} and out and out[-1] != "":
            out.append("")
        out.append(b["text"])
    return "\n".join(out).strip()


class UnionFind:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.p[self.find(a)] = self.find(b)


def _load_extract(out: Path) -> list[dict]:
    """Stage 01 output of an earlier run (stages never edit earlier output, so a later stage can be re-run alone)."""
    recs = [r for f in sorted((out / "01_extract" / "acts").glob("*.jsonl.gz")) for r in read_jsonl(f)]
    rows: dict[str, list[dict]] = defaultdict(list)
    for f in sorted((out / "01_extract" / "unit_versions").glob("*.jsonl.gz")):
        for u in read_jsonl(f):
            rows[u["lex_id"]].append({k: v for k, v in u.items() if k != "lex_id"})
    for r in recs:
        r["unit_rows"] = rows.get(r["lex_id"], [])
    return recs


def run_pilot(
    out: Path, tasks: list[dict], workers: int = 4, census: Path | None = None, reuse_extract: bool = False
) -> dict:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "config": {
            k: getattr(config, k)
            for k in ("TIME_CUT", "SEED", "MIN_CHARS", "NEAR_DUP_JACCARD", "LEAK_NGRAM", "MAX_CHUNK_WORDS")
        },
        "stages": {},
        "drops": Counter(),
    }
    cat = Catalog()
    extract.CATALOG = cat
    # ---------------------------------------------------------------- 01 extract
    if reuse_extract:
        recs = _load_extract(out)
    else:
        with mp.get_context("fork").Pool(workers) as pool:
            recs = list(pool.imap(extract.extract_task, tasks, chunksize=4))
    recs = sorted(recs, key=lambda r: r["lex_id"])
    errors = Counter(r["error"] for r in recs if r.get("error"))
    recs = [r for r in recs if not r.get("error")]
    unit_rows = [{"lex_id": r["lex_id"], **u} for r in recs for u in r.get("unit_rows", [])]
    if not reuse_extract:
        _write_shards(
            out / "01_extract" / "acts", [{k: v for k, v in r.items() if k != "unit_rows"} for r in recs]
        )
        _write_shards(out / "01_extract" / "unit_versions", unit_rows)
    manifest["stages"]["01_extract"] = {
        "in": len(tasks),
        "out": len(recs),
        "errors": dict(errors),
        "unit_rows": len(unit_rows),
        "seconds": round(time.time() - t0, 1),
    }
    # ---------------------------------------------------------------- 02 meta (+ family)
    docs: dict[str, dict] = {}
    # vocabulary from the clean national HTML acts (count >= 5 in >= 3 documents): the OCR quality yardstick, and the
    # dictionary that undoes the OCR model's loss of the Uzbek Cyrillic letters (карори -> қарори)
    vocab = filters.build_vocab(
        [_body(r["blocks"]) for r in recs if r["source_kind"] == "html" and r["meta"]["level"] == "national"]
    )
    ocr_fixed = 0
    for r in recs:
        m = r["meta"]
        if r["source_kind"] == "ocr":
            for blk in r["blocks"]:
                blk["text"], n_fixed = extract_ocr.ocr_correct(blk["text"], vocab)
                ocr_fixed += n_fixed
        raw = _body(r["blocks"])
        d = detect_lang(raw)
        lat, cyr = script_counts(raw)
        norm_blocks, mixed_fixed = [], 0
        for b in r["blocks"]:
            t, st = normalise(b["text"], latin=lat >= cyr)
            mixed_fixed += st["homoglyph_fixed"]
            norm_blocks.append({**{k: b[k] for k in ("kind", "path", "art")}, "text": t})
        norm_blocks = [b for b in norm_blocks if b["text"]]
        docs[r["lex_id"]] = {
            "rec": r,
            "meta": m,
            "blocks": norm_blocks,
            "lang": d,
            "homoglyph_fixed": mixed_fixed,
            "expected_script": _EXPECT_SCRIPT.get(m.get("catalog_lang", "")),
            "key": r["lex_id"],
        }
    write_jsonl(
        out / "03_norm" / "docs.jsonl.gz",
        ({"lex_id": k, "lang": d["lang"], "blocks": d["blocks"]} for k, d in sorted(docs.items())),
    )
    manifest["stages"]["03_norm"] = {
        "vocab_words": len(vocab),
        "ocr_words_corrected": ocr_fixed,
        "docs": len(docs),
        "homoglyph_fixed_words": sum(d["homoglyph_fixed"] for d in docs.values()),
    }
    for d in docs.values():
        d["text"] = _body(d["blocks"])
    # twins
    twin_rows, uf = [], UnionFind()
    for lid in sorted(docs):
        o = twin_of(lid)
        if lid.startswith("-") and o in docs:
            verdict, sim = dedup.twin_verdict(docs[lid]["text"], docs[o]["text"])
            twin_rows.append({"lex_id": lid, "twin_id": o, "sim": sim, "verdict": verdict})
            if verdict == "twin":
                docs[lid]["twin_id"], docs[o]["twin_id"] = o, lid
                uf.union(lid, o)
    for lid, d in sorted(docs.items()):
        m = d["meta"]
        if m.get("number") and m.get("adopted"):
            uf.union(lid, "k:" + f"{m['number']}|{m['adopted']}|{m['level']}".lower())
    fam: dict[str, int] = {}
    members: dict[str, list[int]] = defaultdict(list)
    for lid in docs:
        members[uf.find(lid)].append(docs[lid]["meta"]["abs_id"])
    for lid, d in docs.items():
        d["family_id"] = min(members[uf.find(lid)])
        d.setdefault("twin_id", None)
        fam[lid] = d["family_id"]
    # ---------------------------------------------------------------- 06 dedup
    ex_groups = {}
    by_ls: dict[str, dict[str, str]] = defaultdict(dict)
    for lid, d in docs.items():
        by_ls[f"{d['lang']['lang']}-{d['lang']['script']}"][lid] = d["text"]
    for ls, texts in by_ls.items():
        for h, mem in dedup.exact_groups(texts).items():
            ex_groups[f"{ls}:{h}"] = mem
    exact_drop: dict[str, str] = {}
    for mem in ex_groups.values():
        for other in sorted(mem)[1:]:
            exact_drop[other] = min(mem)
    items = []
    for lid, d in docs.items():
        m = d["meta"]
        stratum = (
            f"{m['act_type']}|{(m.get('adopted') or '0000')[:4]}|{d['lang']['lang']}-{d['lang']['script']}"
        )
        items.append({"id": lid, "stratum": stratum, "text": d["text"], "adopted": m.get("adopted")})
    clusters = dedup.minhash_clusters([i for i in items if i["id"] not in exact_drop])
    cl_by_id = {c["id"]: c for c in clusters}
    units_by_doc = {
        lid: [
            {"path": b["path"], "text": b["text"]}
            for b in d["blocks"]
            if b["path"] and b["path"].startswith("cl:")
        ]
        for lid, d in docs.items()
        if d["meta"]["level"] == "local"
    }
    boiler = dedup.boilerplate_clauses(units_by_doc)
    write_jsonl(out / "04_dedup" / "twins.jsonl.gz", twin_rows)
    write_jsonl(
        out / "04_dedup" / "exact.jsonl.gz",
        [{"group": g, "members": m} for g, m in sorted(ex_groups.items())],
    )
    write_jsonl(out / "04_dedup" / "minhash_clusters.jsonl.gz", clusters)
    manifest["stages"]["04_dedup"] = {
        "twin_pairs": len(twin_rows),
        "twin_verdicts": dict(Counter(t["verdict"] for t in twin_rows)),
        "exact_groups": len(ex_groups),
        "exact_dropped": len(exact_drop),
        "clusters": len({c["cluster"] for c in clusters}),
        "cluster_members": len(clusters),
        "cluster_dropped": sum(1 for c in clusters if not c["keep"]),
        "boilerplate_clauses_dropped": sum(len(v) for v in boiler.values()),
    }
    # ---------------------------------------------------------------- 07 filters
    sig_rows = []
    for lid, d in sorted(docs.items()):
        r = d["rec"]
        exp = {"script": d["expected_script"]} if d["expected_script"] else None
        d["sig"] = filters.signals(
            d["text"],
            r["source_kind"],
            exp,
            d["lang"],
            vocab,
            r.get("n_table_chars", 0),
            r.get("table_numeric_share", 0.0),
        )
        d["decision"], d["reason"] = filters.decide(d["sig"], r["source_kind"], bool(r.get("ocr_partial")))
        d["flags"] = filters.flags(d["sig"])
        d["tier"] = filters.tier(r["source_kind"], d["meta"]["level"], d["flags"])
        sig_rows.append(
            {
                "lex_id": lid,
                "stratum": r["stratum"],
                "source_kind": r["source_kind"],
                **d["sig"],
                "decision": d["decision"],
                "reason": d["reason"],
                "flags": d["flags"],
                "tier": d["tier"],
            }
        )
    write_jsonl(out / "05_filter" / "signals.jsonl.gz", sig_rows)
    # ---------------------------------------------------------------- eval flags
    bench = leak.load_bench()
    core = leak.load_core()
    net = leak.build_net(bench, core, unseen)
    golden_fams: set[int] = set()
    for lid, d in docs.items():
        m = d["meta"]
        d["eval_flag"] = leak.golden_flag(lid, m.get("reg_number"))
        if d["eval_flag"] != "none":
            golden_fams.add(d["family_id"])
    cluster_gold = {
        c["cluster"] for c in clusters if docs[c["id"]]["eval_flag"] in {"golden", "cancelling_act"}
    }
    for lid, d in docs.items():
        m = d["meta"]
        if d["eval_flag"] == "none" and d["family_id"] in golden_fams:
            d["eval_flag"] = "golden"  # the other script or number-twin of a golden act
        if d["eval_flag"] == "none" and lid in cl_by_id and cl_by_id[lid]["cluster"] in cluster_gold:
            d["eval_flag"] = "golden"  # copies of a golden text would leak it
        if d["eval_flag"] == "none" and (m.get("adopted") or "") >= config.TIME_CUT:
            d["eval_flag"] = "time_cut"
        if d["eval_flag"] == "none" and str(m["abs_id"]) in net.blocklist:
            d["eval_flag"] = "bench_family"
    # ---------------------------------------------------------------- 08 PII
    df = pii.document_frequency(
        [
            d["text"]
            for d in docs.values()
            if d["meta"]["level"] == "local" or d["rec"]["source_kind"] == "ocr"
        ]
    )
    pii_rows, contexts = [], []
    for lid, d in sorted(docs.items()):
        lvl = (
            "national" if (d["meta"]["level"] == "national" and d["rec"]["source_kind"] != "ocr") else "local"
        )
        names: dict[str, int] = {}  # one token map per document, in memory only
        sens = bool(SENSITIVE.search(fold(d["meta"].get("title", ""))))
        counts: Counter = Counter()
        new_blocks = []
        for blk in d["blocks"]:
            t, c = pii.mask(blk["text"], lvl, df, names=names, sensitive=sens)
            counts.update(c)
            new_blocks.append({**blk, "text": t})
        d["blocks"] = new_blocks
        counts = dict(counts)
        masked = "\n".join(blk["text"] for blk in new_blocks)
        sp = pii.second_pass(masked, lvl, d["meta"].get("title", ""), df)
        d["text"] = _body(d["blocks"])
        d["pii"], d["pii_exclude"] = counts, sp["exclude"]
        pii_rows.append(
            {
                "lex_id": lid,
                "level": lvl,
                "counts": counts,
                "guardianship": sp["guardianship"],
                "residual_after_second_pass": sp["residual"],
                "exclude": sp["exclude"],
            }
        )
        if lvl == "local" and counts and len(contexts) < 120:
            contexts.extend(pii.context_samples("", masked, 2))
    write_jsonl(out / "06_safe" / "pii_report.jsonl.gz", pii_rows)
    (out / "06_safe").mkdir(parents=True, exist_ok=True)
    (out / "06_safe" / "pii_contexts_sample.txt").write_text("\n".join(contexts[:150]), encoding="utf-8")
    # ---------------------------------------------------------------- 09 leak
    leak_rows = []
    for lid, d in sorted(docs.items()):
        res = leak.clean_blocks(d["blocks"], net, str(d["meta"]["abs_id"]))
        d["blocks"], d["leak"] = res["blocks"], res
        d["text"] = _body(d["blocks"])
        leak_rows.append(
            {
                "lex_id": lid,
                "removed_units": res["removed_units"],
                "removed_sentences": res["removed_sentences"],
                "events": res["events"][:50],
            }
        )
    write_jsonl(out / "06_safe" / "leak_report.jsonl.gz", leak_rows)
    canary = leak.canary_test(net, bench, unseen)
    (out / "06_safe" / "canary.json").write_text(json.dumps(canary, indent=1), encoding="utf-8")
    # ---------------------------------------------------------------- 07 train
    cpt, a0, amend, status_docs, lessons, held, drops = [], [], [], [], [], [], Counter()
    drop_samples: list[dict] = []
    for lid, d in sorted(docs.items()):
        m, r = d["meta"], d["rec"]
        why = None
        if lid in exact_drop:
            why = "exact_duplicate"
        elif d["decision"] == "drop":
            why = d["reason"]
        elif lid in cl_by_id and not cl_by_id[lid]["keep"]:
            why = "near_duplicate"
        elif d["pii_exclude"]:
            why = "pii_guardianship"
        elif d["eval_flag"] in {"golden", "cancelling_act", "time_cut"}:
            held.append(
                {
                    "lex_id": lid,
                    "abs_id": m["abs_id"],
                    "eval_flag": d["eval_flag"],
                    "reg_number": m.get("reg_number"),
                    "sha1_raw": r.get("sha1_raw"),
                }
            )
            drops["held_out_" + d["eval_flag"]] += 1
            continue
        if why:
            drops[why] += 1
            if len(drop_samples) < 60:
                drop_samples.append(
                    {"lex_id": lid, "reason": why, "stratum": r["stratum"], "n_chars": d["sig"]["n_chars"]}
                )
            continue
        tag = (d["lang"]["lang"], d["lang"]["script"])
        status_key = "provisional" if m.get("provisional") else m["status"]
        eds = r.get("editions") or []
        v_from = eds[-1]["valid_from"] if eds else m.get("adopted")
        v_to = None
        hdr = export.header(m, *tag, v_from, v_to, status_key)
        drop_units = boiler.get(lid, set())
        blocks = [b for b in d["blocks"] if b["path"] not in drop_units]
        chunks = export.chunk_by_article(blocks, hdr)
        dup = cl_by_id[lid]["dup_count"] if lid in cl_by_id else 1
        for ch in chunks:
            cpt.append(
                {
                    "doc_id": f"{lid}:{ch['chunk']}",
                    "lex_id": lid,
                    "family_id": d["family_id"],
                    "twin_id": d["twin_id"],
                    "lang": tag[0],
                    "script": tag[1],
                    "act_type": m["act_type"],
                    "level": m["level"],
                    "number": m.get("number"),
                    "adopted": m.get("adopted"),
                    "valid_from": v_from,
                    "valid_to": v_to,
                    "status": m["status"],
                    "tier": d["tier"],
                    "source_kind": r["source_kind"],
                    "source_url": m["source_url"],
                    "dup_count": dup,
                    "pii": d["pii"],
                    "eval_flag": d["eval_flag"],
                    "header_chars": ch["header_chars"],
                    "text": ch["text"],
                    "n_chars": len(ch["text"]),
                    "n_words": ch["n_words"],
                }
            )
        orig = r.get("original")
        if orig and (orig["valid_from"] or "") < config.TIME_CUT:
            ob = [{**b, "text": normalise(b["text"], latin=tag[1] == "Latn")[0]} for b in orig["blocks"]]
            ob = [b for b in ob if b["text"]]
            ob = leak.clean_blocks(ob, net, str(m["abs_id"]))["blocks"]
            differs, sim = export.original_differs(d["text"], _body(ob))
            if differs and ob:
                ohdr = export.header(m, *tag, orig["valid_from"], orig["valid_to"], "original")
                for ch in export.chunk_by_article(ob, ohdr):
                    a0.append(
                        {
                            "doc_id": f"{lid}:orig:{ch['chunk']}",
                            "lex_id": lid,
                            "family_id": d["family_id"],
                            "tier": "A0",
                            "similarity_to_latest": sim,
                            "act_type": m["act_type"],
                            "valid_from": orig["valid_from"],
                            "valid_to": orig["valid_to"],
                            "text": ch["text"],
                            "n_words": ch["n_words"],
                            "eval_flag": d["eval_flag"],
                        }
                    )
        if r["source_kind"] == "html":
            block_paths = net.blocklist.get(str(m["abs_id"]), set())
            rows = [
                u
                for u in r.get("unit_rows", [])
                if not leak.blocked(net, str(m["abs_id"]), u["path"], u["path"].split("/part:")[0])
            ]
            for a in export.amendment_docs(m, rows, *tag):
                cleaned = leak.clean_blocks(
                    [{"kind": "text", "text": ln, "path": None, "art": None} for ln in a["text"].split("\n")],
                    net,
                    "none",
                    protected_kinds=(),
                )
                txt = "\n".join(b["text"] for b in cleaned["blocks"])
                if txt.count("\n") >= 1:
                    amend.append(
                        {
                            "doc_id": f"{lid}:chg:{a['date']}:{a['part']}",
                            "lex_id": lid,
                            "family_id": d["family_id"],
                            "tier": "B",
                            "act_type": m["act_type"],
                            "date": a["date"],
                            "text": txt,
                            "n_words": len(txt.split()),
                            "eval_flag": d["eval_flag"],
                        }
                    )
            sd = export.status_doc(m, *tag)
            if sd:
                status_docs.append(
                    {"doc_id": f"{lid}:status", "lex_id": lid, "tier": "B", **sd, "eval_flag": d["eval_flag"]}
                )
            key = next((k for k, v in core.items() if v == lid), None)
            li = export.lesson_inputs(m, rows, key or lid, block_paths)
            lessons.extend(x for x in li if not leak.scan_segments([x["text"]], net)[0])
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
                for b in blocks
                if b["path"]
                and b["path"].startswith(("cl:", "annex:"))
                and len(b["text"]) >= 80
                and (m.get("adopted") or "") < config.TIME_CUT
                and (b["path"] not in drop_units)
            ]
            lessons.extend(x for x in units if not leak.scan_segments([x["text"]], net)[0])
    for name, rows in (
        ("cpt_docs", cpt),
        ("cpt_original_edition", a0),
        ("amendment_docs", amend),
        ("status_docs", status_docs),
        ("lesson_inputs", lessons),
    ):
        _write_shards(out / "07_train" / name, rows)
    write_jsonl(out / "07_train" / "held_out" / "held_out.jsonl.gz", held)
    write_jsonl(out / "07_train" / "drop_samples.jsonl.gz", drop_samples)
    manifest["drops"] = dict(drops)
    manifest["stages"]["07_train"] = {
        "cpt_chunks": len(cpt),
        "original_edition_chunks": len(a0),
        "amendment_docs": len(amend),
        "status_docs": len(status_docs),
        "lesson_rows": len(lessons),
        "held_out": len(held),
    }
    # ---------------------------------------------------------------- statistics
    stats = _stats(docs, cpt, amend, lessons, canary, net, manifest, population(census) if census else {}, t0)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    stats["output_hashes"] = _hash_outputs(out)
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    return stats


def _hash_outputs(out: Path) -> str:
    h = hashlib.sha1()
    for p in sorted(out.glob("0[1-9]_*/**/*.jsonl.gz")) + sorted(out.glob("0[1-9]_*/*.jsonl.gz")):
        h.update(str(p.relative_to(out)).encode())
        h.update(sha1_file(p).encode())
    return h.hexdigest()


def _stats(docs, cpt, amend, lessons, canary, net, manifest, pop, t0) -> dict:
    by_stratum: dict[str, dict] = defaultdict(lambda: {"docs": 0, "kept": 0, "words": [], "chars": []})
    for d in docs.values():
        s = by_stratum[d["rec"]["stratum"]]
        s["docs"] += 1
        s["words"].append(d["sig"]["n_words"])
        s["chars"].append(d["sig"]["n_chars"])
        s["kept"] += d["decision"] == "keep"

    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else 0

    strat = {
        k: {
            "docs": v["docs"],
            "kept_by_filters": v["kept"],
            "words_total": sum(v["words"]),
            "words_median": med(v["words"]),
            "words_mean": round(sum(v["words"]) / max(len(v["words"]), 1)),
            "chars_median": med(v["chars"]),
        }
        for k, v in sorted(by_stratum.items())
    }
    pii_tot: Counter = Counter()
    pii_docs = Counter()
    for d in docs.values():
        pii_tot.update(d["pii"])
        if d["pii"]:
            pii_docs[d["meta"]["level"]] += 1
    tiers = Counter(c["tier"] for c in cpt)
    tier_words: Counter = Counter()
    for c in cpt:
        tier_words[c["tier"]] += c["n_words"]
    events = Counter(e["type"] for d in docs.values() for e in d["leak"]["events"])
    return {
        "seconds": round(time.time() - t0, 1),
        "documents_extracted": len(docs),
        "source_kinds": dict(Counter(d["rec"]["source_kind"] for d in docs.values())),
        "levels": dict(Counter(d["meta"]["level"] for d in docs.values())),
        "act_types": dict(Counter(d["meta"]["act_type"] for d in docs.values())),
        "status": dict(Counter(d["meta"]["status"] for d in docs.values())),
        "lang_script": dict(Counter(f"{d['lang']['lang']}-{d['lang']['script']}" for d in docs.values())),
        "meta_conflicts": sum(1 for d in docs.values() if d["meta"].get("meta_conflict")),
        "by_stratum": strat,
        "cpt_chunks_by_tier": dict(tiers),
        "cpt_words_by_tier": dict(tier_words),
        "amendment_docs": len(amend),
        "lesson_rows": len(lessons),
        "pii_totals": dict(pii_tot),
        "docs_with_masks_by_level": dict(pii_docs),
        "leak_events": dict(events),
        "canary": {
            k: canary[k]
            for k in ("n", "failed", "passed", "short_unseen_answers_not_coverable_by_13gram", "unseen_items")
        },
        "eval_flags": dict(Counter(d["eval_flag"] for d in docs.values())),
        "drops": manifest["drops"],
        "population_by_level_lang": pop,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--out", default=str(config.OUT / "pilot"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--reuse-extract", action="store_true", help="re-run stages 02+ on the existing 01_extract"
    )
    ap.add_argument("--census", default=str(config.OUT / "00_census" / "census.jsonl.gz"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ids_file = Path(a.ids) if a.ids else out.parent / "pilot_ids.jsonl"
    if a.ids and ids_file.exists():
        tasks = list(read_jsonl(ids_file))
    else:
        tasks = select(Path(a.census), a.n)
        write_jsonl(ids_file, tasks)
        (out / "ids.txt").write_text(
            "\n".join(f"{t['lex_id']}\t{t['stratum']}" for t in tasks), encoding="utf-8"
        )
    stats = run_pilot(out, tasks, a.workers, Path(a.census), a.reuse_extract)
    print(
        json.dumps(
            {k: stats[k] for k in ("seconds", "documents_extracted", "source_kinds", "output_hashes")},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
