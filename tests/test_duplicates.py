from pathlib import Path

import pytest

from research.duplicates import analyse
from research.lexuz_crawl import load_text, parse_doc

DOCS = Path(__file__).resolve().parents[1] / "data" / "cache" / "lexuz" / "docs"


def _doc(doc_id: str) -> dict:
    page = DOCS / f"{doc_id}.html"
    if not page.exists() or not load_text(doc_id):
        pytest.skip(f"{doc_id} not cached")
    meta = parse_doc(page.read_text(encoding="utf-8"))
    meta.pop("inline_text")
    return meta | {"id": f"-{doc_id}", "url": f"https://lex.uz/uz/docs/-{doc_id}"}


def test_qarshi_golden_case_found_blind():
    flags = analyse([_doc("6961952"), _doc("6986157")])
    reasons = {(f["older_number"], f["newer_number"], f["reason"].split(",")[0]) for f in flags}
    assert (
        "207-4-59-Q/24",
        "231-4-59-Q/24",
        "near-identical decision while the older one is in force",
    ) in reasons
    assert ("207-4-59-Q/24", "231-4-59-Q/24", "repeals 161-4-59-Q/23") in reasons
