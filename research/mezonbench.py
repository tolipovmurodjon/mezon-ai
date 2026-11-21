"""MezonBench v1: the exam for an Uzbek legal foundation model, generated from the point-in-time law store.

    .venv/Scripts/python.exe -X utf8 -m research.mezonbench build            # -> data/bench/mezonbench_v1.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench score preds.jsonl  # preds: {"id", "answer"} per line

Four task families, every answer checked by the store, no human or LLM grader:
  lookup     "quote article X of act Y as it read on date D"   -> a verbatim quote of >= 60 characters from that edition
  flip       two versions of one article, "which was in force on D?"  -> A / B (tests the date, not memory)
  in_force   "did article X of act Y exist / stand on date D?"  -> ha / yo'q (incl. deleted and later-inserted parts)
  hierarchy  two acts of different legal force, "which prevails in a conflict?" (NLA O'RQ-682 art. 6) -> A / B
Each item has "recent": true when its date is on or after 2025-07-01 (the newest models' knowledge thins out there).
Answers saying "noaniq" count as abstentions, reported separately. Scores print N and a 95 % Wilson interval.
Decision audit, court rulings and the lawyer exam join as further families when their gold labels exist.
"""

import itertools
import json
import random
import re
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from datetime import date, timedelta
from math import sqrt
from pathlib import Path

from mezon.config import LAW_DB
from mezon.lawstore.store import LawStore
from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bench" / "mezonbench_v1.jsonl"
TODAY = "2026-11-20"
RECENT = "2025-07-01"
SEED = 20261120
SIZES = {"lookup": 120, "flip": 120, "in_force": 120, "hierarchy": 40}
# Legal force by act type (NLA O'RQ-682 art. 6): higher number wins. Codes are laws; President's PF and PQ are equal.
RANK = {"constitution": 6, "law": 5, "code": 5, "pf": 4, "pq": 4, "vmq": 3, "ministry": 2, "local": 1}
SYSTEM = ("Siz O'zbekiston qonunchiligi bo'yicha ekspertsiz. Qonunni ko'rsatilgan sanadagi tahriri bo'yicha javob "
          "bering. Bilmasangiz yoki asos topilmasa, \"noaniq\" deb yozing.")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s or "")).strip(" .;:,\"'«»“”")


def human_path(path: str) -> str:
    words = {"art": "modda", "part": "qism", "cl": "band", "annex": "ilova", "ch": "bob", "sec": "bo'lim",
             "sub": "kichik band", "pre": "kirish qismi"}
    out = []
    for piece in path.split("/"):
        kind, _, num = piece.partition(":")
        out.append(f"{num}-{words.get(kind, kind)}")
    return " ".join(out)


def act_name(a) -> str:
    kind = {"law": "Qonun", "code": "Kodeks", "constitution": "Konstitutsiya", "pf": "Prezident Farmoni",
            "pq": "Prezident qarori", "vmq": "Vazirlar Mahkamasi qarori", "ministry": "vazirlik hujjati",
            # refinery types (local decisions, courts, others); the store never produces them
            "local_hokim": "hokim qarori", "local_kengash": "Kengash qarori", "court": "sud hujjati",
            "f": "Prezident farmoyishi", "chamber": "palata qarori", "other": "hujjat"}[a["type"]]
    num = (a["number"] or "").replace("‘", "'")
    if a["type"] == "vmq" and num:
        num = f"VMQ-{num}"
    return f"«{a['title']}» ({kind}{', ' + num if num else ''})"


def rand_date(rng: random.Random, start: str, end: str | None) -> str | None:
    a = date.fromisoformat(start)
    b = date.fromisoformat(min(end or TODAY, TODAY)) - timedelta(days=1)
    if b < a:
        return None
    return (a + timedelta(days=rng.randint(0, (b - a).days))).isoformat()


def diff_window(x: str, y: str, width: int = 420) -> tuple[str, str]:
    i = next((k for k, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
    s = max(0, i - 120)
    return ("…" if s else "") + x[s:s + width], ("…" if s else "") + y[s:s + width]


def build() -> None:
    rng = random.Random(SEED)
    law = LawStore()
    con = sqlite3.connect(LAW_DB)
    con.row_factory = sqlite3.Row
    acts = {r["act_key"]: r for r in con.execute("SELECT * FROM acts")}
    units = con.execute("SELECT act_key, path, text, valid_from, valid_to FROM units WHERE length(text) >= 80 "
                        "AND path NOT LIKE '%preamble%' ORDER BY id").fetchall()
    by_path = defaultdict(list)
    for u in units:
        by_path[(u["act_key"], u["path"])].append(u)
    items = []

    def add(family, prompt, answer, meta, on):
        items.append({"id": f"{family}-{sum(i['family'] == family for i in items) + 1:03d}", "family": family,
                      "system": SYSTEM, "prompt": prompt, "answer": answer, "date": on,
                      "recent": on >= RECENT, **meta})

    def gap_free(key, on):  # skip dates where the store may have skipped editions of a big code
        return law.edition_gap(key, on) is None

    # lookup: quote the article as on the date
    pool = units[:]
    rng.shuffle(pool)
    for u in pool:
        if sum(i["family"] == "lookup" for i in items) >= SIZES["lookup"]:
            break
        on = rand_date(rng, u["valid_from"], u["valid_to"])
        if not on or not gap_free(u["act_key"], on):
            continue
        got = law.get_unit(u["act_key"], u["path"], on)
        if not got or norm(got["text"]) != norm(u["text"]):
            continue
        a = acts[u["act_key"]]
        add("lookup", f"{act_name(a)} {human_path(u['path'])} {on} holatida qanday edi? Matn boshidan kamida 60 belgini "
            f"aynan (so'zma-so'z) keltiring.", got["text"], {"act": u["act_key"], "path": u["path"], "edition": got["edition"]}, on)

    # flip: two consecutive versions, which one stood on the date
    pairs = []
    for (key, path), rows in by_path.items():
        rows = sorted(rows, key=lambda r: r["valid_from"])
        for r1, r2 in itertools.pairwise(rows):
            a, b = norm(r1["text"]), norm(r2["text"])
            short, long_ = sorted((a, b), key=len)
            # a wording fully contained in the other is usually a parser boundary shift, not an amendment
            # (flip-017/028/098/114 in v1; lex.uz's own page disagreed with flip-028)
            if r1["valid_to"] == r2["valid_from"] and a != b and short.rstrip(";.,: ") not in long_:
                pairs.append((r1, r2))
    rng.shuffle(pairs)
    for r1, r2 in pairs:
        if sum(i["family"] == "flip" for i in items) >= SIZES["flip"]:
            break
        old_is_gold = rng.random() < 0.5
        gold = r1 if old_is_gold else r2
        on = rand_date(rng, gold["valid_from"], gold["valid_to"])
        if not on or not gap_free(r1["act_key"], on):
            continue
        got = law.get_unit(r1["act_key"], r1["path"], on)
        if not got or norm(got["text"]) != norm(gold["text"]):
            continue
        t_old, t_new = diff_window(r1["text"], r2["text"])
        first_is_old = rng.random() < 0.5
        a_txt, b_txt = (t_old, t_new) if first_is_old else (t_new, t_old)
        answer = "A" if (old_is_gold == first_is_old) else "B"
        a = acts[r1["act_key"]]
        add("flip", f"{act_name(a)} {human_path(r1['path'])} ikki tahrirda:\nA) {a_txt}\nB) {b_txt}\n"
            f"{on} kuni qaysi tahrir amalda edi? Faqat A yoki B deb javob bering.", answer,
            {"act": r1["act_key"], "path": r1["path"], "changed_on": r2["valid_from"]}, on)

    # in_force: yes on a live date; no before an inserted part or after a deleted one
    yes, no = [], []
    for (key, path), rows in by_path.items():
        rows = sorted(rows, key=lambda r: r["valid_from"])
        first_ed = law.editions(key)[0]["valid_from"] if law.editions(key) else None
        yes.append((rows[0], "in"))
        if first_ed and rows[0]["valid_from"] > first_ed:
            no.append((rows[0], "before"))
        if rows[-1]["valid_to"] and rows[-1]["valid_to"] < TODAY:
            no.append((rows[-1], "after"))
    rng.shuffle(yes)
    rng.shuffle(no)
    half = SIZES["in_force"] // 2
    for pool, want in ((yes, "ha"), (no, "yo'q")):
        n = 0
        for r, where in pool:
            if n >= half:
                break
            key = r["act_key"]
            if where == "in":
                on = rand_date(rng, r["valid_from"], r["valid_to"])
            elif where == "before":
                on = rand_date(rng, law.editions(key)[0]["valid_from"], r["valid_from"])
            else:
                on = rand_date(rng, r["valid_to"], None)
            if not on or not gap_free(key, on):
                continue
            exists = law.get_unit(key, r["path"], on) is not None
            if exists != (want == "ha"):
                continue
            a = acts[key]
            add("in_force", f"{act_name(a)} {human_path(r['path'])} {on} kuni amalda bo'lganmi (shu raqam bilan "
                f"mavjud edimi)? Faqat \"ha\" yoki \"yo'q\" deb javob bering.", want,
                {"act": key, "path": r["path"], "case": where}, on)
            n += 1

    # hierarchy: which prevails in a conflict (different legal force only)
    keys = sorted(acts)
    tries = 0
    while sum(i["family"] == "hierarchy" for i in items) < SIZES["hierarchy"] and tries < 5000:
        tries += 1
        x, y = rng.sample(keys, 2)
        if RANK[acts[x]["type"]] == RANK[acts[y]["type"]]:
            continue
        on = max(acts[x]["adopted"] or "2000-01-01", acts[y]["adopted"] or "2000-01-01")
        win = "A" if RANK[acts[x]["type"]] > RANK[acts[y]["type"]] else "B"
        if any(i["family"] == "hierarchy" and {i["a"], i["b"]} == {x, y} for i in items):
            continue
        add("hierarchy", f"A) {act_name(acts[x])}\nB) {act_name(acts[y])}\nUlarning normalari bir-biriga zid bo'lsa, "
            f"qaysi biri ustun turadi? Faqat A yoki B deb javob bering.", win, {"a": x, "b": y}, on)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    counts = defaultdict(int)
    for it in items:
        counts[it["family"]] += 1
    print(f"{OUT}: {len(items)} items {dict(counts)}; recent (>= {RECENT}): {sum(i['recent'] for i in items)}")


def unseen(act: str, path: str) -> bool:
    """Half of the exam articles are never taught (generalisation); the other half are taught as law-school
    lessons but never with the exam's question (did it learn the law?). Fixed by a hash, so it never moves."""
    return zlib.crc32(f"{act}|{path}".encode()) % 2 == 0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def grade(item: dict, answer: str) -> str:
    """'right' | 'wrong' | 'abstain'."""
    a = (answer or "").strip()
    if "noaniq" in fold(a):
        return "abstain"
    if item["family"] == "lookup":
        # the quote may come wrapped ("<act> 73-modda ... edi: > «quote»"): accept any quoted span, "> " line or text
        # after a colon that is itself verbatim in the gold text and long enough (21 Nov: whole-answer matching marked
        # correct tool-backed quotes wrong)
        gold, need = norm(item["answer"]), min(60, len(norm(item["answer"])))
        spans = [a, a.split(":", 1)[-1], *re.findall(r"«(.{20,}?)»(?!\S)", a, re.DOTALL),
                 *(ln.lstrip("> ").strip(" «»\"") for ln in a.splitlines())]
        ok = any(len(q) >= need and q in gold for q in (norm(s.strip(" «»\"“”.…")) for s in spans))
        return "right" if ok else "wrong"
    if item["family"] == "in_force":
        f = fold(a).lstrip(" *\"'")
        said = "yo'q" if f.startswith(("yo", "yoq", "йў", "нет", "no")) else "ha" if f.startswith(("ha", "да", "yes")) else ""
        return "right" if said == item["answer"] else "wrong"
    m = re.search(r"\b([AB])\b", a.upper())
    return "right" if m and m.group(1) == item["answer"] else "wrong"


def score(pred_path: str) -> dict:
    items = {json.loads(line)["id"]: json.loads(line) for line in OUT.open(encoding="utf-8")}
    with Path(pred_path).open(encoding="utf-8") as f:
        preds = {json.loads(line)["id"]: json.loads(line).get("answer", "") for line in f}
    table = defaultdict(lambda: {"right": 0, "wrong": 0, "abstain": 0})
    excl = OUT.parent / "excluded_ids.json"  # items found invalid after the build (see research/bench_key_check.py)
    excluded = set(json.loads(excl.read_text(encoding="utf-8"))) if excl.exists() else set()
    for iid, it in items.items():
        if iid not in preds:
            continue
        g = grade(it, preds[iid])
        if iid not in excluded:
            table["CLEAN"][g] += 1
        split = ("unseen" if unseen(it["act"], it["path"]) else "seen") if "path" in it else None
        for key in (it["family"], "ALL", f"{it['family']}:recent" if it["recent"] else None,
                    f"{it['family']}:{split}" if split else None, f"ALL:{split}" if split else None):
            if key:
                table[key][g] += 1
    # answer shares per binary family + the always-majority baseline: a collapse to one answer shows up here
    # (pilot v1: flip "A" 109/120, in_force "ha" 119/120 while gold is ~50/50)
    shares = defaultdict(Counter)
    for iid, it in items.items():
        if iid in preds and it["family"] in ("flip", "in_force", "hierarchy"):
            a = norm(preds[iid]).lower()
            shares[it["family"]]["noaniq" if "noaniq" in a else (a.split() or ["?"])[0][:4]] += 1
    for fam, c in sorted(shares.items()):
        gold = Counter(norm(str(it["answer"])).lower()[:4] for it in items.values() if it["family"] == fam)
        n = sum(c.values())
        top, top_n = c.most_common(1)[0]
        flag = "  <-- COLLAPSE?" if top != "noaniq" and top_n / n > 0.65 else ""
        print(f"{fam:10s} answer shares {dict(c.most_common(4))} | gold {dict(gold)} | always-majority "
              f"{max(gold.values()) / sum(gold.values()):.3f}{flag}")
    out = {}
    for key in sorted(table):
        t = table[key]
        n = sum(t.values())
        lo, hi = wilson(t["right"], n)
        out[key] = {"n": n, **t, "acc": round(t["right"] / n, 3) if n else 0, "ci95": [round(lo, 3), round(hi, 3)]}
        print(f"{key:18} N={n:4}  right {t['right']:4}  wrong {t['wrong']:4}  abstain {t['abstain']:3}  "
              f"acc {out[key]['acc']:.3f}  95% CI {out[key]['ci95']}")
    return out


if __name__ == "__main__":
    {"build": build, "score": lambda: score(sys.argv[2])}[sys.argv[1]]()
