"""A2: local drafts on regulation.gov.uz whose own entry-into-force date falls before their public discussion ends."""

import csv
import datetime as dt
import html
import random
import re
import socket
import subprocess
import sys

from research.polite_http import ROOT, _path, fetch
from research.textnorm import _OPERATIVE_RE, fold, normalize, split_decision, to_latin

BASE = "https://regulation.gov.uz"
TODAY = dt.date(2026, 11, 18)
OUT = ROOT / "data" / "interim" / "regulation_window.csv"
FLAGS = ROOT / "research" / "flags_for_lawyer_A2.csv"
INTEREST = ROOT / "data" / "interim" / "drafts_of_interest.csv"
CLOSED_RANGE = (95_000, 116_000)
CLOSED_TARGET = 200
OPEN_FROM = 117_800

_ROW = re.compile(
    r'<td>(\d+)</td>\s*<td id="authority-title">\s*(.*?)\s*</td>\s*<td>([\d/]+)</td>\s*<td>([\d/]+)</td>\s*'
    r'<td class="all-comments-count-top">\s*(\d+)\s*</td>', re.DOTALL)
_COUNTER = re.compile(r'id="count-vote-modal-(anti-corruption|gender|survey)">\s*(\d+)\s*<')
_PDF = re.compile(r'data-url="/oz/download/get-pdf\?id=(\d+)&amp;type=paragraph"')
_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)

MONTHS = {"yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
          "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12}
_M = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_UZ = re.compile(rf"\b(20\d\d) yil(?:ning|dagi)? (\d{{1,2}}) ({_M})\w*")
_DATE_RU = re.compile(rf"\b(\d{{1,2}}) ({_M})\w* (20\d\d)\b")
_DATE_NUM = re.compile(r"\b(\d{1,2}) (\d{1,2}) (20\d\d)\b")
_EIF = re.compile(r"kuchga kir|kuchga kiritil|v silu|vstupaet|vstupit")
_RELATIVE = re.compile(r"elon qilingan|rasmiy elon|imzolangan|qabul qilingan|royxatdan otkazilgan|royxatdan otgan"
                       r"|otgach|so dnya|opublikovan|tasdiqlangan kundan|imzolangan kundan")
_SELF = re.compile(r"\b(?:mazkur|ushbu|shbu|dannoe|nastoyashee)\b.{0,40}\b(?:qaror|postanovlen|reshen)")


def parse_page(page: str) -> dict | None:
    m = _ROW.search(page)
    if not m:
        return None
    counters = dict(_COUNTER.findall(page))
    title = _TITLE.search(page)
    return {
        "id": int(m[1]), "creator": html.unescape(re.sub(r"\s+", " ", m[2])).strip(),
        "title": html.unescape(re.sub(r"\s+", " ", title[1])).strip() if title else "",
        "start": m[3], "end": m[4], "proposals": int(m[5]),
        "anti_corruption": int(counters.get("anti-corruption", 0)), "gender": int(counters.get("gender", 0)),
        "survey": int(counters.get("survey", 0)), "pdf_ids": _PDF.findall(page),
    }


def is_local(creator: str) -> bool:
    c = to_latin(creator).lower()
    return "kengash" in c or "hokim" in c


def ddmmyyyy(s: str) -> dt.date:
    d, m, y = s.split("/")
    return dt.date(int(y), int(m), int(d))


def _dates(f: str) -> list[tuple[int, dt.date]]:
    out = []
    for rx, order in ((_DATE_UZ, "ydm"), (_DATE_RU, "dmy"), (_DATE_NUM, "dny")):
        for m in rx.finditer(f):
            try:
                if order == "ydm":
                    d = dt.date(int(m[1]), MONTHS[m[3]], int(m[2]))
                elif order == "dmy":
                    d = dt.date(int(m[3]), MONTHS[m[2]], int(m[1]))
                else:
                    d = dt.date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                continue
            out.append((m.start(), d))
    return sorted(out, key=lambda x: x[0])


def entry_into_force(text: str) -> dict:
    """The draft's own entry-into-force rule: an explicit date, a relative rule, or nothing."""
    t = normalize(text)
    op = _OPERATIVE_RE.search(t)
    body = t[op.end():] if op else t
    candidates = []
    for s in re.split(r"(?<=[.;])\s+", body):
        f = fold(s)
        e = _EIF.search(f)
        if not e:
            continue
        dates = _dates(f)
        before = [d for pos, d in dates if pos < e.start()]
        near_after = [d for pos, d in dates if e.end() <= pos <= e.end() + 80]
        relative = _RELATIVE.search(f[: e.start()]) or _RELATIVE.search(f[e.end(): e.end() + 80])
        date = before[-1] if before else (None if relative else (near_after[0] if near_after else None))
        kind = "date" if date else ("relative" if relative else "other")
        rank = (0 if _SELF.search(f) else 1, {"date": 0, "relative": 1, "other": 2}[kind])
        candidates.append((rank, {"kind": kind, "date": date, "sentence": s[:400]}))
    if not candidates:
        return {"kind": "none", "date": None, "sentence": ""}
    return min(candidates, key=lambda c: c[0])[1]


def classify(eif: dict, end: dt.date) -> str:
    if eif["kind"] == "date":
        return "before_end" if eif["date"] <= end else "after_end"
    return "on_publication" if eif["kind"] == "relative" else "not_found"


def clause_gap(text: str) -> str:
    nums = [n for n, _ in split_decision(text)["clauses"]]
    seq: list[int] = []
    for n in nums:
        if not seq and n == 1 or seq and n > seq[-1]:
            seq.append(n)
    missing = sorted(set(range(1, seq[-1] + 1)) - set(seq)) if seq else []
    return " ".join(map(str, missing))


def pin_dns(host: str) -> None:
    """The laptop's resolver intermittently fails for this host; resolve once via 8.8.8.8 and pin it."""
    try:
        socket.getaddrinfo(host, 443)
        return
    except socket.gaierror:
        pass
    out = subprocess.run(["nslookup", host, "8.8.8.8"], check=False, capture_output=True, text=True).stdout
    ips = re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", out.split("Name:")[-1])
    if not ips:
        raise RuntimeError(f"cannot resolve {host}")
    orig = socket.getaddrinfo
    socket.getaddrinfo = lambda h, *a, **k: orig(ips[0] if h == host else h, *a, **k)


def page(draft_id: int) -> dict | None:
    body = fetch(f"{BASE}/oz/d/{draft_id}", source="regulation", key=f"d{draft_id}.html")
    return parse_page(body.decode("utf-8", "replace")) if body else None


def draft_text(rec: dict) -> str:
    texts = []
    for pdf_id in rec["pdf_ids"][:2]:
        key = f"d{rec['id']}_{pdf_id}.pdf"
        body = fetch(f"{BASE}/oz/download/get-pdf?id={pdf_id}&type=paragraph", source="regulation", key=key)
        if not body.startswith(b"%PDF"):
            continue
        url = f"{BASE}/oz/download/get-pdf?id={pdf_id}&type=paragraph"
        pdf = _path("regulation", key, url, None)
        txt = pdf.with_suffix(".txt")
        if not txt.exists():
            subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(txt)], check=False)
        if txt.exists():
            texts.append(txt.read_text(encoding="utf-8", errors="replace"))
        if texts and entry_into_force(texts[0])["kind"] != "none":
            break
    return "\n".join(texts)


def analyse(rec: dict) -> dict:
    text = draft_text(rec)
    eif = entry_into_force(text)
    end = ddmmyyyy(rec["end"])
    return {
        **{k: v for k, v in rec.items() if k != "pdf_ids"}, "url": f"{BASE}/oz/d/{rec['id']}",
        "is_open": end >= TODAY, "pdf_ids": " ".join(rec["pdf_ids"]), "text_chars": len(text),
        "eif_class": classify(eif, end), "eif_date": eif["date"].isoformat() if eif["date"] else "",
        "days_after_end": (eif["date"] - end).days if eif["date"] else "", "eif_sentence": eif["sentence"],
        "clause_gap": clause_gap(text) if text else "",
    }


def of_interest(r: dict) -> bool:
    title, creator = fold(r["title"]), fold(r["creator"])
    if "dizayn" in title:
        return True
    start = ddmmyyyy(r["start"])
    budget = "byudjet" in title or "budjet" in title
    return "kengash" in creator and budget and start.year in (2024, 2025) and start.month == 12 and start.day >= 15


def log(*a) -> None:
    print(*a, flush=True)


def scan_open() -> list[dict]:
    recs, misses, i = [], 0, OPEN_FROM
    while misses < 25:
        r = page(i)
        misses = misses + 1 if r is None else 0
        if r:
            recs.append(r)
        i += 1
    lo = OPEN_FROM
    while True:
        block = [page(j) for j in range(lo - 100, lo)]
        block = [r for r in block if r]
        recs += block
        if not any(ddmmyyyy(r["end"]) >= TODAY for r in block):
            break
        lo -= 100
    log(f"open scan: ids {lo - 100}..{i - 1}, {len(recs)} pages")
    return recs


def scan_closed() -> list[dict]:
    ids = random.Random(7).sample(range(*CLOSED_RANGE), CLOSED_RANGE[1] - CLOSED_RANGE[0])
    out = []
    for n, i in enumerate(ids):
        r = page(i)
        if r and is_local(r["creator"]) and ddmmyyyy(r["end"]) < TODAY:
            out.append(r)
            if len(out) >= CLOSED_TARGET:
                log(f"closed sample: {len(out)} local drafts from {n + 1} ids tried")
                break
    return out


def main() -> None:
    pin_dns("regulation.gov.uz")
    opened = [r for r in scan_open() if is_local(r["creator"]) and ddmmyyyy(r["end"]) >= TODAY]
    log(f"open local drafts: {len(opened)}")
    closed = scan_closed()
    rows = []
    for n, rec in enumerate(opened + closed, 1):
        rows.append(analyse(rec))
        if n % 50 == 0:
            log(f"analysed {n}/{len(opened) + len(closed)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    flagged = [r for r in rows if r["eif_class"] == "before_end"]
    pick = random.Random(7).sample(flagged, min(10, len(flagged)))
    with FLAGS.open("w", encoding="utf-8", newline="") as f:
        keys = ["id", "url", "creator", "title", "start", "end", "eif_date", "days_after_end", "eif_sentence"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(pick)
    interest = [r for r in rows if of_interest(r)]
    with INTEREST.open("w", encoding="utf-8", newline="") as f:
        keys = ["id", "creator", "title", "start", "end", "proposals", "url"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(interest)
    for group, sel in (("open", [r for r in rows if r["is_open"]]), ("closed", [r for r in rows if not r["is_open"]])):
        counts = {c: sum(r["eif_class"] == c for r in sel) for c in
                  ("before_end", "after_end", "on_publication", "not_found")}
        n = len(sel)
        log(f"{group}: N={n} " + " ".join(f"{c}={k} ({k / n:.1%})" for c, k in counts.items() if n))
    log(f"drafts of interest: {len(interest)}; flags for lawyer: {len(pick)}")


if __name__ == "__main__":
    sys.exit(main())
