"""MezonBench v3 (expert tier): cross-source items, gold computed from real dates, never from a model.

    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v3 build
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v3 score preds1.jsonl [preds2.jsonl ...] [--private]
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v3 oracle [--private]
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v3 audit      # re-derive every gold from its evidence
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v3 freeze     # writes data/bench/FROZEN_v3_0.json

Families (each item cites 2+ real sources and one legal rule):
  discussion_window  regulation.gov.uz draft page (discussion start / end) + the adopted decision on lex.uz (adoption
                     date), joined by body and title (similarity >= 0.9, one-to-one): "was the discussion long enough
                     and did adoption come after it ended?" (NLA art. 24, PQ-3666). ha / yo'q / noaniq.
  three_month        lex.uz decision text (burden clause) + lex.uz metadata dates + NLA art. 40: ha (violation) /
                     yo'q (entry >= 3 months + 30 days after adoption) / noaniq (no date stated: the law fills it).
  defect_spot        original of a decision cancelled on adliya representation / protest / court, options A-F. It
                     needs a defect that is unambiguous in the sources; today none qualifies (the cancelling acts name
                     no defect), so the family is empty and says so. Lawyers fill it through v3_lawyer_template.csv.
Inputs: data/bench/v3_src/*.csv|jsonl, written on the GPU box by research/v3_extract*.py.
Disjoint from v1, where_v1, v2 and the training files by decision registration number; golden cases excluded.
Never train on v3. Changing an item or the grader = v3.1.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from mezon.rules.common import add_months
from research import mezonbench as mb
from research import regnum
from research.mezonbench_v2 import letter_of, verdict_of
from research.textnorm import fold
from research.v3_match import SRC, day, load, match

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench"
OUT = BENCH / "mezonbench_v3.jsonl"
PRIVATE = BENCH / "private" / "mezonbench_v3_private.jsonl"
FROZEN = BENCH / "FROZEN_v3_0.json"
TEMPLATE = BENCH / "v3_lawyer_template.csv"
SEED = 20261121
FAMILIES = ["discussion_window", "three_month", "defect_spot"]
MIN_DAYS = 15  # NLA art. 24: public discussion of a draft lasts at least 15 days
GAP_NO = 30  # a "yo'q" needs the entry date 30 days beyond adoption + 3 months (publication lags adoption)
GOLDEN = {
    "231-4-59-Q/24",
    "207-4-59-Q/24",
    "261-4-59-Q/24",
    "VII-3-1-5-77-K/25",
    "VII-4-12-5-77-K/25",
    "VI-76-4-10-146-K/24",
    "VI-76-21-10-146-K/24",
}
USED = [
    "data/bench/mezonbench_v1.jsonl",
    "data/bench/mezonbench_v1_1.jsonl",
    "data/bench/mezonbench_where_v1.jsonl",
    "data/bench/mezonbench_v2.jsonl",
    "data/train/judge_q_r1.jsonl",
    "data/train/internship_sft.jsonl",
    "data/train/internship_val.jsonl",
    "data/train/internship_v1.jsonl",
]
SYSTEM = (
    "Siz O'zbekiston mahalliy qarorlari bo'yicha ekspertsiz. Faqat berilgan manbalar va qonun normasi asosida "
    'javob bering. Manbalardan aniq javob chiqmasa "noaniq" deb yozing. Javob shakli: ha / yo\'q / noaniq.'
)


def key(n: str) -> str:
    return re.sub(r"\s+", "", (n or "").lower())


def used_regs() -> set:
    """Every registration number that appears anywhere in the older benchmarks or training files."""
    out = {key(g) for g in GOLDEN}
    for f in USED:
        p = ROOT / f
        if p.exists():
            out |= {key(h["raw"]) for h in regnum.find_all(p.read_text(encoding="utf-8"))}
    return out


def lex_url(lex_id: str) -> str:
    return f"https://lex.uz/uz/docs/{lex_id}"


def dmy(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def parse_dmy(s: str) -> dt.date | None:
    return day((s or "")[:10], "%d.%m.%Y")


# ---------------------------------------------------------------- discussion_window


def window_gold(start: dt.date, end: dt.date, adopted: dt.date) -> str | None:
    """'ha' | "yo'q" | None when the sources are borderline (conventions differ by a day): dropped, never guessed."""
    length, gap = (end - start).days, (adopted - end).days
    if length == MIN_DAYS - 1 or gap == 0:
        return None
    return "ha" if length >= MIN_DAYS and gap >= 1 else "yo'q"


def discussion_prompt(d: dict | None, x: dict) -> str:
    src2 = (
        f'2) lex.uz qarori {lex_url(x["lex_id"])}: {x["badge"]}; sarlavha: "{x["title"]}"; qabul qilingan sana: '
        f"{dmy(x['adopted_d'])}."
    )
    if d is None:
        src1 = "1) regulation.gov.uz: bu qaror uchun muhokama sahifasi (loyiha) berilmagan va tegishli sahifa topilmadi."
    else:
        src1 = (
            f"1) regulation.gov.uz loyiha sahifasi https://regulation.gov.uz/oz/d/{d['id']}: yaratuvchi: "
            f'{d["creator"]}; sarlavha: "{d["title"]}"; jamoatchilik muhokamasi {dmy(d["start_d"])} dan '
            f"{dmy(d['end_d'])} gacha."
        )
    return (
        f"Ikki manba:\n{src1}\n{src2}\n\nSavol: \"Normativ-huquqiy hujjatlar to'g'risida\"gi qonun va PQ-3666 bo'yicha, "
        "jamoatchilik muhokamasi qonuniy eng kam muddat davom etganmi VA qaror muhokama tugaganidan keyin (kamida "
        "bir kun o'tib) qabul qilinganmi? Muddat = tugash sanasi minus boshlanish sanasi (kalendar kunlari). "
        "Javob: ha / yo'q / noaniq."
    )


def discussion_items(rng: random.Random, used: set) -> list[dict]:
    decs, drafts = load()
    ms = [m for m in match(decs, drafts) if key(m["decision"]["number"]) not in used]
    yes, no = [], []
    for m in ms:
        d, x = m["draft"], m["decision"]
        g = window_gold(d["start_d"], d["end_d"], x["adopted_d"])
        if g:
            item = {
                "family": "discussion_window",
                "task": "window",
                "answer": g,
                "verdict": g,
                "prompt": discussion_prompt(d, x),
                "decision": x["number"],
                "lex_id": x["lex_id"],
                "evidence": [
                    {
                        "source": "regulation.gov.uz",
                        "url": f"https://regulation.gov.uz/oz/d/{d['id']}",
                        "start": d["start_d"].isoformat(),
                        "end": d["end_d"].isoformat(),
                    },
                    {"source": "lex.uz", "url": lex_url(x["lex_id"]), "adopted": x["adopted_d"].isoformat()},
                ],
                "rule": "NLA art. 24; PQ-3666 item 4",
                "title_similarity": m["sim"],
            }
            (yes if g == "ha" else no).append(item)
    n = min(len(no), 100)
    rng.shuffle(yes)
    rng.shuffle(no)
    out = yes[:n] + no[:n]
    # noaniq: decisions with NO draft candidate at all (best same-body title similarity < 0.5): the second source
    # does not exist in the sources given, so the honest answer is noaniq.
    matched = {m["decision"]["lex_id"] for m in ms}
    by = defaultdict(list)
    for d in drafts:
        by[(d["place"], d["kind"])].append(d["ft"])
    from research.textnorm import similarity

    pool = [
        x
        for x in decs
        if x["lex_id"] not in matched
        and key(x["number"]) not in used
        and x["adopted_d"].year >= 2020
        and not any(similarity(x["ft"], t) >= 0.5 for t in by.get((x["place"], x["kind"]), []))
    ]
    rng.shuffle(pool)
    for x in pool[: round(0.15 * len(out) / 0.85)]:
        out.append(
            {
                "family": "discussion_window",
                "task": "window_nodraft",
                "answer": "noaniq",
                "verdict": "noaniq",
                "prompt": discussion_prompt(None, x),
                "decision": x["number"],
                "lex_id": x["lex_id"],
                "evidence": [
                    {"source": "lex.uz", "url": lex_url(x["lex_id"]), "adopted": x["adopted_d"].isoformat()}
                ],
                "rule": "NLA art. 24; PQ-3666 item 4",
                "why": "no draft page in the sources",
            }
        )
    return out


# ---------------------------------------------------------------- three_month

_LATER = re.compile(r"(?<![0-9a-z])(?:3|uch) oy\w*")


# budgets, taxes and fees set by the Tax Code / Budget Code have their own timing rules: never a clear art. 40 case
_SPECIAL = re.compile(r"budjet|byudjet|soliq|koeffitsiyent|bojxona")


def three_month_gold(adopted: dt.date, sentence: str, burden_business: bool) -> str | None:
    """Gold from the decision's own entry-into-force sentence (lex.uz's 'effective' metadata is unreliable: many acts
    carry the crawl-era date 14.02.2022). yo'q = the text itself puts entry three months after publication, or on a
    stated date at least 30 days beyond adoption + 3 months (publication lags adoption). ha = a business burden that
    takes effect on publication or on a stated date earlier than adoption + 3 months. None = anything else."""
    from research.regulation_window import entry_into_force

    ev = entry_into_force(sentence) if sentence else {"kind": "none"}
    f = fold(sentence)
    if ev["kind"] == "relative" and _LATER.search(f) and re.search(r"keyin|song|otgach|otib", f):
        return "yo'q"
    if ev["kind"] == "date":
        d = ev["date"]
        if d >= add_months(adopted, 3) + dt.timedelta(days=GAP_NO):
            return "yo'q"
        if adopted <= d < add_months(adopted, 3) and burden_business:
            return "ha"
        return None
    if ev["kind"] == "relative" and burden_business and not _LATER.search(f) and "kuchga kir" in f:
        return "ha"
    return None


def clip(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def three_prompt(r: dict, adopted: dt.date) -> str:
    sent = r["eif_sentence"].strip() or "(matnda kuchga kirish sanasi haqida band topilmadi)"
    return (
        f'Manbalar:\n1) lex.uz qarori {lex_url(r["lex_id"])}: {r["body"]}, {r["number"]}; sarlavha: "{r["title"]}".\n'
        f'   Majburiyat yuklovchi band ({r["clause_no"]}-band): "{clip(r["clause"], 520)}"\n'
        f'   Kuchga kirish bandi: "{sent}"\n2) lex.uz ma\'lumoti: qaror {dmy(adopted)} da qabul qilingan.\n\n'
        "Savol: \"Normativ-huquqiy hujjatlar to'g'risida\"gi qonunning 40-moddasi 2-qismi (tadbirkorlik subyektlariga "
        "majburiyat yuklovchi hujjat rasmiy e'lon qilinganidan keyin kamida uch oy o'tib kuchga kiradi) bu qaror "
        "bo'yicha buzilganmi? Javob: ha / yo'q / noaniq."
    )


def three_month_items(rng: random.Random, used: set) -> list[dict]:
    yes, no, na = [], [], []
    for r in csv.DictReader((SRC / "lex_local_text.csv").open(encoding="utf-8")):
        a = parse_dmy(r["adopted"])
        if not a or a.year < 2021 or key(r["number"]) in used:
            continue
        explicit = (
            r["business"] == "1"
            and r["quota_or_tax"] == "0"
            and r["budget_alloc"] == "0"
            and not _SPECIAL.search(fold(r["title"] + " " + r["clause"]))
        )
        ev = {
            "source": "lex.uz",
            "url": lex_url(r["lex_id"]),
            "adopted": a.isoformat(),
            "quote": r["eif_sentence"].strip(),
            "explicit_business": explicit,
        }
        base = {
            "family": "three_month",
            "task": "art40",
            "decision": r["number"],
            "lex_id": r["lex_id"],
            "rule": "NLA art. 40 part 2",
            "evidence": [ev],
        }
        if explicit and not r["eif_sentence"].strip():
            na.append(
                {
                    **base,
                    "task": "art40_nodate",
                    "answer": "noaniq",
                    "verdict": "noaniq",
                    "prompt": three_prompt(r, a),
                    "why": "no stated date: NLA art. 40 part 1 fills the silence",
                }
            )
            continue
        g = three_month_gold(a, r["eif_sentence"], explicit)
        if g:
            (yes if g == "ha" else no).append(
                {**base, "answer": g, "verdict": g, "prompt": three_prompt(r, a)}
            )
    n = min(len(no), len(yes), 100)
    rng.shuffle(yes)
    rng.shuffle(no)
    out = yes[:n] + no[:n]
    rng.shuffle(na)
    return out + na[: round(0.15 * len(out) / 0.85)]


# ---------------------------------------------------------------- defect_spot


def defect_items(rng: random.Random, used: set) -> list[dict]:
    """No cancelling act in the sources names its defect (checked 21.11.2026 on 39 adliya/protest cancellations),
    and the rule engine flags one unambiguous defect on none of the non-golden originals, so nothing qualifies."""
    return []


# ---------------------------------------------------------------- build


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def split_of(item_id: str) -> str:
    return "private" if int(sha16(item_id), 16) % 100 < 30 else "public"


def build() -> None:
    rng = random.Random(SEED)
    used = used_regs()
    items = []
    for fam, fn in (
        ("discussion_window", discussion_items),
        ("three_month", three_month_items),
        ("defect_spot", defect_items),
    ):
        rows = fn(rng, used)
        rng.shuffle(rows)
        for i, it in enumerate(rows, 1):
            it["id"] = f"{fam}-{i:03d}"
            it["system"] = SYSTEM
            it["lang"] = "uz"
            it["gold_source"] = "dates and quotes from the cited sources + the legal rule (no model)"
            it["lawyer_verified"] = False
            it["split"] = split_of(it["id"])
            items.append(it)
    BENCH.mkdir(exist_ok=True)
    (BENCH / "private").mkdir(exist_ok=True)
    pub = [i for i in items if i["split"] == "public"]
    prv = [i for i in items if i["split"] == "private"]
    OUT.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in pub), encoding="utf-8")
    PRIVATE.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in prv), encoding="utf-8")
    write_template(items, rng)
    for fam in FAMILIES:
        sub = [i for i in items if i["family"] == fam]
        print(
            f"{fam:18s} N={len(sub):3d} answers {dict(Counter(i['answer'] for i in sub))} "
            f"public {sum(i['split'] == 'public' for i in sub)} private {sum(i['split'] == 'private' for i in sub)}"
        )
    print(f"public {len(pub)} -> {OUT}; private {len(prv)} -> {PRIVATE}")


def write_template(items: list[dict], rng: random.Random) -> None:
    """40 rows for the lawyers: 10 pre-filled from these families (question + sources, answer blank), 30 empty."""
    cols = [
        "row",
        "family",
        "question",
        "sources",
        "lawyer_answer",
        "lawyer_defect",
        "lawyer_article_quote",
        "note",
    ]
    picks = []
    for fam in FAMILIES:
        sub = [i for i in items if i["family"] == fam and i["answer"] != "noaniq"]
        rng.shuffle(sub)
        picks += sub[: 5 if fam == "discussion_window" else 5 if fam == "three_month" else 0]
    with TEMPLATE.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for n in range(1, 41):
            if n <= len(picks):
                p = picks[n - 1]
                w.writerow(
                    [n, p["family"], p["prompt"], " | ".join(e["url"] for e in p["evidence"]), "", "", "", ""]
                )
            else:
                w.writerow([n, "", "", "", "", "", "", ""])


# ---------------------------------------------------------------- grader (changing it = a new version)


def grade(item: dict, answer: str) -> str:
    """'right' | 'wrong' | 'abstain'. On a noaniq item the only right answer is to abstain."""
    a = (answer or "").strip()
    abstains = "noaniq" in fold(a)
    if item["answer"] == "noaniq":
        return "right" if abstains else "wrong"
    if abstains:
        return "abstain"
    got = letter_of(a) if item["family"] == "defect_spot" else verdict_of(a)
    return "right" if got == item["verdict"] else "wrong"


def strict_value(item: dict, g: str) -> float:
    if g == "right":
        return (
            1.0 if item["answer"] != "noaniq" else 0.2
        )  # a correct abstention is worth little: no free points
    return 0.0 if g == "abstain" else -1.5


def load_items(private: bool = False) -> list[dict]:
    paths = [OUT] + ([PRIVATE] if private and PRIVATE.exists() else [])
    return [json.loads(x) for p in paths for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def read_preds(path: str) -> dict:
    out = {}
    for x in Path(path).read_text(encoding="utf-8").splitlines():
        if x.strip():
            j = json.loads(x)
            out[j["id"]] = j.get("answer", "")
    return out


def oracle_answer(item: dict) -> str:
    return item["answer"]


def baselines(items: list[dict]) -> dict:
    out = {}
    for fam in FAMILIES:
        sub = [i for i in items if i["family"] == fam]
        if not sub:
            continue
        consts = ["A", "B", "C", "D"] if fam == "defect_spot" else ["ha", "yo'q"]
        sc = {c: sum(grade(i, c) == "right" for i in sub) for c in consts + ["noaniq"]}
        best = max(consts, key=lambda c: sc[c])
        out[fam] = {
            "n": len(sub),
            "best_const": best,
            "const_acc": round(sc[best] / len(sub), 3),
            "noaniq_only": round(sc["noaniq"] / len(sub), 3),
            "const_strict": round(sum(strict_value(i, grade(i, best)) for i in sub) / len(sub), 3),
            "noaniq_strict": round(sum(strict_value(i, grade(i, "noaniq")) for i in sub) / len(sub), 3),
        }
    return out


def score(pred_paths: list[str], private: bool = False) -> dict:
    items = {i["id"]: i for i in load_items(private)}
    runs = [read_preds(p) for p in pred_paths]
    res = {}
    keys = [(f, [i for i in items.values() if i["family"] == f]) for f in FAMILIES] + [
        ("ALL", list(items.values()))
    ]
    for name, sub in keys:
        sub = [i for i in sub if all(i["id"] in r for r in runs)]
        if not sub:
            continue
        g0 = [grade(i, runs[0][i["id"]]) for i in sub]
        right, wrong, ab = g0.count("right"), g0.count("wrong"), g0.count("abstain")
        lo, hi = mb.wilson(right, len(sub))
        strict = sum(strict_value(i, g) for i, g in zip(sub, g0, strict=True)) / len(sub)
        ans = Counter(
            (
                "noaniq"
                if "noaniq" in fold(runs[0][i["id"]])
                else verdict_of(runs[0][i["id"]]) or letter_of(runs[0][i["id"]]) or "other"
            )
            for i in sub
        )
        collapse = max(ans.values()) / len(sub) > 0.65 and name != "ALL"
        pk = sum(all(grade(i, r[i["id"]]) == "right" for r in runs) for i in sub)
        res[name] = {
            "n": len(sub),
            "right": right,
            "wrong": wrong,
            "abstain": ab,
            "acc": round(right / len(sub), 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "strict": round(strict, 3),
            f"pass^{len(runs)}": round(pk / len(sub), 3),
        }
        print(
            f"{name:18s} N={len(sub):3d} right {right:3d} wrong {wrong:3d} abstain {ab:3d} acc {right / len(sub):.3f} "
            f"CI {res[name]['ci95']} strict {strict:+.3f} pass^{len(runs)} {pk / len(sub):.3f} shares {dict(ans.most_common(3))}"
            + ("  <-- COLLAPSE?" if collapse else "")
        )
    for fam, b in baselines(list(items.values())).items():
        print(
            f"baseline {fam:18s} best const {b['best_const']!r} {b['const_acc']:.3f} (strict {b['const_strict']:+.3f}); "
            f"all-noaniq {b['noaniq_only']:.3f} (strict {b['noaniq_strict']:+.3f})"
        )
    return res


def oracle(private: bool = False) -> dict:
    items = load_items(private)
    g = Counter(grade(i, oracle_answer(i)) for i in items)
    print(
        f"oracle {dict(g)} of {len(items)}; oracle strict "
        f"{sum(strict_value(i, grade(i, oracle_answer(i))) for i in items) / max(len(items), 1):.3f}"
    )
    for fam, b in baselines(items).items():
        print(
            f"baseline {fam:18s} N={b['n']:3d} best const {b['best_const']!r:6} acc {b['const_acc']:.3f}  "
            f"all-noaniq {b['noaniq_only']:.3f}"
        )
    return {"oracle": dict(g), "baselines": baselines(items)}


# ---------------------------------------------------------------- audit: gold re-derived from the item's own evidence


def audit(private: bool = True) -> list[str]:
    """Recompute every gold from the evidence dates and check the prompt carries them. Returns the problems."""
    bad = []
    for it in load_items(private):
        ev = it["evidence"]
        if it["family"] == "discussion_window" and it["answer"] != "noaniq":
            reg = next(e for e in ev if e["source"] == "regulation.gov.uz")
            lex = next(e for e in ev if e["source"] == "lex.uz")
            s, e, a = (
                dt.date.fromisoformat(reg["start"]),
                dt.date.fromisoformat(reg["end"]),
                dt.date.fromisoformat(lex["adopted"]),
            )
            if window_gold(s, e, a) != it["answer"]:
                bad.append(f"{it['id']}: gold {it['answer']} != recomputed {window_gold(s, e, a)}")
            for d in (s, e, a):
                if dmy(d) not in it["prompt"]:
                    bad.append(f"{it['id']}: date {dmy(d)} missing from prompt")
        if it["family"] == "three_month" and it["answer"] != "noaniq":
            e0 = ev[0]
            if (
                three_month_gold(dt.date.fromisoformat(e0["adopted"]), e0["quote"], e0["explicit_business"])
                != it["answer"]
            ):
                bad.append(f"{it['id']}: gold mismatch")
            if e0["quote"] and e0["quote"] not in it["prompt"]:
                bad.append(f"{it['id']}: quote missing from prompt")
        if len(ev) < 1 or not all(e["url"].startswith("https://") for e in ev):
            bad.append(f"{it['id']}: evidence links")
        if it["answer"] != "noaniq" and it["family"] == "discussion_window" and len(ev) < 2:
            bad.append(f"{it['id']}: needs 2 sources")
    return bad


# ---------------------------------------------------------------- freeze


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def freeze() -> None:
    pub, prv = load_items(False), [i for i in load_items(True) if i["split"] == "private"]
    man = {
        "frozen": "2026-11-21 Tashkent",
        "version": "v3.0 (expert tier, lean)",
        "public": {
            OUT.name: {
                "n": len(pub),
                "sha256_16": sha(OUT),
                "families": dict(Counter(i["family"] for i in pub)),
            }
        },
        "private": {
            "n": len(prv),
            "file_sha256_16": sha(PRIVATE) if PRIVATE.exists() else None,
            "item_hashes_sha256_16": {
                i["id"]: sha16(json.dumps(i, ensure_ascii=False, sort_keys=True)) for i in prv
            },
            "note": "the private items are not published; only these hashes are",
        },
        "code_sha256_16": {
            p: sha(ROOT / p)
            for p in (
                "research/mezonbench_v3.py",
                "research/v3_match.py",
                "research/v3_extract.py",
                "research/v3_extract_text.py",
            )
        },
        "sources_sha256_16": {p.name: sha(p) for p in sorted(SRC.glob("*.csv"))},
        "rules": "Never train on v3. Changing an item or the grader = v3.1 and every model re-runs.",
    }
    FROZEN.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{FROZEN}: public {len(pub)}, private {len(prv)} (hashes only)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "score", "oracle", "audit", "freeze"])
    ap.add_argument("preds", nargs="*")
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "score":
        score(a.preds, a.private)
    elif a.cmd == "oracle":
        oracle(a.private)
    elif a.cmd == "audit":
        bad = audit()
        print("audit problems:", len(bad))
        for b in bad[:20]:
            print(" ", b)
    else:
        freeze()


if __name__ == "__main__":
    main()
