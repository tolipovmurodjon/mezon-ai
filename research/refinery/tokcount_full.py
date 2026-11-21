"""Exact token counts of the refinery's training shards with a local tokenizer.json (the refinery's token counter,
`tokcount.py`, samples 500 documents per language; this one counts every document).

    ~/vllm-venv/bin/python -X utf8 research/refinery/tokcount_full.py <full dir> <tokenizer.json> [more .jsonl files]

Counts `text` of 07_train/{cpt_docs,cpt_original_edition,amendment_docs,status_docs} per language-script, and the
`text` field of any extra JSONL file (the law-school lessons). Writes <full dir>/tokens.json. Set
RAYON_NUM_THREADS=2 to stay small on the shared box."""

import glob
import gzip
import json
import sys
from collections import Counter


def rows(path: str):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def count(tok, texts: list[str]) -> int:
    return sum(len(e.ids) for e in tok.encode_batch(texts))


def main(full: str, tok_path: str, extra: list[str]) -> None:
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(tok_path)
    out: dict = {}
    for name in ("cpt_docs", "cpt_original_edition", "amendment_docs", "status_docs"):
        toks: Counter = Counter()
        words: Counter = Counter()
        docs: Counter = Counter()
        buf: list[tuple[str, str]] = []

        def flush(buf=buf, toks=toks):
            if not buf:
                return
            for (k, _), e in zip(buf, tok.encode_batch([t for _, t in buf]), strict=True):
                toks[k] += len(e.ids)
            buf.clear()

        for f in sorted(glob.glob(f"{full}/07_train/{name}/*.jsonl.gz")):
            for r in rows(f):
                k = f"{r.get('lang', '?')}-{r.get('script', '?')}"
                buf.append((k, r["text"]))
                words[k] += len(r["text"].split())
                docs[k] += 1
                if len(buf) >= 256:
                    flush()
        flush()
        out[name] = {
            "rows": dict(docs),
            "words": dict(words),
            "tokens": dict(toks),
            "tokens_total": sum(toks.values()),
        }
        print(name, out[name]["tokens_total"], flush=True)
    for path in extra:
        n = t = 0
        buf2: list[str] = []
        for r in rows(path):
            buf2.append(r["text"])
            n += 1
            if len(buf2) >= 256:
                t += count(tok, buf2)
                buf2 = []
        t += count(tok, buf2) if buf2 else 0
        out[path] = {"rows": n, "tokens_total": t}
        print(path, t, flush=True)
    with open(f"{full}/tokens.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
