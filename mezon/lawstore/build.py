"""Build the point-in-time law store: resolve core acts, fetch every edition, split into units, index."""

import csv
import re
import sys
from datetime import date

from mezon.config import DATA, LAW_DB
from mezon.lawstore import fetch as lx
from mezon.lawstore.parse import parse_units
from mezon.lawstore.store import connect, iso
from research.lexuz_crawl import parse_hits
from research.polite_http import fetch as http_fetch
from research.textnorm import fold

# key, kind, how to resolve (lex id | actnum:N | title:phrase), type keyword in the search badge, year, edition floor
CORE = [
    ("constitution", "constitution", "-6445145", "", None, None),
    ("nla", "law", "-5378966", "", None, None),
    ("lsp", "law", "-112170", "", None, None),
    ("adminproc", "law", "-3492199", "", None, None),
    ("landtaking", "law", "-6087433", "", None, None),
    ("budgetcode", "code", "-2304138", "", None, "2019-01-01"),
    ("ombudsman", "law", "-3321352", "", None, None),
    ("publiccontrol", "law", "-3679092", "", None, None),
    ("eqaror390", "vmq", "-5470461", "", None, None),
    ("order3333", "ministry", "-5735507", "", None, None),
    ("ai3787", "ministry", "-8083233", "", None, None),
    ("pq3666", "pq", "-3681790", "", None, None),
    ("landcode", "code", "-152653", "", None, "2019-01-01"),
    ("taxcode", "code", "-4674902", "", None, "2025-06-01"),
    ("education", "law", "actnum:637", "qonuni", 2020, None),
    ("geonames", "law", "title:Geografik obyektlarning nomlari toʻgʻrisida", "qonuni", None, None),
    ("employment", "law", "actnum:582", "qonuni", 2020, None),
    ("advertising", "law", "title:Reklama toʻgʻrisida", "qonuni", None, None),
    ("appeals", "law", "title:Jismoniy va yuridik shaxslarning murojaatlari toʻgʻrisida", "qonuni", None, None),
    ("prosecutor", "law", "title:Prokuratura toʻgʻrisida", "qonuni", None, None),
    ("pf6243", "pf", "actnum:6243", "farmoni", 2021, None),
    ("pf6075", "pf", "actnum:6075", "farmoni", 2020, None),
    ("pf126", "pf", "actnum:126", "farmoni", None, None),
    ("pq353", "pq", "actnum:353", "qarori", 2022, None),
    ("pq4407", "pq", "actnum:4407", "qarori", None, None),
    ("pq190", "pq", "actnum:190", "Prezidentining qarori", None, None),
    ("pq236", "pq", "actnum:236", "Prezidentining qarori", None, None),
    ("vmq428", "vmq", "actnum:428", "Vazirlar Mahkamasining", 2023, None),
    ("vmq563", "vmq", "actnum:563", "Vazirlar Mahkamasining", 2026, None),
    ("vmq140", "vmq", "actnum:140", "Vazirlar Mahkamasining", 2017, None),
    ("vmq965", "vmq", "actnum:965", "Vazirlar Mahkamasining", 2017, None),
    ("vmq54", "vmq", "actnum:54", "Vazirlar Mahkamasining", 2003, None),
    ("vmq1010", "vmq", "actnum:1010", "Vazirlar Mahkamasining", 2018, None),
    ("vmq125", "vmq", "actnum:125", "Vazirlar Mahkamasining", 2021, None),
    ("vmq172", "vmq", "actnum:172", "Vazirlar Mahkamasining", 2022, None),
    # The most-cited acts the store lacked (research/missing_acts.py, 19.11.2026): PQ-5 alone is cited by 192 decisions.
    ("pq5", "pq", "actnum:5", "Prezidentining qarori", 2024, None),
    ("vmq295", "vmq", "actnum:295", "Vazirlar Mahkamasining", 2022, None),
    ("vmq299", "vmq", "actnum:299", "Vazirlar Mahkamasining", 2018, None),
    ("pf6121", "pf", "actnum:6121", "farmoni", 2020, None),
    ("vmq82", "vmq", "actnum:82", "Vazirlar Mahkamasining", 2013, None),
    # Adliya's own expertise types: anti-corruption (O'RQ-860) and linguistic (VMQ-662) expertise of drafts.
    ("anticorruption860", "law", "-6561894", "", None, None),
    ("linguistic662", "vmq", "-5701504", "", None, None),
]
import os

# MEZON_FULL_HISTORY=1 (the AWS box, ~1 TB): every edition of every core act, no floors. The laptop keeps the caps.
FULL_HISTORY = os.environ.get("MEZON_FULL_HISTORY") == "1"
MAX_EDITIONS = 1000 if FULL_HISTORY else 25
_TITLE_DATE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")
_TITLE_NUM = re.compile(r"^(.*?)-(?:сон|son)\s+\d{2}\.\d{2}\.\d{4}")
_LATIN = re.compile(r"[a-z]{4}", re.IGNORECASE)
_LOST = re.compile(r"(?:kuchini yoʻqotgan|кучини йўқотган)\D{0,40}(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)


def _search_hits(query: str) -> list[dict]:
    key = "resolve/" + re.sub(r"\W+", "_", query)[:60] + ".html"
    page = http_fetch(f"{lx.BASE}/uz/search/all?{query}", "lexuz", key=key).decode("utf-8", "replace")
    return parse_hits(page)


def resolve(how: str, type_kw: str, year: int | None) -> str | None:
    if not how.startswith(("actnum:", "title:")):
        return how
    if how.startswith("actnum:"):
        from urllib.parse import quote

        from research.lexuz_crawl import search_url

        num = how.split(":", 1)[1]
        _, hits = search_url(f"{lx.BASE}/uz/search/all?actnum={quote(num)}",
                             "resolve/actnum_" + re.sub(r"\W+", "_", num), max_pages=6)
        ok = [h for h in hits if h["number"] and re.search(rf"(?:^|\D){re.escape(num)}$", h["number"])]
    else:
        phrase = how.split(":", 1)[1]
        from urllib.parse import quote

        from research.lexuz_crawl import search_url

        _, hits = search_url(f"{lx.BASE}/uz/search/all?searchtitle={quote(phrase)}",
                             "resolve/" + re.sub(r"\W+", "_", phrase)[:50], max_pages=3)
        ok = [h for h in hits if fold(phrase) in fold(h["title"])
              and not re.search(r"ozgartirish|qoshimcha|kiritish", fold(h["title"]))]
        ok.sort(key=lambda h: len(h["title"]))
    ok = [h for h in ok if fold(type_kw) in fold(h["badge"]) and _LATIN.search(h["title"]) and h["id"].startswith("-")]
    if year:
        ok = [h for h in ok if h["date"] and h["date"].endswith(str(year))]
    if how.startswith("actnum:"):
        ok.sort(key=lambda h: (h.get("status") == "1", iso(h["date"] or "01.01.1900")), reverse=True)
    return ok[0]["id"] if ok else None


def collect_editions(lex_id: str, current: str, floor: str | None) -> list[str]:
    """Edition dates ('dd.mm.yyyy NN'), found from the current page and then walking older editions' links."""
    found = lx.edition_dates(current, lex_id) | {f"{d} 00" for d in lx.amendment_dates(current)}
    checked: set[str] = set()
    for _ in range(3):
        todo = sorted(found - checked, key=lambda s: (iso(s), s), reverse=True)
        if floor:
            todo = [s for s in todo if iso(s) >= floor]
        for s in todo[:MAX_EDITIONS]:
            checked.add(s)
            page = lx.edition_page(lex_id, s)
            if page:
                found |= lx.edition_dates(page, lex_id)
        if not todo:
            break
    dates = sorted(found, key=lambda s: (iso(s), s))
    if not FULL_HISTORY and (len(dates) > MAX_EDITIONS or floor):
        keep_floor = floor or "2019-01-01"
        dates = dates[:1] + [s for s in dates[1:] if iso(s) >= keep_floor]
    return dates


def relations(lex_id: str) -> list[tuple]:
    out = []
    for panel in ("revhis", "correspondents"):
        page = lx.relation_page(lex_id, panel)
        for m in re.finditer(r'href="/uz/docs/(-?\d+)"[^>]*>(.*?)</a>(.{0,400})', page, re.DOTALL):
            title = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
            d = _TITLE_DATE.search(m.group(3))
            kind = "amends" if panel == "revhis" else ("amends" if "oʻzgartirish" in title.lower() else "cites")
            out.append((panel, m.group(1), title, iso(d.group(1)) if d else None, kind))
    return out


def build(only: list[str] | None = None) -> None:
    if not only:
        for suffix in ("", "-wal", "-shm"):
            LAW_DB.with_name(LAW_DB.name + suffix).unlink(missing_ok=True)
    con = connect(LAW_DB)
    rows = []
    for key, kind, how, type_kw, year, floor in CORE:
        floor = None if FULL_HISTORY else floor
        if only and key not in only:
            continue
        lex_id = resolve(how, type_kw, year)
        if not lex_id:
            print(f"UNRESOLVED {key}: {how}", flush=True)
            rows.append({"act_key": key, "kind": kind, "lex_id": "", "title": "", "number": "", "date": "",
                         "verified": "no", "url": ""})
            continue
        current = lx.doc_page(lex_id)
        title = lx.page_title(current)
        num = _TITLE_NUM.match(title)
        adopted = _TITLE_DATE.search(title)
        number = num.group(1).strip() if num else ""
        name = re.sub(r"^.*?\d{2}\.\d{2}\.\d{4}\.\s*", "", title)
        lost = _LOST.search(current[:20000])
        con.execute("DELETE FROM acts WHERE act_key=?", (key,))
        con.execute("INSERT INTO acts VALUES(?,?,?,?,?,?,?,?)", (
            key, lex_id, name, kind, number, iso(adopted.group(1)) if adopted else None,
            iso(lost.group(1)) if lost else None, f"{lx.BASE}/uz/docs/{lex_id}"))
        dates = collect_editions(lex_id, current, floor)
        latest = dates[-1] if dates else f"{adopted.group(1) if adopted else '01.01.1900'} 00"
        if not dates:
            dates = [latest]
        _store_editions(con, key, lex_id, dates, current, lx.has_pending_banner(current))
        con.execute("DELETE FROM relations WHERE from_act=?", (key,))
        con.executemany("INSERT INTO relations VALUES(?,?,?,?,?,?)", [(key, *r) for r in relations(lex_id)])
        con.commit()
        n_units = con.execute("SELECT count(*) FROM units WHERE act_key=?", (key,)).fetchone()[0]
        print(f"{key}: {lex_id} | {title[:70]} | editions {len(dates)} | units {n_units}", flush=True)
        rows.append({"act_key": key, "kind": kind, "lex_id": lex_id, "title": name, "number": number,
                     "date": adopted.group(1) if adopted else "", "verified": "yes",
                     "url": f"{lx.BASE}/uz/docs/{lex_id}"})
    _write_csv(rows)
    _rebuild_fts(con)
    con.close()


def _store_editions(con, key: str, lex_id: str, dates: list[str], current: str, banner: bool) -> None:
    con.execute("DELETE FROM editions WHERE act_key=?", (key,))
    con.execute("DELETE FROM units WHERE act_key=?", (key,))
    kept: list[tuple[str, str]] = []
    for i, s in enumerate(dates):
        page = current if i == len(dates) - 1 else lx.edition_page(lex_id, s)
        if not page:
            continue
        kept.append((s, page))
    starts = [iso(s) for s, _ in kept]
    open_units: dict[str, list] = {}
    closed: list[list] = []
    for i, (s, page) in enumerate(kept):
        valid_to = starts[i + 1] if i + 1 < len(kept) else None
        con.execute("INSERT INTO editions VALUES(?,?,?,?,?,?)",
                    (key, s, starts[i], i, valid_to, int(banner and i == len(kept) - 1)))
        seen = set()
        for u in parse_units(page):
            if u.path in seen:
                continue
            seen.add(u.path)
            cur = open_units.get(u.path)
            if cur and cur[2] == u.text and cur[1] == u.heading and cur[7] == i - 1:
                cur[7] = i
                continue
            if cur:
                closed.append(cur)
            open_units[u.path] = [u.path, u.heading, u.text, u.element_id, "\n".join(u.notes), s, i, i]
        for path in [p for p, row in open_units.items() if row[7] < i]:
            closed.append(open_units.pop(path))
    closed.extend(open_units.values())
    con.executemany(
        """INSERT INTO units(act_key, path, heading, text, element_id, notes, ondate, seq_from, seq_to,
           valid_from, valid_to) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        [(key, p, h, t, e, n, s, a, b, starts[a], starts[b + 1] if b + 1 < len(starts) else None)
         for p, h, t, e, n, s, a, b in closed],
    )


def _rebuild_fts(con) -> None:
    """One transaction: under WAL, readers keep searching the previous index until the commit."""
    rows = con.execute("SELECT id, heading, text FROM units").fetchall()
    con.execute("DROP TABLE IF EXISTS units_fts")
    con.execute("CREATE VIRTUAL TABLE units_fts USING fts5(heading, body, unit_id UNINDEXED, tokenize='unicode61')")
    con.executemany("INSERT INTO units_fts(heading, body, unit_id) VALUES(?,?,?)",
                    [(fold(r["heading"] or ""), fold(r["text"] or ""), r["id"]) for r in rows])
    con.commit()


def _write_csv(rows: list[dict]) -> None:
    path = DATA / "knowledge" / "core_acts.csv"
    existing = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            existing = {r["act_key"]: r for r in csv.DictReader(f)}
    existing.update({r["act_key"]: r for r in rows})
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["act_key", "kind", "lex_id", "title", "number", "date", "verified", "url"])
        w.writeheader()
        w.writerows(sorted(existing.values(), key=lambda r: r["act_key"]))


if __name__ == "__main__":
    build(sys.argv[1:] or None)
    print("built", LAW_DB, date.today())
