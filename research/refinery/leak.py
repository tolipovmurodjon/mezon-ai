"""Stage 09: exam-leak control (design section 8).

Policy of research/mezonbench.py: the `unseen` half of the exam articles is never taught, the `seen` half may be taught
(but never with the exam question). Enforced on every document: (1) unit blocklist per family, (2) a 13-word n-gram net
over the answers and prompts of the unseen items, (3) golden cases and cancelling acts held out whole, (4) time cut,
(5) a canary test that must remove all 20 injected documents or the build fails."""

import csv
import json
import random
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from research.refinery import config
from research.textnorm import fold


def window_key(words: list[str]) -> int:
    s = " ".join(words).encode("utf-8")
    return (zlib.crc32(s) << 32) | zlib.adler32(s)


def windows(words: list[str], n: int = config.LEAK_NGRAM):
    for i in range(len(words) - n + 1):
        yield i, window_key(words[i : i + n])


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;!?])\s+|\n+", text)
    return [p for p in parts if p.strip()]


def load_core(path: Path = config.CORE_ACTS) -> dict[str, str]:
    """act_key -> lex_id (signed) from data/knowledge/core_acts.csv."""
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["act_key"]: r["lex_id"] for r in csv.DictReader(f) if r.get("lex_id")}


def load_bench(path: Path = config.BENCH) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).open(encoding="utf-8") if line.strip()]


@dataclass
class LeakNet:
    blocklist: dict[str, set[str]] = field(default_factory=dict)  # family (abs id) -> unit paths never taught
    unseen: dict[int, str] = field(default_factory=dict)  # window key -> bench id (answers + prompts)
    seen: dict[int, str] = field(default_factory=dict)  # logged, not removed
    short_unseen_answers: int = 0
    n_unseen_items: int = 0


def build_net(bench: list[dict], core: dict[str, str], unseen_fn) -> LeakNet:
    net = LeakNet()
    for it in bench:
        act, path = it.get("act"), it.get("path")
        is_unseen = bool(path) and unseen_fn(act, path)
        if is_unseen:
            net.n_unseen_items += 1
            fam = core.get(act, "").lstrip("-")
            if fam:
                net.blocklist.setdefault(fam, set()).add(path)
                # a part inside an article also blocks the article text that contains it (container rows)
        texts = [("answer", it.get("answer", "")), ("prompt", it.get("prompt", ""))]
        for kind, txt in texts:
            if kind == "answer" and it["family"] != "lookup":
                continue
            if kind == "prompt":  # the act name inside « » is public and also the document title: not a leak
                txt = re.sub(r"«[^»]*»", " ", txt)
            w = fold(txt).split()
            if kind == "answer" and is_unseen and len(w) < config.LEAK_NGRAM:
                net.short_unseen_answers += 1
            target = net.unseen if is_unseen else net.seen
            for _, k in windows(w):
                target.setdefault(k, it["id"])
    return net


def blocked(net: LeakNet, family: str, path: str | None, art: str | None) -> bool:
    paths = net.blocklist.get(family)
    if not paths:
        return False
    return (path in paths) or (art in paths if art else False)


def scan_segments(segs: list[str], net: LeakNet) -> tuple[dict[int, str], dict[int, str]]:
    """Segments sharing a 13-word window with an unseen (removed) or seen (logged) item: {segment index: bench id}."""
    words, owner = [], []
    for i, s in enumerate(segs):
        w = fold(s).split()
        words.extend(w)
        owner.extend([i] * len(w))
    hit_u, hit_s = {}, {}
    for i, k in windows(words):
        if k in net.unseen:
            for j in range(owner[i], owner[i + config.LEAK_NGRAM - 1] + 1):
                hit_u.setdefault(j, net.unseen[k])
        elif k in net.seen:
            for j in range(owner[i], owner[i + config.LEAK_NGRAM - 1] + 1):
                hit_s.setdefault(j, net.seen[k])
    return hit_u, hit_s


def clean_blocks(
    blocks: list[dict], net: LeakNet, family: str, protected_kinds=("title", "form", "heading")
) -> dict:
    """Remove blocklisted units, then every sentence that shares a 13-gram with an unseen item. Blocks are dicts
    {kind, text, path, art}. Returns {blocks, removed_units, removed_sentences, events}; title and heading lines are
    never cut (they repeat the act name that the prompts contain) but their overlaps are logged."""
    out, events = [], []
    removed_units = removed_sent = 0
    for b in blocks:
        if blocked(net, family, b.get("path"), b.get("art")):
            removed_units += 1
            events.append({"type": "unit_blocklist", "path": b.get("path")})
            continue
        out.append(dict(b))
    for b in out:
        segs = sentences(b["text"])
        hit_u, hit_s = scan_segments(segs, net)
        for bid in hit_s.values():
            events.append({"type": "seen_overlap", "bench": bid, "path": b.get("path")})
        if hit_u and b["kind"] in protected_kinds:
            events.extend(
                {"type": "unseen_overlap_protected", "bench": bid, "path": b.get("path")}
                for bid in hit_u.values()
            )
            continue
        if hit_u:
            keep = [s for j, s in enumerate(segs) if j not in hit_u]
            removed_sent += len(segs) - len(keep)
            events.extend(
                {"type": "unseen_ngram_removed", "bench": bid, "path": b.get("path")}
                for bid in hit_u.values()
            )
            b["text"] = " ".join(keep)
    out = [b for b in out if b["text"].strip()]
    return {
        "blocks": out,
        "removed_units": removed_units,
        "removed_sentences": removed_sent,
        "events": events,
    }


def survivors(text: str, answer: str, n: int = 8) -> int:
    """Windows of n consecutive words of `answer` still present in `text` (the canary criterion)."""
    aw = fold(answer).split()
    tw = fold(text)
    return sum(1 for i in range(max(len(aw) - n + 1, 0)) if " ".join(aw[i : i + n]) in tw)


def canary_test(net: LeakNet, bench: list[dict], unseen_fn, seed: int = config.SEED, n: int = 20) -> dict:
    """20 synthetic documents carrying unseen-half lookup quotes: verbatim, with one word changed, and embedded in
    a longer local decision. The refinery must remove all of them; the build fails if any survives."""
    rng = random.Random(seed)
    pool = sorted(
        (
            it
            for it in bench
            if it["family"] == "lookup"
            and it.get("path")
            and unseen_fn(it["act"], it["path"])
            and len(it["answer"].split()) >= 2 * config.LEAK_NGRAM + 2
        ),
        key=lambda i: i["id"],
    )
    rng.shuffle(pool)
    docs = []
    for i, it in enumerate(pool[:n]):
        words = it["answer"].split()
        if i % 3 == 0:
            kind, text = "verbatim", it["answer"]
        elif i % 3 == 1:
            j = len(words) // 2
            kind, text = "one_word_changed", " ".join(words[:j] + ["almashtirilgan"] + words[j + 1 :])
        else:
            kind = "inside_local_decision"
            text = (
                "Hokimning qarori. Qarorga muvofiq quyidagilar belgilansin. "
                + it["answer"]
                + " Ushbu qaror e'lon qilingan kundan boshlab kuchga kiradi."
            )
        docs.append({"kind": kind, "bench": it["id"], "answer": it["answer"], "text": text})
    results = []
    for d in docs:
        res = clean_blocks([{"kind": "text", "text": d["text"], "path": None, "art": None}], net, "none")
        left = " ".join(b["text"] for b in res["blocks"])
        results.append(
            {
                "kind": d["kind"],
                "bench": d["bench"],
                "survivors_8gram": survivors(left, d["answer"]),
                "unseen_13gram_left": sum(1 for _ in scan_segments([left], net)[0]),
            }
        )
    failed = [r for r in results if r["survivors_8gram"] or r["unseen_13gram_left"]]
    return {
        "n": len(results),
        "failed": len(failed),
        "results": results,
        "passed": len(results) == n and not failed,
        "short_unseen_answers_not_coverable_by_13gram": net.short_unseen_answers,
        "unseen_items": net.n_unseen_items,
    }


def golden_flag(lex_id: str, reg_number: str | None) -> str:
    """eval_flag from the golden-case lists in config (by lex id or registration number)."""
    if lex_id in config.GOLDEN_IDS:
        return "cancelling_act" if config.GOLDEN_IDS[lex_id].endswith("_cancel") else "golden"
    if reg_number and reg_number in config.GOLDEN_REG:
        return config.GOLDEN_REG[reg_number]
    return "none"
