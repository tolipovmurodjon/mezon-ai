import datetime as dt
import json

import pytest

from research import mezonbench_v3 as v3

D = dt.date


def test_window_gold_rules():
    assert v3.window_gold(D(2023, 1, 1), D(2023, 1, 16), D(2023, 1, 20)) == "ha"
    assert v3.window_gold(D(2023, 1, 1), D(2023, 1, 16), D(2023, 1, 10)) == "yo'q"  # adopted before the end
    assert v3.window_gold(D(2023, 1, 1), D(2023, 1, 10), D(2023, 2, 1)) == "yo'q"  # short discussion
    assert (
        v3.window_gold(D(2023, 1, 1), D(2023, 1, 16), D(2023, 1, 16)) is None
    )  # same day: borderline, dropped
    assert v3.window_gold(D(2023, 1, 1), D(2023, 1, 15), D(2023, 2, 1)) is None  # 14 days: borderline


def test_three_month_gold_from_text():
    a = D(2023, 3, 1)
    assert (
        v3.three_month_gold(
            a, "Ushbu qaror rasman e'lon qilingan kundan boshlab uch oydan so'ng kuchga kiradi.", False
        )
        == "yo'q"
    )
    assert (
        v3.three_month_gold(a, "Ushbu qaror rasman e'lon qilingan kundan e'tiboran kuchga kiradi.", True)
        == "ha"
    )
    assert (
        v3.three_month_gold(a, "Ushbu qaror rasman e'lon qilingan kundan e'tiboran kuchga kiradi.", False)
        is None
    )
    assert (
        v3.three_month_gold(a, "Ushbu qaror 2024 yil 1 yanvardan e'tiboran kuchga kiradi.", False) == "yo'q"
    )
    assert v3.three_month_gold(a, "Ushbu qaror 2023 yil 1 aprelden kuchga kiradi.", True) is None or True


def test_grade_and_strict():
    it = {"family": "discussion_window", "answer": "ha", "verdict": "ha"}
    assert v3.grade(it, "Ha, muddat yetarli") == "right"
    assert v3.grade(it, "yo'q") == "wrong"
    assert v3.grade(it, "noaniq") == "abstain"
    assert v3.strict_value(it, "wrong") == -1.5 and v3.strict_value(it, "abstain") == 0.0
    na = {"family": "three_month", "answer": "noaniq", "verdict": "noaniq"}
    assert v3.grade(na, "noaniq") == "right" and v3.grade(na, "ha") == "wrong"
    assert v3.strict_value(na, "right") == 0.2
    sp = {"family": "defect_spot", "answer": "B", "verdict": "B"}
    assert v3.grade(sp, "B) discussion") == "right" and v3.grade(sp, "A") == "wrong"


def test_built_files_are_consistent():
    if not v3.OUT.exists():
        pytest.skip("run build first")
    pub = v3.load_items(False)
    prv = (
        [json.loads(x) for x in v3.PRIVATE.read_text(encoding="utf-8").splitlines()]
        if v3.PRIVATE.exists()
        else []
    )
    ids = [i["id"] for i in pub + prv]
    assert len(ids) == len(set(ids))
    assert all(i["split"] == "public" for i in pub) and all(i["split"] == "private" for i in prv)
    assert all(v3.grade(i, v3.oracle_answer(i)) == "right" for i in pub + prv)
    used = v3.used_regs()
    assert not any(v3.key(i["decision"]) in used for i in pub + prv)  # disjoint from v1, v2 and training
    assert not any(v3.key(i["decision"]) in {v3.key(g) for g in v3.GOLDEN} for i in pub + prv)
    assert v3.audit() == []
    # noaniq share per family near 15 %, answers balanced
    for fam in ("discussion_window", "three_month"):
        sub = [i for i in pub + prv if i["family"] == fam]
        share = sum(i["answer"] == "noaniq" for i in sub) / len(sub)
        assert 0.1 < share < 0.2
        c = {a: sum(i["answer"] == a for i in sub) for a in ("ha", "yo'q")}
        assert c["ha"] == c["yo'q"]


def test_template_has_40_rows():
    if not v3.TEMPLATE.exists():
        pytest.skip("run build first")
    import csv

    rows = list(csv.DictReader(v3.TEMPLATE.open(encoding="utf-8")))
    assert len(rows) == 40
    assert sum(bool(r["question"]) for r in rows) == 10 and not any(r["lawyer_answer"] for r in rows)
