import datetime as dt
from pathlib import Path

import pytest

from mezon.sync import regulation_all as ra

CACHE = Path(__file__).resolve().parents[1] / "data" / "cache" / "regulation"
TODAY = dt.date(2026, 11, 19)


@pytest.fixture
def con(tmp_path, monkeypatch):
    if not (CACHE / "d118221.html").exists() or not (CACHE / "d109599.html").exists():
        pytest.skip("cached draft pages missing")
    monkeypatch.setattr(ra, "page_html", lambda i: (CACHE / f"d{i}.html").read_text(encoding="utf-8"))
    monkeypatch.setattr(ra, "_pdf_text", lambda i, p: (CACHE / f"d{i}_{p}.txt").read_text(encoding="utf-8")
                        if (CACHE / f"d{i}_{p}.txt").exists() else "")
    return ra.connect(tmp_path / "reg.sqlite")


def test_local_draft_is_classified_before_discussion_end(con):
    row = ra.process(con, 118221, TODAY)
    assert row["is_local"] == 1 and row["status"] == "open"
    assert row["eif_class"] == "before_end" and row["eif_date"] == "2026-12-01"
    assert "4" in row["clause_gap"].split()
    assert con.execute("select count(*) from drafts").fetchone()[0] == 1


def test_national_draft_keeps_type_and_status_without_text(con):
    row = ra.process(con, 109599, TODAY)
    assert row["is_local"] == 0 and row["text"] is None
    assert row["status"] == "Muhokama yakunlandi"
    assert "Vazirlar Mahkamasi" in row["doc_type"]


def test_missing_id_is_remembered(con, monkeypatch):
    monkeypatch.setattr(ra, "page_html", lambda i: "")
    assert ra.process(con, 1, TODAY) is None
    assert con.execute("select id from missing").fetchall() == [(1,)]
