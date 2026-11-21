from pathlib import Path

import pytest

from mezon.sync import rss

CACHED = Path(__file__).resolve().parents[1] / "data" / "cache" / "lexuz" / "rss_2026-11-19.xml"


@pytest.fixture(scope="module")
def items():
    if not CACHED.exists():
        pytest.skip("RSS snapshot not cached")
    return rss.parse(CACHED.read_bytes())


def test_parses_every_item_with_dates(items):
    assert len(items) >= 50
    first = items[0]
    assert first.lex_id == "8602667"
    assert first.adopted == "2026-11-17" and first.in_force == "2027-02-19"
    assert first.days_to_force == 94
    assert "Markaziy banki" in first.issuer and not first.is_local


def test_local_decisions_are_tagged(items):
    assert all(rss._LOCAL.search(rss.fold(i.issuer)) for i in items if i.is_local)
    assert not any(i.is_local for i in items if "vazirligi" in i.issuer and "hokim" not in i.issuer.lower())
