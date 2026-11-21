"""MezonBench v2.2: oracle, fixed answer keys, new families, and a frozen manifest."""

import json
from collections import Counter

import pytest

from research import mezonbench_v2 as v2
from research import mezonbench_v22 as v22

needs = pytest.mark.skipif(not (v22.PUBLIC.exists() and v22.PRIVATE.exists()), reason="v2.2 not built")


@needs
def test_oracle_is_100_percent():
    items = v22.load_all()
    assert all(v22.grade(i, v22.oracle_answer(i)) == "right" for i in items)


@needs
def test_conflict_pair_accepts_6_or_18_for_different_force():
    items = [i for i in v22.load_all() if i["family"] == "conflict_pair"]
    diff = next(i for i in items if i["rule"].startswith("different_force"))
    for art in ("6", "18"):
        assert v22.grade(diff, f"{diff['verdict']}, {art}-modda") == "right"
    eq = next(i for i in items if i["rule"] == "equal_force_later")
    assert v22.grade(eq, f"{eq['verdict']}, 6-modda") == "wrong"


@needs
def test_noaniq_future_items_state_the_reference_date():
    for i in v22.load_all():
        if i["family"] == "noaniq" and i["why"] == "date_after_store_end":
            assert i["prompt"].startswith(f"Bugun {v22.TODAY}.")
        assert i["why"] != "edition_gap" if i["family"] == "noaniq" else True


@needs
def test_new_families_balanced_and_not_trivial():
    items = v22.load_all()
    th = [i["verdict"] for i in items if i["family"] == "two_hop"]
    assert abs(th.count("ha") - th.count("yo'q")) <= 2
    for fam in v22.NEW_FAMS:
        sub = [i for i in items if i["family"] == fam]
        assert len(sub) >= 30
        for c in ("ha", "yo'q", "A", "B", "C", "D", "0", "1", "noaniq"):
            assert sum(v22.grade(i, c) == "right" for i in sub) / len(sub) < 0.5


@needs
def test_ids_unique_and_manifest_hashes_match():
    items = v22.load_all()
    assert len({i["id"] for i in items}) == len(items)
    man = json.loads(v22.FROZEN.read_text(encoding="utf-8"))
    for p in (v22.PUBLIC, v22.PRIVATE):
        assert man["items"][p.name]["sha256_16"] == v2.sha(p)
    assert Counter(i["family"] for i in items)["noaniq"] == 75
