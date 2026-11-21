from typing import ClassVar

import pytest

from mezon.decisions import build as dbuild
from mezon.decisions.store import DecisionStore
from mezon.report import Citation, Evidence, Flag
from mezon.rules import basis, business, run
from mezon.rules.common import SafeLaw
from mezon.verify import verify_flag


class FakeLawStore:
    """A tiny stand-in for mezon.lawstore.store with the same interface."""

    NLA = "O'RQ-682"
    UNITS: ClassVar[dict] = {
        (NLA, "art:16"): "Kengashlar normativ-huquqiy hujjatlarni qarorlar tarzida qabul qiladi.",
        (NLA, "art:18/part:3"): "Yuridik kuchi yuqori bo'lgan hujjat qo'llaniladi.",
        (NLA, "art:24/part:1"): "Loyihalar jamoatchilik muhokamasi uchun portalga joylashtiriladi.",
        (NLA, "art:24/part:3"): "Muhokama muddati o'n besh kundan kam bo'lmasligi kerak.",
        (NLA, "art:24/part:4"): "Takliflarni hisobga olish ishlab chiquvchi zimmasida.",
        (NLA, "art:40/part:2"): "Tadbirkorlik subyektlari uchun majburiyatlar kamida uch oy o'tgach kuchga kiradi.",
        (NLA, "art:41/part:1"): "Normativ-huquqiy hujjatlar orqaga qaytish kuchiga ega emas.",
        (NLA, "art:46/part:1"): "Ilgari qabul qilingan hujjatlar o'z kuchini yo'qotgan deb topilishi lozim.",
        ("3333", "annex:1/cl:1"): "Normativ-huquqiy hujjatlar qaror shaklida qabul qilinadi.",
        ("3333", "annex:1/cl:6"): "Adliya organining ijobiy xulosasi qaror qabul qilish uchun majburiy shartdir.",
        ("3333", "annex:1/cl:51"): "Qarorlarni o'z kuchini yo'qotgan deb topish tartibi.",
        ("913-XII", "art:21-1"): "Yuqori turuvchi hokim quyi hokimning qarorini bekor qiladi.",
        ("PF-6243", "1"): "Yer uchastkalarini ajratish tartibi o'zgartiriladi.",
        ("OLD-1", "1"): "Eski band.",
    }
    REPEALED: ClassVar[dict] = {"OLD-1": "2020-01-01"}

    def find_act(self, number_or_title):
        for act, _ in self.UNITS:
            if act.lower() == str(number_or_title).lower():
                return act
        return None

    def in_force(self, act_key, date):
        lost = self.REPEALED.get(act_key)
        return any(a == act_key for a, _ in self.UNITS) and not (lost and date >= lost)

    def edition_on(self, act_key, date):
        return "2024-01-01" if self.in_force(act_key, date) else None

    def get_unit(self, act_key, unit_path, on_date):
        text = self.UNITS.get((act_key, unit_path))
        if text is None or not self.in_force(act_key, on_date):
            return None
        return {
            "text": text,
            "edition": "2024-01-01",
            "url": f"https://lex.uz/fake/{act_key}",
            "provisional": False,
        }

    def search(self, query, on_date, k=5):
        return []


@pytest.fixture(scope="module")
def dstore(tmp_path_factory):
    db = tmp_path_factory.mktemp("store") / "decisions.sqlite"
    n = dbuild.build(db)
    store = DecisionStore(db)
    if not store.by_reg("231-4-59-Q/24") or not store.get(store.by_reg("231-4-59-Q/24")[0])["text"]:
        pytest.skip("Qarshi texts not cached (set MEZON_CACHE)")
    assert n > 100
    return store


def _flags(dstore, reg, store=None):
    did = dstore.by_reg(reg)[0]
    return run.audit(did, law=store or FakeLawStore(), decisions=dstore)


def test_qarshi_231_is_negative(dstore):
    rep = _flags(dstore, "231-4-59-Q/24")
    checks = {f.check for f in rep.flags}
    assert {"R_duplicate", "R_double_repeal"} <= checks
    assert rep.verdict == "negative"


def test_207_has_no_duplicate_flag(dstore):
    rep = _flags(dstore, "207-4-59-Q/24")
    assert not [f for f in rep.flags if f.check == "R_duplicate"]


def test_draft_118221_window(dstore):
    rep = run.audit("draft:118221", law=FakeLawStore(), decisions=dstore)
    assert rep.gate == "0_draft"
    assert "R_draft_window" in {f.check for f in rep.flags}


def test_yangiyol_discussion_flag(dstore):
    rep = _flags(dstore, "VI-76-4-10-146-K/24")
    assert "R_discussion" in {f.check for f in rep.flags}
    twin = _flags(dstore, "VI-76-21-10-146-K/24")
    assert "R_discussion" not in {f.check for f in twin.flags}


def test_missing_law_store_never_crashes(dstore):
    did = dstore.by_reg("231-4-59-Q/24")[0]
    rep = run.audit(did, law=None, decisions=dstore)
    assert rep.flags and all(f.status == "unclear_needs_expert" for f in rep.flags)
    assert rep.verdict != "negative"


def test_clean_control_is_positive(dstore):
    rep = _flags(dstore, run.CLEAN_CONTROL)
    assert rep.verdict == "positive", [f.check for f in rep.flags]


def _decision(text="1. Barcha tadbirkorlik subyektlari uchun yig'im belgilansin."):
    return {"id": "t", "text": text, "adopted": "2025-01-10", "stages": None}


def test_verifier_drops_fabricated_citation():
    f = Flag(
        "R_x",
        "t",
        "e",
        "high",
        evidence=[Evidence("decision", "1", "yig'im belgilansin")],
        citations=[Citation("FAKE-1", "Fake", "99", "nothing", "2025-01-10")],
    )
    out, stats = verify_flag(f, _decision(), FakeLawStore())
    assert out is not None and out.citations == [] and out.status == "unclear_needs_expert"
    assert stats["fabricated"] == 1


def test_verifier_drops_misgrounded_citation():
    f = Flag(
        "R_x",
        "t",
        "e",
        "high",
        evidence=[Evidence("decision", "1", "yig'im belgilansin")],
        citations=[Citation("OLD-1", "Old", "1", "Eski band.", "2025-01-10")],
    )
    out, stats = verify_flag(f, _decision(), FakeLawStore())
    assert out.citations == [] and stats["misgrounded"] == 1


def test_verifier_rejects_non_verbatim_evidence():
    f = Flag(
        "R_x",
        "t",
        "e",
        "high",
        evidence=[Evidence("decision", "1", "this sentence is not in the decision")],
        citations=[
            Citation("O'RQ-682", "NLA", "art:40/part:2", "kamida uch oy o'tgach kuchga kiradi", "2025-01-10")
        ],
    )
    out, stats = verify_flag(f, _decision(), FakeLawStore())
    assert out is None and stats["fabricated_evidence"] == 1


def test_verifier_keeps_good_flag():
    f = Flag(
        "R_x",
        "t",
        "e",
        "high",
        evidence=[Evidence("decision", "1", "yig‘im belgilansin")],
        citations=[
            Citation("O'RQ-682", "NLA", "art:40/part:2", "kamida uch oy o'tgach kuchga kiradi", "2025-01-10")
        ],
    )
    out, _ = verify_flag(f, _decision(), FakeLawStore())
    assert out.status == "possible_violation" and len(out.citations) == 1


def test_business_burden_detection():
    assert business.burden("Barcha tadbirkorlik subyektlari uchun majburiy to'lov belgilansin")["business"]
    assert business.burden("Maishiy chiqindilar uchun majburiy tolov tariflari tasdiqlansin")["money"]
    assert not business.burden("Tuman hokimining o'rinbosari nazorat qilsin")["money"]


def test_retroactive_and_three_month_rules():
    text = (
        "QAROR QILAMAN: 1. Barcha tadbirkorlik subyektlari uchun yig'im miqdori belgilansin. "
        "2. Mazkur qaror 2025-yil 1-yanvardan e'tiboran kuchga kiradi."
    )
    d = {"id": "t", "text": text, "adopted": "2025-02-01", "published": "", "role": "adopted"}
    checks = {f.check for f in business.check(d)}
    assert {"R_retroactive", "R_business_3m"} <= checks


class _ActStore(FakeLawStore):
    ACTS: ClassVar[dict] = {"PQ-190": {"adopted": "2025-05-23"}, "PQ-77": {"adopted": "2010-01-05"}}
    LOST: ClassVar[dict] = {"PQ-77": "2020-01-01"}

    def find_act(self, q):
        return q if q in self.ACTS else super().find_act(q)

    def act(self, key):
        return self.ACTS.get(key)

    def in_force(self, key, date):
        if key in self.ACTS:
            lost = self.LOST.get(key)
            return self.ACTS[key]["adopted"] <= date and not (lost and lost <= date)
        return super().in_force(key, date)


def test_basis_ignores_same_number_from_a_later_year_but_flags_a_lost_act():
    text = ("Prezidentning PQ-190-son qarori va PQ-77-son qarori ijrosini ta'minlash maqsadida QAROR QILAMAN: "
            "1. Ijro etilsin.")
    d = {"id": "t", "text": text, "adopted": "2024-05-21", "url": ""}
    flags = basis.check(d, SafeLaw(_ActStore()))
    assert [f.title for f in flags] == ["Rests on PQ-77, which wasn't in force on 2024-05-21"]
