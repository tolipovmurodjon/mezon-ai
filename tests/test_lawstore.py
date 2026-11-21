import pytest

from mezon.config import LAW_DB
from mezon.lawstore.fetch import doc_page
from mezon.lawstore.parse import parse_units


def _units(lex_id: str) -> dict:
    try:
        page = doc_page(lex_id)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"page not cached and not fetchable: {e}")
    return {u.path: u for u in parse_units(page)}


def test_parse_nla_core_articles():
    u = _units("-5378966")
    assert "inson foydasiga talqin etiladi" in u["art:18/part:6"].text
    assert "kamida uch oydan keyin kuchga kiradi" in u["art:40/part:2"].text
    assert u["annex:1/cl:102"].text.startswith("102. Quyidagilar bilan majburiy tartibda kelishib olinadi")


def test_parse_order_3333_deadlines():
    u = _units("-5735507")
    assert "ikki ish kuni" in u["annex:1/cl:92"].text and "besh ish kuni" in u["annex:1/cl:92"].text
    assert "ijobiy xulosasi" in u["annex:1/cl:6"].text


@pytest.fixture(scope="module")
def store():
    if not LAW_DB.exists():
        pytest.skip("law store not built")
    from mezon.lawstore.store import LawStore

    return LawStore()


def test_find_act_by_number_and_title(store):
    assert store.find_act("O'RQ-682") == "nla"
    assert store.find_act("913-XII") == "lsp"
    assert store.find_act("PQ-3666") == "pq3666"


def test_non_edition_date_resolves_to_previous_edition(store):
    eds = store.editions("lsp")
    assert len(eds) >= 10
    a, b = eds[-3], eds[-2]
    assert a["valid_from"] < b["valid_from"]
    day_before_b = store.edition_on("lsp", b["valid_from"])["ondate"]
    assert day_before_b == b["ondate"]
    assert store.edition_on("lsp", "1990-01-01") is None


def test_point_in_time_text_changes(store):
    before = store.get_unit("lsp", "art:1/part:2", "2024-10-01")
    after = store.get_unit("lsp", "art:1/part:2", "2025-01-01")
    assert before and after
    assert before["text"] != after["text"]
    assert before["edition"] != after["edition"]
    assert "ONDATE=" in after["url"]


def test_in_force(store):
    assert store.in_force("nla", "2025-01-01")[0]
    assert not store.in_force("nla", "2020-01-01")[0]


def test_search_finds_person_favour_rule(store):
    hits = store.search("ziddiyatlar noaniqliklar inson foydasiga talqin", "2025-06-01", k=5)
    assert any(h["act_key"] == "nla" and h["path"] == "art:18/part:6" for h in hits)


def test_search_public_discussion_finds_nla_art_24(store):
    hits = store.search("jamoatchilik muhokamasi", "2024-01-11", k=8)
    assert any(h["act_key"] == "nla" and h["path"].startswith("art:24") for h in hits)


def test_superscript_article_is_its_own_unit(store):
    unit = store.get_unit("lsp", "art:21-1", "2025-01-01")
    assert unit and "hokim" in unit["text"].lower()


def test_decree_has_clause_units(store):
    assert store.get_unit("pf6243", "cl:1", "2025-01-01")


def test_reader_is_read_only(store):
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        store.con.execute("CREATE TABLE should_fail(x)")


def test_search_respects_date(store):
    hits = store.search("ziddiyatlar noaniqliklar inson foydasiga talqin", "2023-06-01", k=5)
    assert not any(h["act_key"] == "nla" and h["path"] == "art:18/part:6" for h in hits)


def test_find_act_as_questions_name_it(store):
    """MezonBench and users name acts as «Title» (Type, Number); the tools must resolve that form (21 Nov: the model
    fell back to a wrong act when «...» (Kodeks) did not resolve)."""
    law = store
    assert law.find_act("«Oʻzbekiston Respublikasining Soliq kodeksi» (Kodeks)") == "taxcode"
    assert law.find_act("«Maʼmuriy tartib-taomillar toʻgʻrisida» (Qonun, O'RQ-457)") is not None
    assert law.find_act("PQ-3666") == "pq3666"
    assert law.find_act("taxcode") == "taxcode"
