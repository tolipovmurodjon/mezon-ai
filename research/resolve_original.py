"""For each POSITIVE cancellation, find the cancelled (original) decision on lex.uz and fetch its text."""

import csv
import re
from urllib.parse import quote

from research import regnum
from research.lexuz_crawl import BASE, INTERIM, LOCAL_RE, fetch_doc, load_text, parse_hits
from research.polite_http import fetch


def _canon(num: str) -> str:
    return re.sub(r"\s+", "", num or "").upper()


def find_by_number(number: str) -> dict | None:
    url = f"{BASE}/uz/search/all?actnum={quote(number)}"
    page = fetch(url, "lexuz", key=f"actnum/{re.sub(r'[^0-9A-Za-z]+', '_', number)}.html").decode(
        "utf-8", "replace"
    )
    hits = [
        h for h in parse_hits(page) if _canon(h["number"]) == _canon(number) and LOCAL_RE.search(h["badge"])
    ]
    return hits[0] if hits else None


def candidates(row: dict) -> list[str]:
    nums = [n for n in row["cancelled_numbers"].split(";") if n]
    if not nums:
        own = row.get("number") or ""
        nums = [h["raw"] for h in regnum.find_all(load_text(row["lex_uz_id"])[:4000]) if h["raw"] != own]
    return list(dict.fromkeys(nums))[:2]


def main() -> None:
    with open(INTERIM / "cancellation_labels.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] == "POSITIVE"]
    out = []
    for r in rows:
        rec = {
            "cancelling_id": r["lex_uz_id"],
            "cancelling_url": r["url"],
            "trigger": r["trigger"],
            "original_number": "",
            "original_id": "",
            "original_url": "",
            "original_date": "",
            "original_title": "",
            "original_text_chars": 0,
            "resolved": False,
        }
        for num in candidates(r):
            hit = find_by_number(num)
            if not hit:
                continue
            doc = fetch_doc(hit["id"])
            rec |= {
                "original_number": num,
                "original_id": hit["id"],
                "original_url": doc.get("url", ""),
                "original_date": doc.get("date") or hit.get("date") or "",
                "original_title": doc.get("title") or hit["title"],
                "original_text_chars": doc.get("text_chars", 0),
                "resolved": bool(doc.get("text_source")),
            }
            break
        if not rec["original_number"]:
            rec["original_number"] = ";".join(candidates(r))
        out.append(rec)
    with open(INTERIM / "positive_originals.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    ok = sum(r["resolved"] for r in out)
    print(f"originals resolved with text: {ok}/{len(out)} = {ok / max(len(out), 1):.1%}")


if __name__ == "__main__":
    main()
