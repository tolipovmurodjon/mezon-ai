"""Measure the OCR clean-up chain on finished OCR documents: raw markdown -> markup strip -> letter restoration ->
normalisation -> the filter decision. Reports how many documents pass the out-of-vocabulary gate.

    python -X utf8 -m research.refinery.ocr_eval --ids data/refinery/pilot_ids.jsonl [--vocab html|html+pdf] [--no-fix]

The vocabulary is built from clean text only: national HTML acts and (with `html+pdf`) text-PDF local decisions
that were read from the cache by the same extractor."""

import argparse
import json
from pathlib import Path

from research.refinery import config, filters
from research.refinery.extract_ocr import extract_ocr, ocr_correct, ocr_quality
from research.refinery.io import read_jsonl
from research.refinery.normalize import normalise, script_counts


def restore_blocks(blocks: list[dict], vocab: set[str], fix: bool = True) -> tuple[list[str], int]:
    """Texts of the blocks after letter restoration and normalisation, and the number of words restored."""
    texts, fixed = [], 0
    lat = cyr = 0
    parts = []
    for b in blocks:
        t = b["text"]
        if fix:
            t, n = ocr_correct(t, vocab)
            fixed += n
        parts.append(t)
        a, c = script_counts(t)
        lat, cyr = lat + a, cyr + c
    for t in parts:
        norm, _ = normalise(t, latin=lat >= cyr)
        if norm:
            texts.append(norm)
    return texts, fixed


def evaluate(keys: list[str], vocab: set[str], fix: bool = True, root: Path = config.OCR_DIR) -> dict:
    n = oov_pass = keep = fixed = 0
    oov_rates = []
    for key in keys:
        o = extract_ocr(key, root, vocab)
        if o is None:
            continue
        n += 1
        texts, nf = restore_blocks(o.units, vocab, fix)
        fixed += nf
        text = "\n".join(texts)
        q = ocr_quality(text, vocab)
        oov_rates.append(q["oov_rate"])
        oov_pass += q["oov_rate"] <= config.OOV_MAX
        sig = {
            "n_chars": len(text),
            "oov_rate": q["oov_rate"],
            "nonalnum_share": q["nonalnum_share"],
            "dup_line_share": 0,
            "top5gram_share": 0,
            "script_purity": 1,
            "mixed_share": 0,
        }
        keep += filters.decide(sig, "ocr", o.ocr_partial)[0] == "keep"
    oov_rates.sort()
    return {
        "docs": n,
        "oov_pass": oov_pass,
        "keep": keep,
        "words_restored": fixed,
        "median_oov": oov_rates[len(oov_rates) // 2] if oov_rates else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default=str(config.OUT / "pilot_ids.jsonl"))
    ap.add_argument("--pilot", default=str(config.OUT / "pilot"))
    ap.add_argument("--vocab", default="html", choices=["html", "html+pdf"])
    ap.add_argument("--no-fix", action="store_true")
    a = ap.parse_args()
    keys = [t["key"] for t in read_jsonl(Path(a.ids)) if t.get("kind") == "ocr"]
    from research.refinery.io import read_jsonl as rj

    def body(bl):
        return "\n".join(b["text"] for b in bl)

    texts = []
    for f in sorted((Path(a.pilot) / "01_extract" / "acts").glob("*.jsonl.gz")):
        for r in rj(f):
            if r["source_kind"] == "html" and r["meta"]["level"] == "national":
                texts.append(body(r["blocks"]))
            elif a.vocab == "html+pdf" and r["source_kind"] == "pdf_text":
                texts.append(body(r["blocks"]))
    vocab = filters.build_vocab(texts)
    print(json.dumps({"vocab_words": len(vocab), "vocab": a.vocab, "fix": not a.no_fix}))
    print(json.dumps(evaluate(keys, vocab, not a.no_fix), ensure_ascii=False))


if __name__ == "__main__":
    main()
