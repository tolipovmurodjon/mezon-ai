from pathlib import Path


def test_long_answer_families_get_room():
    src = Path("research/bench_run.py").read_text(encoding="utf-8")
    assert 'short = it["family"] in ("flip", "in_force", "hierarchy")' in src
    assert "(24 if short else 200)" in src
