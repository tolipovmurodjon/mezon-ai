"""Pattern A3: near-identical decisions in force at once, and repeals of acts that were already repealed."""

import csv
import json
import random
import re
import sys
from datetime import datetime
from itertools import combinations, pairwise

from research import regnum, textnorm
from research.lexuz_crawl import BASE, INTERIM, fetch_doc, load_text, search_url
from research.polite_http import ROOT

SIM_MIN = 0.95
MIN_OPERATIVE_CHARS = 200
REPEAL_VERB = re.compile(r"kuchini yo.?qotgan deb|bekor qilinsin", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.;](?!\d)")


def _date(s: str | None) -> datetime | None:
    return datetime.strptime(s, "%d.%m.%Y") if s else None


BODIES = {
    10452: "Qarshi tumani hokimi",
    12199: "Sherobod tumani hokimi",
    12498: "Guliston tuman hokimi",
    10335: "Kitob tumani hokimi",
    10422: "Yakkabog' tumani hokimi",
    11576: "Farg'ona shahar hokimi",
    9962: "Toshkent shahri hokimi",
    12043: "Termiz shahar hokimi",
    20452: "Nukus shahar hokimi",
    9938: "Toshkent shahar Kengashi",
    14870: "Jarqo'rg'on tumani Kengashi",
    19641: "Ellikqal'a tumani Kengashi",
}
CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def collect(body_id: int, since: str = "01.01.2024", max_pages: int = 5) -> list[dict]:
    """Decisions of one issuing body adopted since a date (public search: body_id + from), one per language pair."""
    _, found = search_url(
        f"{BASE}/uz/search/all?body_id={body_id}&from={since}", f"body/{body_id}_{since}", max_pages
    )
    best: dict[str, dict] = {}
    for h in found:
        key = h["id"].lstrip("-")
        if key not in best or (not CYRILLIC.search(h["badge"]) and CYRILLIC.search(best[key]["badge"])):
            best[key] = h
    return list(best.values())


def repealed_numbers(text: str, own: str) -> set[str]:
    nums = set()
    for sentence in SENTENCE_END.split(textnorm.normalize(text)):
        if REPEAL_VERB.search(sentence):
            nums |= {h["raw"] for h in regnum.find_all(sentence)}
    return nums - {own}


def analyse(docs: list[dict]) -> list[dict]:
    flags = []
    feats = {}
    for d in docs:
        text = load_text(d["id"])
        if not text:
            continue
        s = textnorm.split_decision(text)
        feats[d["id"]] = {
            "op": textnorm.shingles(s["operative"]),
            "op_len": len(s["operative"]),
            "annex": set(s["annex"].split()),
            "repeals": repealed_numbers(text, d.get("number") or ""),
        }
    by_body: dict[str, list[dict]] = {}
    for d in docs:
        p = regnum.parse(d.get("number") or "")
        if p and d["id"] in feats:
            by_body.setdefault(f"{p['region']}-{p['district']}-{p['type']}", []).append(d)

    for body, ds in by_body.items():
        ds.sort(key=lambda d: (_date(d.get("date")) or datetime.min, d["id"]))
        for old, new in combinations(ds, 2):
            fo, fn = feats[old["id"]], feats[new["id"]]
            if min(fo["op_len"], fn["op_len"]) < MIN_OPERATIVE_CHARS:
                continue
            a, b = fo["op"], fn["op"]
            # Jaccard >= SIM_MIN is impossible unless the set sizes are within that ratio.
            if min(len(a), len(b)) < SIM_MIN * max(len(a), len(b)):
                continue
            sim = len(a & b) / len(a | b)
            if sim < SIM_MIN:
                continue
            lost = _date(old.get("lost_force"))
            new_date = _date(new.get("date"))
            if lost and new_date and lost <= new_date:
                continue
            if old["number"] in fn["repeals"]:
                continue
            annex = (
                len(fo["annex"] & fn["annex"]) / len(fo["annex"] | fn["annex"])
                if fo["annex"] and fn["annex"]
                else None
            )
            flags.append(
                _flag("near-identical decision while the older one is in force", body, old, new, sim, annex)
            )
        repealers: dict[str, list[dict]] = {}
        for d in ds:
            for x in feats[d["id"]]["repeals"]:
                repealers.setdefault(x, []).append(d)
        for x, rs in repealers.items():
            for earlier, later in pairwise(rs):
                if earlier["date"] == later["date"]:
                    continue
                f = _flag(
                    f"repeals {x}, already repealed by {earlier['number']}", body, earlier, later, None, None
                )
                flags.append(f | {"repealed_number": x})
    return flags


def _flag(reason: str, body: str, old: dict, new: dict, sim: float | None, annex: float | None) -> dict:
    return {
        "reason": reason,
        "body": body,
        "newer_number": new["number"],
        "newer_date": new.get("date"),
        "newer_url": new["url"],
        "older_number": old["number"],
        "older_date": old.get("date"),
        "older_url": old["url"],
        "older_lost_force": old.get("lost_force"),
        "operative_sim": round(sim, 3) if sim is not None else "",
        "annex_bag_sim": round(annex, 3) if annex is not None else "",
        "repealed_number": "",
    }


def main() -> None:
    bodies = [int(b) for b in sys.argv[1:]] or list(BODIES)
    docs = []
    for body_id in bodies:
        hits = collect(body_id)
        print(f"{BODIES.get(body_id, body_id)}: {len(hits)} decisions on lex.uz since 2024", flush=True)
        for h in hits:
            d = fetch_doc(h["id"])
            docs.append(
                d
                | {
                    "number": d.get("number") or h["number"],
                    "date": d.get("date") or h["date"],
                    "body_name": BODIES.get(body_id, str(body_id)),
                }
            )
    (INTERIM / "district_docs.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    with_text = sum(1 for d in docs if d.get("text_source"))
    print(f"decisions scanned: {len(docs)}, with text: {with_text}", flush=True)

    flags = analyse(docs)
    fields = list(_flag("", "", {"number": "", "url": ""}, {"number": "", "url": ""}, None, None))
    with open(INTERIM / "duplicate_flags.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(flags)
    sample = random.Random(7).sample(flags, min(10, len(flags)))
    with open(ROOT / "research" / "flags_for_lawyer_A3.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["lawyer_verdict", "lawyer_note"])
        w.writeheader()
        w.writerows([s | {"lawyer_verdict": "", "lawyer_note": ""} for s in sample])
    kinds = {}
    for fl in flags:
        k = "near-identical" if fl["reason"].startswith("near") else "double repeal"
        kinds[k] = kinds.get(k, 0) + 1
    print(f"flags: {len(flags)} {kinds}")
    golden = [fl for fl in flags if fl["newer_number"] == "231-4-59-Q/24"]
    print("golden Qarshi flags:", [(fl["reason"], fl["older_number"], fl["operative_sim"]) for fl in golden])


if __name__ == "__main__":
    main()
