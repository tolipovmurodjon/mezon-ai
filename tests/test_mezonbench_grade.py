"""Lookup grading: a verbatim quote counts even when wrapped in a heading; paraphrase or short quotes do not."""

from research.mezonbench import grade

GOLD = ("Oʻzbekiston Respublikasi Vazirlar Mahkamasining, Qoraqalpogʻiston Respublikasi respublika budjetining, "
        "viloyatlar viloyat budjetlarining va Toshkent shahri shahar budjetining zaxira jamgʻarmalari")
ITEM = {"family": "lookup", "answer": GOLD}


def test_wrapped_quote_is_right():
    ans = ("«Budjet kodeksi» 73-modda 2-qismi 2020-11-17 holatida quyidagicha edi:\n\n> «" + GOLD[:120] + "»")
    assert grade(ITEM, ans) == "right"


def test_plain_quote_is_right():
    assert grade(ITEM, GOLD[:90]) == "right"


def test_paraphrase_or_short_is_wrong():
    assert grade(ITEM, "Vazirlar Mahkamasi va mahalliy budjetlarning zaxira jamg'armalari haqida") == "wrong"
    assert grade(ITEM, "> «" + GOLD[:30] + "»") == "wrong"


def test_noaniq_is_abstain():
    assert grade(ITEM, "noaniq") == "abstain"
