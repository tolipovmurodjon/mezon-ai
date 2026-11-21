from pathlib import Path

import pytest

from research import regnum, textnorm

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data" / "cache" / "lexuz" / "zip"


def _text(doc_id: str) -> str:
    files = list((ZIP / doc_id).glob("*.txt"))
    if not files:
        pytest.skip(f"no cached text for {doc_id}")
    return files[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("raw", ["o‘z", "oʻz", "o`z", "o'z", "oz", "ўз", "Ўз"])
def test_fold_unifies_apostrophes_and_script(raw):
    assert textnorm.fold(raw) == "oz"


def test_normalize_unglues_digits():
    assert textnorm.normalize("bo‘limining2022 yil") == "bo'limining 2022 yil"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("231-4-59-Q/24", {"type": "Q", "number": 231, "region": 4, "district": 59, "year": 2024}),
        ("94-9-0-F/21", {"type": "F", "number": 94, "region": 9, "district": 0, "year": 2021}),
        ("VI-76-4-10-146-K/24", {"type": "K", "convocation": "VI", "session": 76, "number": 4, "region": 10,
                                 "district": 146, "year": 2024}),
        ("VI-25-3-9-0-K/21", {"type": "K", "session": 25, "number": 3, "region": 9, "district": 0}),
        ("442-11-169/Q", {"type": "Q", "number": 442, "region": 11, "district": 169, "year": None}),
    ],
)
def test_regnum_parses_all_observed_forms(raw, expected):
    got = regnum.parse(raw)
    assert got is not None
    assert {k: got[k] for k in expected} == expected


def test_regnum_find_all_in_text():
    t = "tuman hokimining 2023-yil 15-iyuldagi 161-4-59-Q/23-sonli qarori va VI-76-4-10-146-K/24"
    assert [h["raw"] for h in regnum.find_all(t)] == ["161-4-59-Q/23", "VI-76-4-10-146-K/24"]


def test_split_decision_qarshi_231():
    d = textnorm.split_decision(_text("6986157"))
    assert [n for n, _ in d["clauses"]] == [1, 2, 3, 4, 5, 6]
    assert "161 4 59 q 23" in d["clauses"][3][1]
    assert d["annex"]


def test_qarshi_231_is_a_copy_of_207():
    a, b = textnorm.split_decision(_text("6986157")), textnorm.split_decision(_text("6961952"))
    assert textnorm.similarity(a["operative"], b["operative"]) >= 0.95
    assert textnorm.bag_similarity(a["annex"], b["annex"]) >= 0.95
