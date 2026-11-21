"""Strict-judge pilot, step 1: fresh training questions from the law store, disjoint from both exams.

    .venv/Scripts/python.exe -X utf8 -m research.judge_questions build [--seed N] [--out data/train/judge_q_r1.jsonl]

Families: lookup / flip / in_force / hierarchy (generator logic of research/mezonbench.py build()) and "where"
(research/mezonbench_where.py style). Disjoint rule: no unit whose article (act + "art:N" root, or the whole path when it
has no article) appears in data/bench/mezonbench_v1.jsonl or mezonbench_where_v1.jsonl (this covers every exam
(act, path) and the 4 excluded flip pairs); hierarchy pairs of the exam are skipped in both orders.
Binary families are balanced 50/50 with A/B twins: flip twins swap the two texts (same date), hierarchy twins swap the
two acts, in_force has equal "ha" and "yo'q". About 12 % of items are unanswerable (gold "noaniq", `unans` names why):
date inside an edition gap of the store, a date after 2026-11-20, or an act the store does not hold.
Every item records family, gold answer, date, act/path; grade with research.judge_reward.reward().
"""

import argparse
import itertools
import json
import random
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from mezon.config import LAW_DB
from mezon.lawstore.store import LawStore
from research.mezonbench import (
    RANK,
    RECENT,
    SYSTEM,
    TODAY,
    act_name,
    diff_window,
    human_path,
    norm,
    rand_date,
)
from research.mezonbench_where import SYSTEM as WHERE_SYSTEM

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "train" / "judge_q_r1.jsonl"
BENCH = [
    ROOT / "data" / "bench" / "mezonbench_v1.jsonl",
    ROOT / "data" / "bench" / "mezonbench_where_v1.jsonl",
]
SEED = 20261121
SIZES = {
    "lookup": 220,
    "flip_pairs": 220,
    "in_force_each": 220,
    "hier_pairs": 50,
    "where": 150,
    "unans_gap": 80,
    "unans_future": 60,
    "unans_noact": 40,
}
# real Uzbek acts the store does not hold (checked with LawStore.find_act at build time)
ABSENT = [
    ("Mehnat kodeksi", "Kodeks"),
    ("Fuqarolik kodeksi", "Kodeks"),
    ("Jinoyat kodeksi", "Kodeks"),
    ("Oila kodeksi", "Kodeks"),
    ("Bojxona kodeksi", "Kodeks"),
    ("Saylov kodeksi", "Kodeks"),
    ("Ekologiya kodeksi", "Kodeks"),
    ("Shaharsozlik kodeksi", "Kodeks"),
    ("Suv kodeksi", "Kodeks"),
    ("Jinoyat-protsessual kodeksi", "Kodeks"),
]


def article_root(path: str) -> str:
    m = re.match(r"(art:\d+(?:-\d+)?|annex:\d+)", path)
    return m.group(1) if m else path


def exam_keys(files=BENCH) -> tuple[set, set]:
    """(act, article root) pairs of every exam item, and hierarchy act pairs (both orders)."""
    keys, pairs = set(), set()
    for f in files:
        if not Path(f).exists():
            continue
        for line in Path(f).read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            it = json.loads(line)
            if "path" in it:
                keys.add((it["act"], article_root(it["path"])))
            if it.get("family") == "hierarchy":
                pairs.add((it["a"], it["b"]))
                pairs.add((it["b"], it["a"]))
    return keys, pairs


def build(seed: int = SEED, out: Path = OUT) -> list[dict]:
    rng = random.Random(seed)
    law = LawStore()
    con = sqlite3.connect(LAW_DB)
    con.row_factory = sqlite3.Row
    acts = {r["act_key"]: r for r in con.execute("SELECT * FROM acts")}
    banned, banned_pairs = exam_keys()
    units = [
        u
        for u in con.execute(
            "SELECT act_key, path, text, valid_from, valid_to FROM units WHERE length(text) >= 80 "
            "AND path NOT LIKE '%preamble%' ORDER BY id"
        )
        if (u["act_key"], article_root(u["path"])) not in banned
    ]
    by_path = defaultdict(list)
    for u in units:
        by_path[(u["act_key"], u["path"])].append(u)
    items: list[dict] = []
    counter: Counter = Counter()

    def add(family, prompt, answer, on, meta, system=SYSTEM):
        counter[family] += 1
        it = {
            "id": f"j-{family}-{counter[family]:04d}",
            "family": family,
            "system": system,
            "prompt": prompt,
            "answer": answer,
            "date": on,
            "recent": bool(on) and on >= RECENT,
            "unans": "",
            **meta,
        }
        items.append(it)
        return it

    def gap_free(key, on):
        return law.edition_gap(key, on) is None

    # lookup
    pool = units[:]
    rng.shuffle(pool)
    n = 0
    for u in pool:
        if n >= SIZES["lookup"]:
            break
        on = rand_date(rng, u["valid_from"], u["valid_to"])
        if not on or not gap_free(u["act_key"], on):
            continue
        got = law.get_unit(u["act_key"], u["path"], on)
        if not got or norm(got["text"]) != norm(u["text"]):
            continue
        add(
            "lookup",
            f"{act_name(acts[u['act_key']])} {human_path(u['path'])} {on} holatida qanday edi? Matn boshidan "
            f"kamida 60 belgini aynan (so'zma-so'z) keltiring.",
            got["text"],
            on,
            {"act": u["act_key"], "path": u["path"], "edition": got["edition"]},
        )
        n += 1

    # flip: twin pairs, same date, A and B swapped
    pairs = []
    for (key, path), rows in by_path.items():
        rows = sorted(rows, key=lambda r: r["valid_from"])
        for r1, r2 in itertools.pairwise(rows):
            a, b = norm(r1["text"]), norm(r2["text"])
            short, long_ = sorted((a, b), key=len)
            if r1["valid_to"] == r2["valid_from"] and a != b and short.rstrip(";.,: ") not in long_:
                pairs.append((r1, r2))
    rng.shuffle(pairs)
    n = 0
    for r1, r2 in pairs:
        if n >= SIZES["flip_pairs"]:
            break
        old_is_gold = n % 2 == 0  # exactly half of the pairs have the old text as gold
        gold = r1 if old_is_gold else r2
        on = rand_date(rng, gold["valid_from"], gold["valid_to"])
        if not on or not gap_free(r1["act_key"], on):
            continue
        got = law.get_unit(r1["act_key"], r1["path"], on)
        if not got or norm(got["text"]) != norm(gold["text"]):
            continue
        t_old, t_new = diff_window(r1["text"], r2["text"])
        a = acts[r1["act_key"]]
        first = None
        for order in (True, False):  # old first, then new first
            a_txt, b_txt = (t_old, t_new) if order else (t_new, t_old)
            answer = "A" if old_is_gold == order else "B"
            it = add(
                "flip",
                f"{act_name(a)} {human_path(r1['path'])} ikki tahrirda:\nA) {a_txt}\nB) {b_txt}\n{on} kuni "
                f"qaysi tahrir amalda edi? Faqat A yoki B deb javob bering.",
                answer,
                on,
                {"act": r1["act_key"], "path": r1["path"], "changed_on": r2["valid_from"]},
            )
            if first is None:
                first = it
            else:
                it["twin"], first["twin"] = first["id"], it["id"]
        n += 1

    # in_force: equal ha / yo'q, two wordings
    yes, no = [], []
    for (key, path), rows in by_path.items():
        rows = sorted(rows, key=lambda r: r["valid_from"])
        eds = law.editions(key)
        first_ed = eds[0]["valid_from"] if eds else None
        yes.append((rows[0], "in"))
        if first_ed and rows[0]["valid_from"] > first_ed:
            no.append((rows[0], "before"))
        if rows[-1]["valid_to"] and rows[-1]["valid_to"] < TODAY:
            no.append((rows[-1], "after"))
    rng.shuffle(yes)
    rng.shuffle(no)
    for pool, want in ((yes, "ha"), (no, "yo'q")):
        n = 0
        for r, where in pool:
            if n >= SIZES["in_force_each"]:
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
            if (law.get_unit(key, r["path"], on) is not None) != (want == "ha"):
                continue
            nm = f"{act_name(acts[key])} {human_path(r['path'])}"
            q = (
                f'{nm} {on} kuni amalda bo\'lganmi (shu raqam bilan mavjud edimi)? Faqat "ha" yoki "yo\'q" deb javob bering.'
                if n % 2 == 0
                else f'{on} kuni {nm} amalda edimi (shu raqam bilan mavjudmidi)? Javob: faqat "ha" yoki "yo\'q".'
            )
            add("in_force", q, want, on, {"act": key, "path": r["path"], "case": where})
            n += 1

    # hierarchy: pairs of different force, both orders (A/B twins), exam pairs skipped
    keys = sorted(acts)
    seen, tries, n = set(), 0, 0
    while n < SIZES["hier_pairs"] and tries < 20000:
        tries += 1
        x, y = rng.sample(keys, 2)
        if (
            RANK[acts[x]["type"]] == RANK[acts[y]["type"]]
            or (x, y) in banned_pairs
            or frozenset((x, y)) in seen
        ):
            continue
        seen.add(frozenset((x, y)))
        on = max(acts[x]["adopted"] or "2000-01-01", acts[y]["adopted"] or "2000-01-01")
        hi = x if RANK[acts[x]["type"]] > RANK[acts[y]["type"]] else y
        first = None
        for p, q in ((x, y), (y, x)):
            it = add(
                "hierarchy",
                f"A) {act_name(acts[p])}\nB) {act_name(acts[q])}\nUlarning normalari bir-biriga zid bo'lsa, "
                f"qaysi biri ustun turadi? Faqat A yoki B deb javob bering.",
                "A" if p == hi else "B",
                on,
                {"a": p, "b": q},
            )
            if first is None:
                first = it
            else:
                it["twin"], first["twin"] = first["id"], it["id"]
        n += 1

    # where: one sentence -> act + article (article not in any exam)
    by_art: dict[tuple[str, str], str] = {}
    for u in con.execute("SELECT act_key, path, text FROM units WHERE valid_to IS NULL"):
        k = (u["act_key"], article_root(u["path"]))
        by_art[k] = by_art.get(k, "") + " " + norm(u["text"])
    rows = [
        r
        for r in con.execute(
            "SELECT act_key, path, text FROM units WHERE valid_to IS NULL AND path LIKE 'art:%' "
            "AND length(text) BETWEEN 200 AND 3000"
        )
        if (r["act_key"], article_root(r["path"])) not in banned
    ]
    rng.shuffle(rows)
    per_act: Counter = Counter()
    for r in rows:
        if counter["where"] >= SIZES["where"]:
            break
        if per_act[r["act_key"]] >= 12:
            continue
        sents = [s.strip() for s in re.split(r"(?<=[.;])\s+", r["text"]) if 80 <= len(s.strip()) <= 260]
        if not sents:
            continue
        s = rng.choice(sents)
        ns = norm(s)
        if sum(ns in v for v in by_art.values()) != 1:
            continue
        art = re.match(r"art:(\d+(?:-\d+)?)", r["path"]).group(1)
        a = acts[r["act_key"]]
        add(
            "where",
            f"Quyidagi norma qaysi hujjatning qaysi moddasida?\n«{s}»\nJavob shakli: <hujjat nomi yoki raqami>, "
            f"<N>-modda.",
            f"{act_name(a)} {human_path(r['path'])}",
            None,
            {
                "act": r["act_key"],
                "path": r["path"],
                "article": art,
                "act_number": a["number"] or "",
                "act_title": a["title"],
            },
            system=WHERE_SYSTEM,
        )
        per_act[r["act_key"]] += 1

    # unanswerable: gold "noaniq" (family = the wording used)
    def unans(kind, key, path, on, i):
        nm = f"{act_name(acts[key])} {human_path(path)}"
        if i % 2 == 0:
            add(
                "in_force",
                f'{nm} {on} kuni amalda bo\'lganmi (shu raqam bilan mavjud edimi)? Faqat "ha" yoki "yo\'q" '
                f"deb javob bering.",
                "noaniq",
                on,
                {"act": key, "path": path, "case": kind},
            ).update(unans=kind)
        else:
            add(
                "lookup",
                f"{nm} {on} holatida qanday edi? Matn boshidan kamida 60 belgini aynan (so'zma-so'z) keltiring.",
                "noaniq",
                on,
                {"act": key, "path": path},
            ).update(unans=kind)

    gaps = []
    for key in sorted(acts):
        eds = law.editions(key)
        if len(eds) > 1 and law.edition_gap(key, eds[0]["valid_from"]):
            lo, hi = eds[0]["valid_from"], eds[1]["valid_from"]
            gaps += [(key, u["path"], lo, hi) for u in units if u["act_key"] == key and u["valid_from"] == lo]
    rng.shuffle(gaps)
    done = 0
    for key, path, lo, hi in gaps:
        if done >= SIZES["unans_gap"]:
            break
        on = rand_date(rng, lo, hi)
        if on and law.edition_gap(key, on):
            unans("gap", key, path, on, done)
            done += 1
    for i in range(SIZES["unans_future"]):
        u = rng.choice(units)
        on = (date.fromisoformat(TODAY) + timedelta(days=rng.randint(40, 700))).isoformat()
        unans("future", u["act_key"], u["path"], on, i)
    for i in range(SIZES["unans_noact"]):
        nm, kind = ABSENT[i % len(ABSENT)]
        assert law.find_act(nm) is None, nm
        on = rand_date(rng, "2019-01-01", None)
        path = f"art:{rng.randint(5, 180)}"
        if i % 2 == 0:
            q = (
                f"«Oʻzbekiston Respublikasining {nm}» ({kind}) {human_path(path)} {on} kuni amalda bo'lganmi "
                f'(shu raqam bilan mavjud edimi)? Faqat "ha" yoki "yo\'q" deb javob bering.'
            )
        else:
            q = (
                f"«Oʻzbekiston Respublikasining {nm}» ({kind}) {human_path(path)} {on} holatida qanday edi? "
                f"Matn boshidan kamida 60 belgini aynan (so'zma-so'z) keltiring."
            )
        add("in_force" if i % 2 == 0 else "lookup", q, "noaniq", on, {"act": "", "path": path}).update(
            unans="no_act"
        )

    rng.shuffle(items)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    summarize(items, out)
    return items


def summarize(items: list[dict], out) -> None:
    fam = Counter((i["family"], "unans" if i["unans"] else "ok") for i in items)
    bal = {
        f: dict(Counter(i["answer"] for i in items if i["family"] == f and not i["unans"]))
        for f in ("flip", "in_force", "hierarchy")
    }
    nu = sum(bool(i["unans"]) for i in items)
    print(
        f"{out}: {len(items)} items; unanswerable {nu} ({nu / max(len(items), 1):.1%}) "
        f"{dict(Counter(i['unans'] for i in items if i['unans']))}"
    )
    print("family counts:", {f"{a}/{b}": n for (a, b), n in sorted(fam.items())})
    print("gold balance (answerable):", bal)


def check_disjoint(path: Path = OUT) -> int:
    """Number of questions whose (act, article root) is in an exam (must be 0)."""
    banned, bpairs = exam_keys()
    bad = 0
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        it = json.loads(line)
        if it.get("act") and "path" in it and (it["act"], article_root(it["path"])) in banned:
            bad += 1
        if it["family"] == "hierarchy" and (it["a"], it["b"]) in bpairs:
            bad += 1
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "check"])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.seed, Path(a.out))
    print("overlap with exams:", check_disjoint(Path(a.out)))
