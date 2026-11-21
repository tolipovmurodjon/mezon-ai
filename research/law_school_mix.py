"""Mix the law-school pilot: ~50 % law lessons, ~25 % Uzbek web text, ~25 % general instructions (replay).

    .venv/bin/python -X utf8 -m research.law_school_mix --law-tokens 6e6     # on the L40S, -> data/train/mix_pilot.jsonl

Inputs: data/train/law_school_pilot.jsonl (research/law_school_data.py), FineWeb-2 uzn_Latn (ODC-By) and the
Tulu 3 SFT mixture (ODC-BY-1.0) under data/raw/replay/. Why replay: training only on law makes the model forget how
to write normal Uzbek and follow instructions (research: 25-50 % replay for a language far from English).
Dropped from Tulu: no_robots (CC BY-NC) and tulu_hard_coded (it teaches the model to call itself "Tulu").
Every lesson of an exam "seen" article is kept; the rest of the law budget is a random sample. Tokens are estimated
from characters (Uzbek ~1.6 chars/token at ~4 tokens per word, English ~4 chars/token); the trainer counts exactly.
Each line: {"kind": "law"|"web"|"instr", "text": ...} or {"kind": "instr", "messages": [...]}; 100 of each kind
go to data/train/mix_pilot_val.jsonl for per-kind held-out loss.
"""

import argparse
import glob
import json
import random
from pathlib import Path

from research.mezonbench import OUT as BENCH
from research.mezonbench import unseen

ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "data" / "train" / "law_school_pilot.jsonl"
REPLAY = ROOT / "data" / "raw" / "replay"
OUT = ROOT / "data" / "train" / "mix_pilot.jsonl"
VAL = ROOT / "data" / "train" / "mix_pilot_val.jsonl"
DROP = ("no_robots", "hard_coded")
UZ_CHARS_PER_TOKEN, EN_CHARS_PER_TOKEN = 1.6, 4.0


def main() -> None:
    import pyarrow.parquet as pq

    ap = argparse.ArgumentParser()
    ap.add_argument("--law-tokens", type=float, default=6e6)
    a = ap.parse_args()
    rng = random.Random(11)
    seen = set()
    for line in BENCH.open(encoding="utf-8"):
        it = json.loads(line)
        if "path" in it and not unseen(it["act"], it["path"]):
            seen.add((it["act"], it["path"]))

    lessons = [json.loads(line) for line in LAW.open(encoding="utf-8")]
    must = [x for x in lessons if (x["act"], x["path"]) in seen]
    rest = [x for x in lessons if (x["act"], x["path"]) not in seen]
    rng.shuffle(rest)
    law, chars = list(must), sum(len(x["text"]) for x in must)
    for x in rest:
        if chars / UZ_CHARS_PER_TOKEN >= a.law_tokens:
            break
        law.append(x)
        chars += len(x["text"])
    law_tok = chars / UZ_CHARS_PER_TOKEN

    web, wchars = [], 0
    for f in sorted(glob.glob(str(REPLAY / "fineweb-2" / "data" / "uzn_Latn" / "train" / "*.parquet"))):
        texts = pq.read_table(f, columns=["text"]).column("text").to_pylist()
        rng.shuffle(texts)
        for t in texts:
            if wchars / UZ_CHARS_PER_TOKEN >= law_tok / 2:
                break
            if 300 <= len(t) <= 12000:
                web.append(t)
                wchars += len(t)

    instr, ichars = [], 0
    files = sorted(glob.glob(str(REPLAY / "tulu-3-sft-mixture" / "data" / "*.parquet")))
    rng.shuffle(files)
    for f in files:
        tb = pq.read_table(f, columns=["messages", "source"]).to_pylist()
        rng.shuffle(tb)
        for r in tb:
            if ichars / EN_CHARS_PER_TOKEN >= law_tok / 2:
                break
            if any(d in r["source"] for d in DROP):
                continue
            n = sum(len(m["content"] or "") for m in r["messages"])
            if 100 <= n <= 16000 and r["messages"][-1]["role"] == "assistant":
                instr.append([{"role": m["role"], "content": m["content"]} for m in r["messages"]])
                ichars += n

    rows = ([{"kind": "law", "text": x["text"]} for x in law] + [{"kind": "web", "text": t} for t in web]
            + [{"kind": "instr", "messages": m} for m in instr])
    rng.shuffle(rows)
    val, train, per = [], [], {"law": 0, "web": 0, "instr": 0}
    for r in rows:
        if per[r["kind"]] < 100:
            per[r["kind"]] += 1
            val.append(r)
        else:
            train.append(r)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in train)
    with VAL.open("w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in val)
    print(f"{OUT}: {len(train):,} rows | law {len(law):,} lessons ~{law_tok / 1e6:.1f}M tok (incl. {len(must)} "
          f"exam-seen) | web {len(web):,} docs ~{wchars / UZ_CHARS_PER_TOKEN / 1e6:.1f}M tok | instr {len(instr):,} "
          f"chats ~{ichars / EN_CHARS_PER_TOKEN / 1e6:.1f}M tok | val {len(val)}")


if __name__ == "__main__":
    main()
