"""Training data for Mezon-LM v0, built only from verified material, never from the exam.

    .venv/Scripts/python.exe -X utf8 -m research.train_data

Writes data/train/:
  cpt.jsonl - {"text"}: every law unit version with its act, path and edition dates, plus every decision text
              (continued pre-training: legal Uzbek and how decisions are built). ~8M tokens.
  sft.jsonl - {"messages"}: decision -> Mezon's verified audit (verdict, flags, article, verbatim quote). The answer is
              the rule engine's output after the citation verifier, so v0 teaches the model our format and our checks;
              lawyer-confirmed flags replace and extend it as they arrive.
Every decision that appears in data/eval/mezon_bench_v0.jsonl is excluded from both files (no leakage).
"""

import json
import sqlite3
from pathlib import Path

from mezon.conclusion import _unit
from mezon.config import DECISIONS_DB, LAW_DB
from mezon.decisions.store import DecisionStore
from mezon.rules.run import audit, load_law

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "train"
BENCH = ROOT / "data" / "eval" / "mezon_bench_v0.jsonl"
SYSTEM = ("Siz Mezon: hokim va Kengash qarorlarini qabul qilingan sanadagi qonun tahriri bilan tekshiradigan yordamchisiz. "
          "Faqat aynan iqtibos va modda bilan javob bering; asos topilmasa \"noaniq, ekspert kerak\" deng. "
          "Belgilangan qaror noqonuniy degani emas: yakuniy qarorni ekspert qabul qiladi.")


def exam_regs() -> set[str]:
    regs = set()
    for line in BENCH.open(encoding="utf-8"):
        gold = json.loads(line)["gold"]
        regs.update(gold.get("reg_numbers") or [])
        if gold.get("reg_number"):
            regs.add(gold["reg_number"])
    return regs


def cpt(exclude: set[str]) -> int:
    law = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
    dec = sqlite3.connect(f"file:{DECISIONS_DB}?mode=ro", uri=True)
    titles = dict(law.execute("SELECT act_key, title FROM acts"))
    n = 0
    with (OUT / "cpt.jsonl").open("w", encoding="utf-8") as f:
        for key, path, text, vf, vt in law.execute(
                "SELECT act_key, path, text, valid_from, valid_to FROM units WHERE length(text) > 40"):
            head = f"{titles.get(key, key)} · {_unit(path)} · amalda: {vf} dan" + (f" {vt} gacha" if vt else " (hozir ham)")
            f.write(json.dumps({"text": f"{head}\n{text}"}, ensure_ascii=False) + "\n")
            n += 1
        for reg, title, adopted, text in dec.execute(
                "SELECT reg_number, title, adopted, text FROM decisions WHERE length(coalesce(text,'')) > 0"):
            if reg in exclude or any(x in text for x in exclude):  # the exam decision, or a text that names it
                continue
            f.write(json.dumps({"text": f"{reg} · {adopted} · {title}\n{text}"}, ensure_ascii=False) + "\n")
            n += 1
    return n


def answer(r: dict) -> str:
    flags = []
    for fl in r["flags"]:
        c = (fl.get("citations") or [{}])[0]
        flags.append({"kamchilik": fl.get("title_uz") or fl["title"],
                      "holat": "ehtimoliy qoidabuzarlik" if fl["status"] == "possible_violation" else "noaniq, ekspert kerak",
                      "qarordan": next((e["quote"] for e in fl.get("evidence") or [] if e.get("quote")), ""),
                      "asos": f"{c.get('act_title', '')}, {_unit(c.get('article', ''))} ({c.get('on_date', '')} holatiga)",
                      "iqtibos": c.get("quote", "")})
    return json.dumps({"xulosa": r["verdict"], "kamchiliklar": flags}, ensure_ascii=False)


def sft(exclude: set[str]) -> int:
    store, law = DecisionStore(), load_law()
    n = 0
    with (OUT / "sft.jsonl").open("w", encoding="utf-8") as f:
        for (i,) in store.con.execute("SELECT id FROM decisions WHERE role='adopted' AND length(coalesce(text,''))>0"):
            d = store.get(i)
            if d["reg_number"] in exclude or any(x in d["text"] for x in exclude):
                continue
            r = audit(i, law=law, decisions=store).to_dict()
            for fl in r["flags"]:
                fl.update(__import__("mezon.plain", fromlist=["explain"]).explain(fl, r))
            user = f"Qaror {d['reg_number']}, qabul qilingan: {d['adopted']}.\n{d['text'][:7000]}\n\nQarorni tekshiring."
            f.write(json.dumps({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user},
                                             {"role": "assistant", "content": answer(r)}]}, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exclude = exam_regs()
    print(f"excluded (exam) decisions: {len(exclude)}")
    print(f"cpt.jsonl: {cpt(exclude)} documents")
    print(f"sft.jsonl: {sft(exclude)} examples")


if __name__ == "__main__":
    main()
