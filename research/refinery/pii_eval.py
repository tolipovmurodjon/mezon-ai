"""Measure the citizen masker on the documents of a pilot run: how many name masks sit in a line that also names a
public position (a commission table row 'Karimov A. | tuman hokimi'), which is an official that must stay.

    python -X utf8 -m research.refinery.pii_eval [--pilot data/refinery/pilot]

Reads the pre-masking text of stage 03 (`03_norm/docs.jsonl.gz`); prints counts only, never a name."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from research.refinery import pii
from research.refinery.io import read_jsonl
from research.refinery.sample import SENSITIVE
from research.textnorm import fold

TITLE = re.compile(
    r"hokim|oʻrinbosar|o'rinbosar|boshligʻi|boshlig'i|boshliq|rais|aʼzo|a'zo|deputat|direktor|mudir|rahbar|vazir|"
    r"prokuror|ҳоким|ўринбосар|бошлиғи|бошлиқ|раис|аъзо|депутат|директор|мудир|раҳбар|вазир|прокурор",
    re.IGNORECASE,
)
TOKEN = re.compile(r"\[FUQARO_\d+\]")


def line_stats(text_before: str, text_after: str) -> dict:
    """Name masks per source line: how many fall in a line with a position title (over-masking candidates)."""
    out: Counter = Counter()
    for old, new in zip(text_before.split("\n"), text_after.split("\n"), strict=False):
        n = len(TOKEN.findall(new))
        if not n:
            continue
        out["name_masks"] += n
        if TITLE.search(old):
            out["in_title_line"] += n
            out["title_lines"] += 1
    return dict(out)


def evaluate(pilot: Path) -> dict:
    docs = list(read_jsonl(pilot / "03_norm" / "docs.jsonl.gz"))
    meta = {}
    for f in sorted((pilot / "01_extract" / "acts").glob("*.jsonl.gz")):
        for r in read_jsonl(f):
            meta[r["lex_id"]] = (r["meta"]["level"], r["source_kind"], r["meta"].get("title", ""))
    texts = [(d["lex_id"], [b["text"] for b in d["blocks"]]) for d in docs]
    local = [
        (lid, bl) for lid, bl in texts if lid in meta and (meta[lid][0] == "local" or meta[lid][1] == "ocr")
    ]
    df = pii.document_frequency(["\n".join(bl) for _, bl in local])
    tot: Counter = Counter()
    n_docs = 0
    for lid, bl in local:
        names: dict[str, int] = {}
        sens = bool(SENSITIVE.search(fold(meta[lid][2])))
        for t in bl:
            m, _ = pii.mask(t, "local", df, names=names, sensitive=sens)
            tot.update(line_stats(t, m))
        n_docs += 1
    tot["docs"] = n_docs
    return dict(tot)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="data/refinery/pilot")
    a = ap.parse_args()
    print(json.dumps(evaluate(Path(a.pilot))))


if __name__ == "__main__":
    main()
