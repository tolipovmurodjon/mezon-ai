"""Mezon Uzbek Legal Benchmark v0: questions whose answers the law store and our labels already verify.

    .venv/Scripts/python.exe -X utf8 -m research.benchmark

Writes data/eval/mezon_bench_v0.jsonl. Every item: id, type, question_uz, answer (short, checkable), gold (structured),
source (lex.uz URL). Types:
  A point_in_time  - was article N of act X in force on date D? (yes and no cases, from the editions table)
  B dead_basis     - does decision R rest on an article that was not in force on its date? (R_basis flags + clean controls)
  C law_change     - which decisions still in force cite an article changed on date D? (/api/law-changes)
This is an exam: never train on it. Answers are from data, not from a model; a lawyer still spot-checks a sample.
"""

import csv
import json
import random
from pathlib import Path

from mezon.decisions.store import DecisionStore
from mezon.rules.basis import _repeal_notes
from mezon.rules.run import load_law

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "mezon_bench_v0.jsonl"
FLAGS = ROOT / "data" / "interim" / "rule_flags.csv"
NAMES = {"lsp": "Mahalliy davlat hokimiyati to'g'risidagi Qonun", "budgetcode": "Budjet kodeksi",
         "nla": "Normativ-huquqiy hujjatlar to'g'risidagi Qonun", "taxcode": "Soliq kodeksi", "landcode": "Yer kodeksi"}


def point_in_time(law, rng) -> list[dict]:
    items = []
    for key, notes in _repeal_notes().items():
        if key not in NAMES:
            continue
        for num, note in notes.items():
            for on, expect in (("2018-06-01", None), ("2025-11-13", False)):
                if law.edition_on(key, on) is None or law.edition_gap(key, on):
                    continue  # act not yet in existence, or the store skipped editions around that date: answer unknowable
                unit = law.get_unit(key, f"art:{num}", on)
                state = unit is not None
                if expect is not None and state != expect:
                    continue
                items.append({"type": "point_in_time",
                              "question_uz": f"{NAMES[key]}ning {num}-moddasi {on} holatida amalda bo'lganmi?",
                              "answer": "ha" if state else "yo'q",
                              "gold": {"act": key, "article": num, "on": on, "in_force": state, "note": note["note"][:160]},
                              "source": note["url"]})
    rng.shuffle(items)
    return items[:60]


def dead_basis(store, rng) -> list[dict]:
    rows = list(csv.DictReader(FLAGS.open(encoding="utf-8-sig")))
    flagged = {r["decision_id"] for r in rows if r["check"] == "R_basis"}
    any_flag = {r["decision_id"] for r in rows}
    items = []
    for did in sorted(flagged):
        d = store.get(did)
        if d:
            items.append((d, "ha"))
    clean = [i for (i,) in store.con.execute("select id from decisions where role='adopted' and length(coalesce(text,''))>0")
             if i not in any_flag]
    rng.shuffle(clean)
    for did in clean[: len(items)]:
        items.append((store.get(did), "yo'q"))
    return [{"type": "dead_basis",
             "question_uz": f"{d['reg_number']} raqamli qaror ({d['adopted']}) qabul qilingan kuni kuchini yo'qotgan "
                            "modda yoki hujjatga tayanganmi?",
             "answer": ans, "gold": {"reg_number": d["reg_number"], "adopted": d["adopted"],
                                     "label_source": "edition check in the Mezon law store (acts it holds); "
                                                     + ("verified by lex.uz's repeal note" if ans == "ha" else "no flag of any kind")},
             "source": d.get("url", "")}
            for d, ans in items]


def law_change() -> list[dict]:
    from mezon.api.main import law_changes
    r = law_changes(since="2026-11-12", limit=200)
    if not r["total"]:
        return []
    regs = sorted({i["reg_number"] for i in r["items"]})
    first = r["items"][0]
    return [{"type": "law_change",
             "question_uz": f"{first['changed_on']} da {first['act']} {first['articles']} o'zgardi. Mezon bazasidagi "
                            "qaysi amaldagi qarorlar shu moddaga tayanadi va qayta tekshirilishi kerak?",
             "answer": ", ".join(regs), "gold": {"reg_numbers": regs, "changed_on": first["changed_on"]},
             "source": first["url"]}]


def main() -> None:
    rng = random.Random(20261119)
    law, store = load_law(), DecisionStore()
    items = point_in_time(law, rng) + dead_basis(store, rng) + law_change()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            f.write(json.dumps({"id": f"mzb-{n:04d}", "split": "test", **it}, ensure_ascii=False) + "\n")
    by = {}
    for it in items:
        by[it["type"]] = by.get(it["type"], 0) + 1
    print(f"{len(items)} items -> {OUT}  {by}")


if __name__ == "__main__":
    main()
