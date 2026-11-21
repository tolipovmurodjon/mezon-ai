import pytest

from mezon.lawstore.store import LawStore

CASES = [
    ("Mahalliy davlat hokimiyati to'g'risidagi Qonun", "lsp"),
    ("Mahalliy davlat hokimiyati to‘g‘risidagi Qonun", "lsp"),
    ("Mahalliy davlat hokimiyati toʻgʻrisidagi Qonunning", "lsp"),
    ("Маҳаллий давлат ҳокимияти тўғрисида", "lsp"),
    ("913-XII", "lsp"),
    ("Normativ-huquqiy hujjatlar to'g'risidagi qonun", "nla"),
    ("O‘RQ-682", "nla"),
    ("Soliq kodeksi", "taxcode"),
    ("Soliq kodeksining", "taxcode"),
    ("PQ-3666", "pq3666"),
    ("Budjet kodeksi", "budgetcode"),
    ("tax", "taxcode"),
]


@pytest.fixture(scope="module")
def law():
    try:
        return LawStore()
    except FileNotFoundError:
        pytest.skip("law store not built")


@pytest.mark.parametrize("q,key", CASES)
def test_find_act(law, q, key):
    assert law.find_act(q) == key


def test_find_act_nothing_close(law):
    assert law.find_act("Kosmik kemalar qurish bo'yicha nizom") is None


from mezon.tools import _path, law_as_of, verify_quote  # noqa: E402


@pytest.mark.parametrize("a", ["art:25", "25-modda", "25", "modda 25", "25-moddasi", "Modda 25"])
def test_article_forms(a):
    assert _path(a) == "art:25"


def test_removed_article_reports_edition(law):
    r = law_as_of(law, "Mahalliy davlat hokimiyati to'g'risidagi Qonun", "25-modda", "2025-11-13")
    assert r["ok"] is False and r["in_force"] is False
    assert r["removed_in_edition"] == "2024-10-19"
    assert r["last_seen_edition"] == "2023-12-19" or r["last_seen_edition"] < "2024-10-19"


def test_live_article_text(law):
    r = law_as_of(law, "O'RQ-682", "modda 40", "2025-10-23")
    assert r.get("text") and r["in_force"] is True
    assert verify_quote(law, "nla", "40-modda", "2025-10-23", "zzzz")["ok"] is False
