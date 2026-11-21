"""MezonBench "where": a sentence of law, no address given -> which act and which article? (the expert's real job).

    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_where build        # -> data/bench/mezonbench_where_v1.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_where score preds.jsonl

Lookup with tools is plumbing (the question names act, article and date). Here the model gets one sentence from an
article in force today, from the UNSEEN half of the store only (never in any training lesson), and must name the act
and the article. Graded automatically: right if the answer names the act (its number, or 3+ distinctive title words)
and the article number. Sentences that occur in more than one unit of the store are skipped (no ambiguous items).
"""

import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from mezon.config import LAW_DB
from research.mezonbench import act_name, human_path, norm, unseen, wilson
from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bench" / "mezonbench_where_v1.jsonl"
N = 60
SYSTEM = ("Siz O'zbekiston qonunchiligi bo'yicha ekspertsiz. Berilgan norma qaysi hujjatning qaysi moddasida "
          "ekanini aniqlang. Bilmasangiz \"noaniq\" deb yozing.")
STOP = {"ozbekiston", "respublikasining", "respublikasi", "togrisida", "haqida", "qonun", "kodeksi", "qarori", "farmoni", "tasdiqlash"}


def build() -> None:
    con = sqlite3.connect(LAW_DB)
    con.row_factory = sqlite3.Row
    acts = {r["act_key"]: dict(r) for r in con.execute("SELECT * FROM acts")}
    rows = con.execute("SELECT act_key, path, text FROM units WHERE valid_to IS NULL AND path LIKE 'art:%' "
                       "AND length(text) BETWEEN 200 AND 3000").fetchall()
    by_art: dict[tuple[str, str], str] = {}  # one text per (act, article): parts repeat their article's words
    for u in con.execute("SELECT act_key, path, text FROM units WHERE valid_to IS NULL"):
        m = re.match(r"(art:\d+(?:-\d+)?|annex:\d+|[^/]+)", u["path"])
        k = (u["act_key"], m.group(1) if m else u["path"])
        by_art[k] = by_art.get(k, "") + " " + norm(u["text"])
    rng = random.Random(21)
    rng.shuffle(rows)
    items, per_act = [], Counter()
    for r in rows:
        if len(items) >= N or not unseen(r["act_key"], r["path"]) or per_act[r["act_key"]] >= 6:
            continue
        sents = [s.strip() for s in re.split(r"(?<=[.;])\s+", r["text"]) if 80 <= len(s.strip()) <= 260]
        if not sents:
            continue
        s = rng.choice(sents)
        art = re.match(r"art:(\d+(?:-\d+)?)", r["path"]).group(1)
        ns = norm(s)
        if sum(ns in v for v in by_art.values()) != 1:  # the sentence must belong to exactly one article
            continue
        a = acts[r["act_key"]]
        items.append({"id": f"where-{len(items) + 1:03d}", "family": "where", "system": SYSTEM,
                      "prompt": f"Quyidagi norma qaysi hujjatning qaysi moddasida?\n«{s}»\n"
                                f"Javob shakli: <hujjat nomi yoki raqami>, <N>-modda.",
                      "act": r["act_key"], "path": r["path"], "article": art, "act_number": a["number"] or "",
                      "act_title": a["title"], "answer": f"{act_name(a)} {human_path(r['path'])}"})
        per_act[r["act_key"]] += 1
    OUT.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(items)} items from {len(per_act)} acts (unseen half only): {dict(per_act)}")


def grade(item: dict, answer: str) -> str:
    a = fold(answer or "").lower()
    if "noaniq" in a:
        return "abstain"
    # article on the raw answer: fold() merges "O'RQ-378) 23-modda" into "orq 378 23 modda"
    art_pat = r"[\s-]*".join(map(re.escape, item["article"].split("-")))
    art_ok = re.search(rf"(?<![\d-]){art_pat}[\s-]*(modda|модда|статья|статьи)", (answer or "").lower()) is not None
    num = re.sub(r"[^0-9a-z]", "", fold(item["act_number"]).lower())
    num_ok = bool(num) and num in re.sub(r"[^0-9a-z]", "", a)
    words = [w for w in re.findall(r"[a-z]{3,}", fold(item["act_title"]).lower().replace("'", "")) if w not in STOP]
    title_ok = bool(words) and sum(w in a.replace("'", "") for w in words) >= min(3, len(words))
    return "right" if art_ok and (num_ok or title_ok) else "wrong"


def score(pred_path: str) -> None:
    items = {json.loads(x)["id"]: json.loads(x) for x in OUT.read_text(encoding="utf-8").split("\n") if x.strip()}
    preds = {json.loads(x)["id"]: json.loads(x).get("answer", "")
             for x in Path(pred_path).read_text(encoding="utf-8").split("\n") if x.strip()}
    c = Counter(grade(items[i], preds[i]) for i in items if i in preds)
    n = sum(c.values())
    lo, hi = wilson(c["right"], n)
    print(f"where  N={n}  right {c['right']}  wrong {c['wrong']}  abstain {c['abstain']}  "
          f"acc {c['right'] / max(n, 1):.3f}  95% CI [{lo:.3f}, {hi:.3f}]")


if __name__ == "__main__":
    {"build": build, "score": lambda: score(sys.argv[2])}[sys.argv[1]]()
