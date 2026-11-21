"""Tokens per word per script on the pilot output (design 11, item 9). Standalone: needs only the `tokenizers` package
(the box has it in ~/vllm-venv) and a local tokenizer.json; reads the pilot's cpt_docs shards, writes one JSON file.

    ~/vllm-venv/bin/python -X utf8 research/refinery/tokcount.py <pilot dir> <tokenizer.json>

Also settles the apostrophe question: the same texts with U+02BB / U+02BC replaced by ASCII ' are tokenised again."""

import glob
import gzip
import json
import random
import re
import sys
from collections import defaultdict


def main(pilot: str, tok_path: str, per_group: int = 500) -> None:
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(tok_path)
    groups: dict[str, list[str]] = defaultdict(list)
    for f in sorted(glob.glob(f"{pilot}/07_train/cpt_docs/*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                groups[f"{r['lang']}-{r['script']}"].append(r["text"])
    rng = random.Random(7)
    out = {}
    for g, texts in sorted(groups.items()):
        rng.shuffle(texts)
        sample = texts[:per_group]
        words = sum(len(t.split()) for t in sample)
        toks = sum(len(tok.encode(t).ids) for t in sample)
        row = {
            "docs": len(sample),
            "words": words,
            "tokens": toks,
            "tokens_per_word": round(toks / max(words, 1), 3),
        }
        if g.endswith("Latn"):
            ascii_t = [re.sub("[ʻʼ]", "'", t) for t in sample]
            toks_a = sum(len(tok.encode(t).ids) for t in ascii_t)
            row["tokens_per_word_ascii_apostrophe"] = round(toks_a / max(words, 1), 3)
        out[g] = row
    with open(f"{pilot}/tokens_per_word.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
