"""Label local cancellation decisions by their official trigger (the protocol in CLAUDE.md, "Labels and samples")."""

import csv
import json
import re

from research import regnum, textnorm
from research.lexuz_crawl import INTERIM, load_text

# Official triggers are checked before the clean-up pattern: some decisions cite both (6421315).
# A sentence window: any character except a full stop, but a dot inside a number ("10.2/-22") does not end it.
W = r"(?:[^.]|\.(?=\d))"
TRIGGERS = [
    ("adliya representation", re.compile(rf"adliya{W}{{0,260}}?taqdimnoma|taqdimnoma{W}{{0,160}}?adliya")),
    ("adliya representation", re.compile(r"qonun hujjatlarining buzilishi,? ularning sabablari")),
    (
        "adliya letter",
        re.compile(rf"adliya (?:bo.?limi|boshqarmasi|vazirligi)\w*{W}{{0,200}}?(?:\bxati\b|xatiga|maktub)"),
    ),
    ("adliya monitoring", re.compile(rf"adliya{W}{{0,200}}?monitoring")),
    (
        "prosecutor protest",
        re.compile(rf"prokur\w*{W}{{0,260}}?(?:protest|taqdimnoma)|protest\w*{W}{{0,120}}?prokur"),
    ),
    ("court ruling", re.compile(r"hal qiluv qaror|haqiqiy emas deb topil")),
]
CLEANUP = re.compile(r"a[hx]amiyatini yoqotgan|pf.?6075\b|6075.?son")
# The body itself says the act broke the law ("qonun hujjatlariga zid ravishda qabul qilinganligi sababli"). Not an
# official trigger, so it stays REVIEW, but named, and checked before the clean-up pattern (found 19.11.2026: 2 texts).
SELF_ADMITTED = re.compile(
    r"qonun(?:chilik)? hujjatlari(?:ga|ning talablariga)? (?:muvofiq|mos) (?:bolmaganligi|kelmaganligi|emasligi)"
    r"|qonunchilik talablariga (?:zid|mos kelmas)\w*|qonun(?:chilik)? hujjatlariga zid"
)


def prepared(text: str) -> str:
    """Latin, lowercase, apostrophes removed, punctuation kept (sentence windows still work)."""
    return textnorm.normalize(text).lower().replace("'", "")


def label(title: str, text: str) -> tuple[str, str, str]:
    t = prepared(f"{title}. {text}")
    for trigger, rx in TRIGGERS:
        if m := rx.search(t):
            return "POSITIVE", trigger, t[max(0, m.start() - 80) : m.end() + 120]
    if m := SELF_ADMITTED.search(t):
        return "REVIEW", "self-admitted non-conformity (lawyer decides)", t[max(0, m.start() - 80) : m.end() + 120]
    if m := CLEANUP.search(t):
        return "EXCLUDE", "clean-up of outdated acts (PF-6075)", t[max(0, m.start() - 80) : m.end() + 120]
    return "REVIEW", "other trigger", t[:200]


def cancelled_numbers(title: str, own_number: str | None) -> list[str]:
    return [h["raw"] for h in regnum.find_all(title) if h["raw"] != (own_number or "")]


def main() -> None:
    titles = {h["id"]: h for h in json.loads((INTERIM / "cancel_titles.json").read_text(encoding="utf-8"))}
    docs = json.loads((INTERIM / "cancel_docs.json").read_text(encoding="utf-8"))
    rows, counts = [], {}
    for d in docs:
        text = load_text(d["id"])
        if not text:
            continue
        h = titles.get(d["id"], {})
        title = d.get("title") or h.get("title", "")
        lab, trig, ev = label(title, text)
        counts[lab] = counts.get(lab, 0) + 1
        rows.append(
            {
                "lex_uz_id": d["id"],
                "url": d["url"],
                "title": title,
                "body": h.get("body"),
                "date": d.get("date"),
                "number": d.get("number"),
                "trigger": trig,
                "evidence_snippet": re.sub(r"\s+", " ", ev),
                "label": lab,
                "cancelled_numbers": ";".join(cancelled_numbers(title, d.get("number"))),
            }
        )
    with open(INTERIM / "cancellation_labels.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"labeled {len(rows)}: {counts}")


if __name__ == "__main__":
    main()
