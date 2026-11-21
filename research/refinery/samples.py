"""Small human-readable samples and headline numbers from a pilot output directory (run on the box, copy back the
small files only): one national act document, one change note, one masked local decision snippet, the PII
context sample (masked text only), and the drop samples.

    python -X utf8 -m research.refinery.samples <pilot dir>"""

import json
import re
import sys
from pathlib import Path

from research.refinery.io import read_jsonl


def _rows(d: Path, sub: str):
    for f in sorted((d / "07_train" / sub).glob("*.jsonl.gz")):
        yield from read_jsonl(f)


def main(pilot: str) -> None:
    d = Path(pilot)
    out = d / "samples"
    out.mkdir(exist_ok=True)
    cpt = list(_rows(d, "cpt_docs"))
    nat = next(
        (
            r
            for r in cpt
            if r["tier"] == "A"
            and r["act_type"] == "law"
            and r["lang"] == "uz"
            and r["script"] == "Latn"
            and r["status"] == "in_force"
            and r["text"].count("\n") > 8
        ),
        None,
    )
    if nat:
        (out / "national_act.txt").write_text(nat["text"][:2500], encoding="utf-8")
    amend = list(_rows(d, "amendment_docs"))

    def score(r):
        t = r["text"]
        return (
            ("kuchini yoʻqotgan" in t) * 4 + ("koʻchirilgan" in t) * 4 + ("Asos:" in t) * 2 + ("Oldin" in t)
        )

    best = sorted(amend, key=lambda r: (-score(r), r["doc_id"]))[:3]
    if best:
        (out / "change_notes.txt").write_text(
            "\n\n=====\n\n".join(b["text"][:1800] for b in best), encoding="utf-8"
        )
    pii_report = {
        r["lex_id"]: r for f in sorted((d / "06_safe").glob("pii_report.jsonl.gz")) for r in read_jsonl(f)
    }
    loc = [
        r
        for r in cpt
        if r["source_kind"] == "pdf_text"
        and r["level"] == "local"
        and r["lang"] == "uz"
        and r["script"] == "Latn"
        and re.search(r"\[(?:FUQARO_\d|TELEFON|MANZIL|RAQAM)\]", r["text"])
        and r["pii"]
        and sum(pii_report.get(r["lex_id"], {}).get("counts", {}).values()) >= 2
    ]
    if loc:
        t0 = loc[0]["text"]
        i0 = re.search(r"\[(?:FUQARO_\d|TELEFON|MANZIL|RAQAM)\]", t0).start()
        snippet = t0[:260] + "\n[...]\n" + t0[max(260, i0 - 500) : i0 + 700]
        (out / "masked_local_decision.txt").write_text(snippet, encoding="utf-8")
    stats = json.loads((d / "stats.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {k: stats[k] for k in ("documents_extracted", "source_kinds", "pii_totals", "canary", "drops")},
            ensure_ascii=False,
            indent=1,
        )
    )
    print("samples:", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1])
