"""Join regulation.gov.uz local drafts to adopted local decisions on lex.uz (same body, title similarity >= 0.9).
Inputs are the two CSVs written by research/v3_extract.py on the GPU box (data/bench/v3_src/)."""

import csv
import datetime as dt
import re
from collections import defaultdict
from pathlib import Path

from research.textnorm import fold, similarity

SRC = Path(__file__).resolve().parents[1] / "data" / "bench" / "v3_src"
_PLACE = re.compile(r"(\w+)\s+(tuman|shahar|viloyat)\w*")


def place(text: str) -> str | None:
    """Most specific place named in a body/creator string ('xorazm viloyati bogot tumani' -> 'bogot tuman')."""
    hits = _PLACE.findall(fold(text))
    return " ".join(hits[-1]) if hits else None


def kind(text: str) -> str | None:
    f = fold(text)
    if "kengash" in f:
        return "kengash"
    if "hokim" in f:
        return "hokim"
    return None


def day(s: str, fmt: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(s, fmt).date()
    except (ValueError, TypeError):
        return None


def digits(t: str) -> tuple:
    return tuple(sorted(re.findall(r"\d+", fold(t))))


def load() -> tuple[list[dict], list[dict]]:
    decs = []
    for r in csv.DictReader((SRC / "lex_local_catalog.csv").open(encoding="utf-8")):
        if "Oliy" in r["body"] or not r["number"]:
            continue
        p, k, a = place(r["body"]), kind(r["body"]), day(r["adopted"], "%d.%m.%Y")
        if p and k and a:
            decs.append({**r, "place": p, "kind": k, "adopted_d": a, "ft": fold(r["title"])})
    drafts = []
    for r in csv.DictReader((SRC / "reg_drafts_local.csv").open(encoding="utf-8")):
        p, k = place(r["creator"]), kind(r["creator"])
        s, e = day(r["start"], "%d/%m/%Y"), day(r["end"], "%d/%m/%Y")
        if p and k and s and e and e >= s:
            drafts.append({**r, "place": p, "kind": k, "start_d": s, "end_d": e, "ft": fold(r["title"])})
    return decs, drafts


def match(decs: list[dict], drafts: list[dict], thr: float = 0.9) -> list[dict]:
    """One-to-one matches only: the decision's single best draft and that draft's single best decision agree,
    the runner-up is clearly worse (< thr), the numbers in the titles are equal, and the decision was adopted
    from the discussion start to 180 days after its end."""
    by = defaultdict(list)
    for d in drafts:
        by[(d["place"], d["kind"])].append(d)
    cand = defaultdict(list)  # decision id -> [(sim, draft)]
    back = defaultdict(list)
    for x in decs:
        for d in by.get((x["place"], x["kind"]), []):
            if not (d["start_d"] <= x["adopted_d"] <= d["end_d"] + dt.timedelta(days=180)):
                continue
            if digits(x["title"]) != digits(d["title"]):
                continue
            s = similarity(x["ft"], d["ft"])
            if s >= thr:
                cand[x["lex_id"]].append((s, d))
                back[d["id"]].append((s, x))
    out = []
    for x in decs:
        c = cand.get(x["lex_id"])
        if not c or len(c) != 1:
            continue
        s, d = c[0]
        if len(back[d["id"]]) != 1:
            continue
        out.append({"sim": round(s, 3), "draft": d, "decision": x})
    return out


if __name__ == "__main__":
    decs, drafts = load()
    m = match(decs, drafts)
    print(len(decs), "decisions", len(drafts), "drafts ->", len(m), "clean matches")
    import collections

    gaps = collections.Counter()
    for r in m:
        d, x = r["draft"], r["decision"]
        length = (d["end_d"] - d["start_d"]).days
        gaps[(length >= 15, x["adopted_d"] > d["end_d"])] += 1
    print(gaps)
