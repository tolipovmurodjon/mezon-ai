import pytest

from mezon.lawstore.store import LawStore

try:
    LAW = LawStore()
except FileNotFoundError:  # pragma: no cover
    LAW = None

pytestmark = pytest.mark.skipif(LAW is None, reason="law store not built")


def test_changed_since_finds_later_editions_only():
    from mezon.delta import changed_since

    eds = [e["valid_from"] for e in LAW.editions("nla")]
    cutoff = sorted(eds)[-2]  # the second newest edition date: exactly the newest one(s) come after it
    rows = changed_since(LAW, cutoff, acts=["nla"])
    assert rows and all(r["valid_from"] > cutoff for r in rows)
    assert {r["valid_from"] for r in rows} == {d for d in eds if d > cutoff}


def test_no_change_after_the_last_edition_means_no_lookup():
    from mezon.delta import needs_lookup

    last = max(e["valid_from"] for e in LAW.editions("nla"))
    assert needs_lookup(LAW, last, ["nla"]) is False
    assert needs_lookup(LAW, "2000-01-01", ["nla"]) is True
