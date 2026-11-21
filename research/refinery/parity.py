"""Parity check (design section 11, check 1): the refinery's unit intervals must equal the law store's `units` rows
(path, heading, text, element id, notes, first edition, seq range, valid_from, valid_to) for every core act.

    python -X utf8 -m research.refinery.parity [--tail 8]     # offline: only cached pages, no network

Both sides get exactly the same pages. The store side is the real `build._store_editions` run on an in-memory database
with `fetch.edition_page` replaced by a cache read, so a difference is a bug in one of the two."""

import argparse
import json
import sqlite3

from mezon.lawstore import build as legacy
from mezon.lawstore import fetch as lx
from mezon.lawstore.parse import parse_units
from mezon.lawstore.store import SCHEMA
from research.refinery import sources as src
from research.refinery.extract_html import unit_versions
from research.refinery.leak import load_core

COLS = "path, heading, text, element_id, notes, ondate, seq_from, seq_to, valid_from, valid_to"
KEYS = (
    "path",
    "heading",
    "text",
    "element_id",
    "notes",
    "ondate",
    "seq_from",
    "seq_to",
    "valid_from",
    "valid_to",
)


def cached_pages(lex_id: str, tail: int | None = None):
    """(current page, [(ondate, page)] oldest first, the last entry being the current page), or None."""
    page, _ = src.doc_page(lex_id)
    if not page:
        return None
    eds = src.edition_files(lex_id, page)
    if tail:
        eds = eds[-tail:]
    pages = [(d, p.read_bytes().decode("utf-8", "replace")) for d, p in eds]
    if pages:
        pages[-1] = (pages[-1][0], page)
    return page, eds, pages


def store_rows(key: str, lex_id: str, page: str, editions) -> list[tuple]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    by_date = {d: p.read_bytes().decode("utf-8", "replace") for d, p in editions}
    dates = [d for d, _ in editions] or ["01.01.1900 00"]
    orig = lx.edition_page
    lx.edition_page = lambda _lid, d: by_date.get(d, "")
    try:
        legacy._store_editions(con, key, lex_id, dates, page, lx.has_pending_banner(page))
    finally:
        lx.edition_page = orig
    return [tuple(r) for r in con.execute(f"SELECT {COLS} FROM units ORDER BY id")]


def refinery_rows(page: str, pages: list[tuple[str, str]]) -> list[tuple]:
    pages = pages or [("01.01.1900 00", page)]
    got = unit_versions([(d, parse_units(pg), False) for d, pg in pages])
    return [tuple(r[k] for k in KEYS) for r in got]


def check(key: str, lex_id: str, tail: int | None = None) -> dict | None:
    c = cached_pages(lex_id, tail)
    if c is None:
        return None
    page, eds, pages = c
    want = store_rows(key, lex_id, page, eds)
    mine = refinery_rows(page, pages)
    return {
        "act": key,
        "lex_id": lex_id,
        "editions": len(eds) or 1,
        "store_rows": len(want),
        "refinery_rows": len(mine),
        "equal": mine == want,
        "mismatches": sum(1 for a, b in zip(mine, want, strict=False) if a != b),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=None, help="only the last N editions of each act")
    a = ap.parse_args()
    rows = [r for k, lid in sorted(load_core().items()) if (r := check(k, lid, a.tail))]
    print(json.dumps(rows, indent=1))
    ok = sum(r["equal"] for r in rows)
    print(
        f"parity: {ok}/{len(rows)} cached core acts identical; "
        f"rows compared: {sum(r['store_rows'] for r in rows)}; core acts listed: {len(load_core())}"
    )


if __name__ == "__main__":
    main()
