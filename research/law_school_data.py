"""Law-school data (phase 1, pilot): every law text becomes a lesson, the text plus questions about that same text.

    .venv/Scripts/python.exe -X utf8 -m research.law_school_data     # -> data/train/law_school_pilot.jsonl

Why not raw text alone: AdaptLLM (Cheng et al., ICLR 2024) found that continued pre-training on raw domain text adds
knowledge but hurts the model's ability to answer prompts; appending reading-comprehension tasks mined from the same
text keeps both. We mine the tasks with rules (no LLM, no cloud), so every answer is copied from the store and is
exact: the heading, a hidden phrase, the date the wording took force, which act and article a sentence comes from,
the act's legal force, what changed between two editions, and true/false with a changed number.

Each line: {"text": <lesson>, "act", "path", "valid_from", "kinds": [...]}. Lessons for the "unseen" half of the MezonBench
articles are left out (generalisation test); the "seen" half is taught, but never with the exam's questions. Answers are balanced by construction (each kind has a
different answer per article; true/false is half true). Variety of question wording: several templates per kind.
"""

import argparse
import datetime as dt
import json
import random
import re
import sqlite3
from collections import Counter, deque
from pathlib import Path

from mezon.config import LAW_DB
from research.mezonbench import OUT as BENCH
from research.mezonbench import act_name, human_path, norm, unseen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "train" / "law_school_pilot.jsonl"
SEED = 7
FORCE = {"constitution": "Konstitutsiya: eng yuqori yuridik kuchga ega", "law": "qonun", "code": "kodeks (qonun kuchiga ega)",
         "pf": "Prezident farmoni", "pq": "Prezident qarori", "vmq": "Vazirlar Mahkamasining qarori",
         "ministry": "idoraviy (vazirlik) hujjati",
         # refinery types (research/refinery/export.py LESSON_TYPE)
         "local_hokim": "mahalliy hokim qarori (mahalliy hujjat)", "local_kengash": "mahalliy Kengash qarori (mahalliy hujjat)",
         "court": "sud hujjati", "f": "Prezident farmoyishi", "chamber": "Oliy Majlis palatasi qarori", "other": "boshqa hujjat"}
NUMS = {"bir": "ikki", "ikki": "uch", "uch": "olti", "besh": "o'n", "o'n": "o'n besh", "o'n besh": "o'ttiz",
        "olti": "uch", "o'ttiz": "o'n"}
T = {
    "heading": ["Bu moddaning sarlavhasi qanday?", "Ushbu norma qanday nomlangan?", "Matnga mos sarlavhani yozing."],
    "cloze": ["Bo'sh joyni matndagi so'zlar bilan to'ldiring: «{q}»", "Tushirib qoldirilgan qismni tiklang: «{q}»"],
    "since": ["Bu tahrir qaysi sanadan beri amalda?", "Mazkur matn qachondan kuchga kirgan tahrirda?"],
    "where": ["«{s}» degan norma qaysi hujjatning qaysi qismida?", "Quyidagi gap qayerdan olingan: «{s}»?"],
    "force": ["Bu hujjat qaysi darajadagi hujjat?", "Ushbu hujjatning yuridik kuchi qanday?"],
    "tf": ["To'g'rimi yoki noto'g'rimi: «{s}»", "Matnga ko'ra bu gap to'g'rimi: «{s}»"],
    "ondate": ["{d} sanada ushbu tahrir amalda bo'lganmi?", "Shu matn {d} holatiga ko'ra amalda edimi?"],
    "change": ["Oldingi tahrirdan ({d0}) keyingi tahrirga ({d1}) o'tishda nima o'zgardi?",
               "{d1} dagi tahrir {d0} dagidan nimasi bilan farq qiladi?"],
}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if 60 <= len(s.strip()) <= 400]


def changed_words(old: str, new: str) -> tuple[str, str]:
    a, b = old.split(), new.split()
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return " ".join(a[i:len(a) - j])[:300], " ".join(b[i:len(b) - j])[:300]


def _date(s: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def ondate(rng, u) -> tuple[str, str] | None:
    """A balanced 'was this wording in force on date D?' item (half yes, half no), from the edition's own dates."""
    start, end = _date(u["valid_from"]), _date(u["valid_to"]) or dt.date(2026, 11, 20)
    if start is None or end <= start:
        return None
    span = f"{start} dan" + (f" {u['valid_to']} gacha" if u["valid_to"] else " (hozirgacha)")
    if rng.random() < 0.5:
        d = start + dt.timedelta(days=rng.randint(0, (end - start).days))
        return d.isoformat(), f"Ha: bu tahrir {span} amalda."
    options = []
    if start > dt.date(1992, 1, 1):
        options.append(start - dt.timedelta(days=rng.randint(1, 900)))
    if u["valid_to"]:
        options.append(end + dt.timedelta(days=rng.randint(1, 900)))
    if not options:
        return None
    return rng.choice(options).isoformat(), f"Yo'q: bu tahrir {span} amalda."


def lesson(rng, a, u, prev, other: str | None = None) -> tuple[str, list[str]]:
    name, where = act_name(a), human_path(u["path"])
    head = f"{name}, {where}" + (f". {u['heading']}" if u["heading"] else "") + f" (tahrir {u['valid_from']} dan)"
    qa, kinds = [], []

    def ask(kind, answer, **kw):
        qa.append((rng.choice(T[kind]).format(**kw), answer))
        kinds.append(kind)

    if u["heading"] and len(u["heading"]) > 12:
        ask("heading", u["heading"])
    sents = sentences(u["text"])
    if sents:
        s = rng.choice(sents)
        words = s.split()
        if len(words) >= 10:
            k = rng.randint(3, len(words) - 4)
            n = min(4, len(words) - k - 1)
            ask("cloze", " ".join(words[k:k + n]), q=" ".join(words[:k] + ["____"] + words[k + n:]))
        ask("where", f"{name}, {where}", s=s[:240])
        # true/false, balanced: a false item is a changed number, the previous edition's wording, or a sentence
        # from another article (the pilot's 95 % "To'g'ri" taught a yes-bias: 119/120 "ha" on the exam)
        m = next((w for w in NUMS if re.search(rf"\b{w}\b", s)), None)
        old = [x for x in sentences(prev["text"]) if norm(x) not in norm(u["text"])] if prev else []
        if rng.random() < 0.5 and (m or old or other):
            if m and (rng.random() < 0.5 or not (old or other)):
                ask("tf", "Noto'g'ri: matnda «" + m + "».", s=re.sub(rf"\b{m}\b", NUMS[m], s, count=1)[:300])
            elif old:
                ask("tf", f"Noto'g'ri: bu oldingi tahrir ({prev['valid_from']}) matni; {u['valid_from']} dan o'zgargan.",
                    s=rng.choice(old)[:300])
            else:
                ask("tf", "Noto'g'ri: bu gap ushbu normada yo'q.", s=other[:300])
        else:
            ask("tf", "To'g'ri.", s=s[:300])
    ask("since", f"{u['valid_from']} dan" + (f" {u['valid_to']} gacha" if u["valid_to"] else " (hozirgacha)"))
    ask("force", FORCE[a["type"]])
    od = ondate(rng, u)
    if od:
        ask("ondate", od[1], d=od[0])
    if prev is not None and norm(prev["text"]) != norm(u["text"]):
        old, new = changed_words(prev["text"], u["text"])
        if old or new:
            ask("change", f"«{old or '—'}» o'rniga «{new or '—'}»", d0=prev["valid_from"], d1=u["valid_from"])
    rng.shuffle(qa)
    body = "\n".join(f"Savol: {q}\nJavob: {ans}" for q, ans in qa)
    return f"{head}\n\n{u['text']}\n\n{body}", kinds


def _rows_from_store():
    con = sqlite3.connect(LAW_DB)
    con.row_factory = sqlite3.Row
    acts = {r["act_key"]: r for r in con.execute("SELECT * FROM acts")}
    rows = con.execute("SELECT act_key, path, heading, text, valid_from, valid_to FROM units "
                       "WHERE length(text) >= 80 ORDER BY act_key, path, valid_from").fetchall()
    return acts, rows


def _rows_from_refinery(path: Path):
    """Refinery lesson inputs (07_train/lesson_inputs/*.jsonl[.gz]): rows already carry the act columns and
    the previous interval's text, container rows and held-out units are already removed."""
    from research.refinery.io import read_jsonl

    files = sorted(path.glob("*.jsonl*")) if path.is_dir() else [path]
    rows, acts = [], {}
    for f in (f for f in files if f.suffix in {".gz", ".jsonl"}):
        for r in read_jsonl(f):
            acts.setdefault(r["act_key"], {"type": r["type"], "title": r["title"], "number": r["number"]})
            rows.append(r)
    rows.sort(key=lambda r: (r["act_key"], r["path"], r["valid_from"] or ""))
    return acts, rows


def main(refinery: Path | None = None, out: Path = OUT) -> None:
    rng = random.Random(SEED)
    held = set()
    for line in BENCH.open(encoding="utf-8"):
        it = json.loads(line)
        if "path" in it and unseen(it["act"], it["path"]):
            held.add((it["act"], it["path"]))
    acts, rows = _rows_from_refinery(refinery) if refinery else _rows_from_store()
    n, kinds_all, skipped, chars = 0, Counter(), 0, 0
    prev = {}
    pool = deque(maxlen=400)  # sentences of recent other articles, for false true/false items
    answers = Counter()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for u in rows:
            key = (u["act_key"], u["path"])
            p = prev.get(key)
            if refinery:   # the refinery gives prev_text itself (previous interval of the same path)
                p = {"text": u["prev_text"], "valid_from": None} if u.get("prev_text") else None
                if p is not None:
                    pv = prev.get(key)
                    p["valid_from"] = pv["valid_from"] if pv else u["valid_from"]
            prev[key] = u
            if key in held:
                skipped += 1
                continue
            picks = [rng.choice(pool) for _ in range(3)] if pool else []
            other = next((s for k, s in picks if k != key), None)
            text, kinds = lesson(rng, acts[u["act_key"]], u, p, other)
            pool.extend((key, s) for s in sentences(u["text"])[:2])
            answers.update(re.findall(r"\nJavob: (To'g'ri|Noto'g'ri|Ha|Yo'q)", text))
            f.write(json.dumps({"text": text, "act": u["act_key"], "path": u["path"], "valid_from": u["valid_from"],
                                "kinds": kinds}, ensure_ascii=False) + "\n")
            n += 1
            chars += len(text)
            kinds_all.update(kinds)
    print(f"{out}: {n:,} lessons, {chars / 1e6:.1f}M characters (~{chars / 6.5 * 4 / 1e6:.1f}M tokens at 4 per word); "
          f"held out for the exam: {skipped:,}; tasks {dict(kinds_all)}; answer balance {dict(answers)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refinery", type=Path, default=None,
                    help="read refinery lesson inputs (dir or file under data/refinery/.../07_train/lesson_inputs) "
                         "instead of the SQLite store")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    main(args.refinery, args.out)
