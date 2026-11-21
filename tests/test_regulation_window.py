import datetime as dt
from pathlib import Path

import pytest

from research import regulation_window as rw

ROOT = Path(__file__).resolve().parents[1]
CACHED_118221 = ROOT / "data" / "cache" / "regulation" / "d118221_401661.txt"
PAGE_118221 = ROOT / "data" / "cache" / "regulation" / "d118221.html"


@pytest.fixture
def text_118221():
    if not CACHED_118221.exists():
        pytest.skip("draft 118221 not cached")
    return CACHED_118221.read_text(encoding="utf-8", errors="replace")


def test_118221_enters_into_force_before_discussion_ends(text_118221):
    eif = rw.entry_into_force(text_118221)
    assert eif["kind"] == "date"
    assert eif["date"] == dt.date(2026, 12, 1)
    assert rw.classify(eif, dt.date(2026, 12, 2)) == "before_end"


def test_118221_clause_4_missing(text_118221):
    assert rw.clause_gap(text_118221) == "4"


def test_parse_page_118221():
    if not PAGE_118221.exists():
        pytest.skip("page not cached")
    rec = rw.parse_page(PAGE_118221.read_text(encoding="utf-8"))
    assert rec["id"] == 118221 and rec["end"] == "02/12/2026" and rec["pdf_ids"] == ["401661"]
    assert rw.is_local(rec["creator"])


@pytest.mark.parametrize(
    "sentence, kind",
    [
        ("7. Mazkur qaror rasmiy e'lon qilingan kundan boshlab kuchga kiradi.", "relative"),
        ("7. Ушбу қарор 2027 йил 1 январдан кучга киради.", "date"),
        ("5. Настоящее решение вступает в силу с 1 января 2027 года.", "date"),
        ("6. Mazkur qaror 01.03.2027 dan kuchga kiradi.", "date"),
        ("5. Mazkur qaror e'lon qilingan kundan boshlab kuchga kiradi Ilova 2026-yil 12-sentabr tadbirlar", "relative"),
    ],
)
def test_entry_into_force_forms(sentence, kind):
    assert rw.entry_into_force("QAROR QILADI: " + sentence)["kind"] == kind


def test_classify_after_end():
    eif = {"kind": "date", "date": dt.date(2027, 1, 1)}
    assert rw.classify(eif, dt.date(2026, 12, 2)) == "after_end"
