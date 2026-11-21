"""Independent check of MezonBench answer keys against lex.uz's own edition pages (not our store or parser).

    .venv/bin/python -X utf8 -m research.bench_key_check 40        # on the L40S (edition HTML cache lives there)

For N random flip items: find the edition in force on the item's date (edition dates from the store), open that
edition's raw HTML from data/cache/lexuz/editions/, strip tags, fold, and check that the keyed option's text is in
it and the other option's text is not. Prints agree / disagree / undecidable with N and examples of disagreements.
"""

import html
import json
import random
import re
import sys
from pathlib import Path

from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "lexuz" / "editions"


def page_text(lex_id: str, ondate: str) -> str | None:
    name = ondate.replace(" ", "_") + ".html"
    for d in sorted(CACHE.glob(f"{lex_id.lstrip('-')}_*")):
        f = d / name
        if f.exists():
            raw = f.read_text(encoding="utf-8", errors="replace")
            return fold(html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    return None


def coverage(option: str, text: str, k: int = 6) -> float:
    """Share of the option's k-word pieces found in the page text (robust to dashes, spacing, cut-offs)."""
    w = re.findall(r"\w+", fold(option).lower())
    page = " ".join(re.findall(r"\w+", text.lower()))
    grams = [" ".join(w[i:i + k]) for i in range(len(w) - k + 1)]
    return round(sum(g in page for g in grams) / len(grams), 2) if grams else 0.0


def diff_parts(a: str, b: str, ctx: int = 3) -> tuple[str, str]:
    """The differing middle of two wordings, with ctx words of shared context on each side."""
    x, y = fold(a).split(), fold(b).split()
    i = 0
    while i < min(len(x), len(y)) and x[i] == y[i]:
        i += 1
    j = 0
    while j < min(len(x), len(y)) - i and x[-1 - j] == y[-1 - j]:
        j += 1
    s = max(0, i - ctx)
    return " ".join(x[s:len(x) - j + ctx]), " ".join(y[s:len(y) - j + ctx])


def options(prompt: str) -> dict[str, str]:
    out = {}
    for k in "AB":
        m = re.search(rf"^{k}\) (.+)$", prompt, re.MULTILINE)
        if m:
            out[k] = m.group(1).replace("…", " ").strip()
    return out


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
    meta = json.loads((ROOT / "data" / "bench" / "key_check_meta.json").read_text(encoding="utf-8"))
    eds = meta["editions"]
    items = [json.loads(x) for x in (ROOT / "data" / "bench" / "mezonbench_v1.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
    flips = [i for i in items if i["family"] == "flip"]
    random.Random(11).shuffle(flips)
    res = {"agree": 0, "disagree": 0, "undecidable": 0}
    bad = []
    for it in flips[:n]:
        ed = [e for e in eds if e["act_key"] == it["act"] and e["valid_from"] <= it["date"]
              and (e["valid_to"] is None or it["date"] < e["valid_to"])]
        opts = options(it["prompt"])
        text = page_text(meta["acts"][it["act"]], ed[-1]["ondate"]) if ed else None
        if not text or len(opts) < 2 or not all(opts.values()):
            res["undecidable"] += 1
            continue
        da, db = diff_parts(opts["A"], opts["B"])
        hit = {"A": coverage(da, text, 4), "B": coverage(db, text, 4)}
        other = "B" if it["answer"] == "A" else "A"
        if hit[it["answer"]] - hit[other] >= 0.15:
            res["agree"] += 1
        elif hit[other] - hit[it["answer"]] >= 0.15:
            res["disagree"] += 1
            bad.append((it["id"], it["act"], it["path"], it["date"], ed[-1]["ondate"], hit))
        else:
            res["undecidable"] += 1
    print(f"flip keys vs lex.uz edition pages, N={n}: {res}")
    for b in bad[:10]:
        print("  DISAGREE", b)


if __name__ == "__main__" and not (len(sys.argv) > 1 and sys.argv[1] == "in_force"):
    main()


def check_in_force() -> None:
    """in_force items on whole articles: does the article heading ("25-modda.") appear on the official page of the
    edition in force on the item's date? Compare with the key (ha / yo'q)."""
    meta = json.loads((ROOT / "data" / "bench" / "key_check_meta.json").read_text(encoding="utf-8"))
    eds = meta["editions"]
    items = [json.loads(x) for x in (ROOT / "data" / "bench" / "mezonbench_v1.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
    res = {"agree": 0, "disagree": 0, "undecidable": 0, "not_article": 0}
    bad = []
    for it in items:
        if it["family"] != "in_force":
            continue
        m = re.fullmatch(r"art:(\d+(?:-\d+)?)", it["path"])
        if not m:
            res["not_article"] += 1
            continue
        ed = [e for e in eds if e["act_key"] == it["act"] and e["valid_from"] <= it["date"]
              and (e["valid_to"] is None or it["date"] < e["valid_to"])]
        text = page_text(meta["acts"][it["act"]], ed[-1]["ondate"]) if ed else None
        if not text:
            res["undecidable"] += 1
            continue
        num = m.group(1)
        n_ = re.escape(num.replace("-", " "))  # fold() drops punctuation: "57-modda." -> "57 modda"
        present = re.search(rf"(?<!\d ){n_} modda\b", text) is not None
        lost = present and re.search(rf"(?<!\d ){n_} modda\W{{0,3}}(\w+\W+){{0,16}}(kuchini yo.?qotgan(?! deb)|chiqarib tashlangan)", text) is not None
        official = "ha" if present and not lost else "yo'q"
        key = fold(str(it["answer"])).lower().replace("'", "").replace("\u2019", "")
        if fold(official).lower().replace("'", "") == key:
            res["agree"] += 1
        else:
            res["disagree"] += 1
            bad.append((it["id"], it["act"], it["path"], it["date"], ed[-1]["ondate"], "key", it["answer"], "page", official))
    print(f"in_force keys (whole articles) vs lex.uz edition pages: {res}")
    for b in bad[:12]:
        print("  DISAGREE", b)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "in_force":
    check_in_force()
