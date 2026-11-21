import csv
from pathlib import Path

import pytest

from research.label_cancellations import label
from research.lexuz_crawl import load_text

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "data" / "labels" / "label_sample_25.csv", encoding="utf-8-sig") as _f:
    SAMPLE = list(csv.DictReader(_f))
FIXES = {"6225616": "EXCLUDE"}


@pytest.mark.parametrize("row", SAMPLE, ids=[r["lex_uz_id"] for r in SAMPLE])
def test_labeler_reproduces_sample(row):
    text = load_text(row["lex_uz_id"])
    if not text:
        pytest.skip("text not cached yet")
    expected = FIXES.get(row["lex_uz_id"], row["use_as"].split(" (")[0])
    got, trigger, _ = label(row["title"], text)
    assert got == expected, trigger


def test_official_trigger_beats_cleanup():
    t = "PF-6075-son Farmoni hamda tuman adliya boʻlimining 38/1-1/70-son taqdimnomasi ijrosini taʼminlash maqsadida"
    assert label("eskirgan va oʻz ahamiyatini yoʻqotgan qarorlarini bekor qilish", t)[0] == "POSITIVE"


def test_axamiyat_spelling_is_cleanup():
    assert (
        label("oʻz axamiyatini yoʻqotgan qarorlarini bekor qilish", "Prezidentining Farmoni")[0] == "EXCLUDE"
    )
