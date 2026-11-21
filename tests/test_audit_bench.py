"""MezonAudit-bench: grader maths, the citation gate, the disabled cloud path, split hygiene, the tool-loop plumbing."""

import json
from pathlib import Path

import pytest

from research.audit_bench import grade, harness, instances

DATA = Path(__file__).resolve().parents[1] / "data" / "bench" / "audit_v1"
needs_data = pytest.mark.skipif(not (DATA / "manifest.json").exists(), reason="bench not built")


def test_wilson_and_pass_hat_k():
    lo, hi = grade.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert grade.wilson(0, 0) == (0.0, 0.0)
    run = lambda *ok: [{"id": str(i), "resolved": r} for i, r in enumerate(ok)]
    ph = grade.pass_hat_k([run(True, True, False), run(True, False, False)])
    assert ph[1] == pytest.approx(0.5) and ph[2] == pytest.approx(1 / 3)


def test_parse_prediction():
    assert grade.parse_prediction({"id": "x", "verdict": "Positive"})["verdict"] == "positive"
    assert grade.parse_prediction({"id": "x", "verdict": "illegal"}) is None
    p = grade.parse_prediction({"id": "x", "verdict": "negative", "defects": [{"type": "nonsense"}]})
    assert p["defects"][0]["type"] == "other"


def test_extract_json_takes_the_last_object_and_ignores_fences():
    ans = 'thinking {"a": 1}\n```json\n{"verdict": "negative", "defects": []}\n```'
    assert harness.extract_json(ans)["verdict"] == "negative"
    assert harness.extract_json("no json here") is None


def test_cloud_is_disabled_by_default():
    with pytest.raises(SystemExit):
        harness.run_cloud([], Path("never.jsonl"), allow=False)


@needs_data
def test_baselines_oracle_resolves_all_and_empty_none():
    from mezon.lawstore.store import LawStore
    from mezon.rules.common import SafeLaw

    law, safe = LawStore(), SafeLaw(LawStore())
    items = grade.collect(("real", "smith", "clean"), private=False)
    assert items
    for mode, want in (("oracle", True), ("empty", False), ("always-positive", None)):
        rows = [grade.grade_one(law, i, g, harness.predict_baseline(mode, i, g, safe)) for i, g, _ in items]
        if want is True:
            assert all(r["resolved"] for r in rows), [r for r in rows if not r["resolved"]][:2]
        if want is False:
            assert not any(r["resolved"] for r in rows)
        if want is None:  # constant "positive" resolves exactly the CLEAN split
            assert {r["split"] for r in rows if r["resolved"]} == {"clean"}


@needs_data
def test_citation_gate_counts_fabricated_and_misgrounded():
    from mezon.lawstore.store import LawStore

    law = LawStore()
    ins = {"id": "t", "date": "2025-03-01", "text": "bir ikki uch"}
    good = {"act": "O'RQ-682", "article": "16", "on_date": "2025-03-01"}
    from mezon.tools import law_as_of

    quote = law_as_of(law, "O'RQ-682", "16", "2025-03-01")["text"][:60]
    assert grade.check_citation(law, {**good, "quote": quote}, "2025-03-01") == "ok"
    assert (
        grade.check_citation(law, {**good, "article": "9999", "quote": quote}, "2025-03-01") == "fabricated"
    )
    assert (
        grade.check_citation(
            law, {**good, "quote": "this sentence is not in the article at all"}, "2025-03-01"
        )
        == "fabricated"
    )
    assert grade.check_citation(law, {**good, "quote": ""}, "2025-03-01") == "ungrounded"
    assert (
        grade.check_citation(law, {"act": "no such act xyz", "article": "1", "quote": "abc"}, "2025-03-01")
        == "fabricated"
    )
    assert (
        grade.check_citation(law, {"act": "lsp", "article": "25", "quote": "Mahalliy"}, "2025-03-01")
        == "misgrounded"
    )
    pred = {
        "id": "t",
        "verdict": "negative",
        "defects": [{"type": "other", "evidence_quote": "ikki", "citations": []}],
    }
    gate = grade.citation_gate(law, grade.parse_prediction(pred), ins)
    assert not gate["pass"] and gate["counts"]["ungrounded"] == 1


@needs_data
def test_split_hygiene():
    man = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    pub = {s: instances.load(s) for s in ("real", "smith", "clean")}
    priv = {s: instances.load(s, private=True) for s in ("real", "smith", "clean")}
    pub_ids = {i["id"] for p in pub.values() for i, _ in p}
    priv_ids = {i["id"] for p in priv.values() for i, _ in p}
    assert pub_ids and priv_ids and not pub_ids & priv_ids
    assert set(man["private_hashes"]) == priv_ids  # only hashes of private items are published
    for p in pub.values():
        for i, _ in p:
            assert set(i) == {
                "id",
                "reg_number",
                "type",
                "date",
                "title",
                "text",
            }  # no label, trigger or gold in what a model sees
            assert i["reg_number"] not in instances.GOLDEN or i["reg_number"].endswith("-F/24")
    regs = {
        i["reg_number"]
        for p in list(pub.values()) + list(priv.values())
        for i, g in p
        if g["split"] != "smith"
    }
    assert not regs & instances.GOLDEN
    smith_bases = {
        g["base_reg"] for p in list(pub.values()) + list(priv.values()) for _, g in p if g["split"] == "smith"
    }
    assert not smith_bases & (instances.GOLDEN | regs)


def test_tool_loop_plumbing_with_a_stub_model():
    """run_tool_loops + _drive + to_prediction end to end, no GPU: the stub 'model' answers with a JSON conclusion."""
    from research.bench_tools_run import run_tool_loops

    class Tok:
        def apply_chat_template(self, msgs, **kw):
            return "prompt"

    answer = '{"verdict": "positive", "defects": []}'
    out = Path(__file__).parent / "_stub_run.jsonl"
    out.unlink(missing_ok=True)
    try:
        ins = {"id": "a1-stub", "reg_number": "1-Q/24", "date": "2025-01-01", "title": "t", "text": "x"}
        harness._drive(
            [(ins, {})], lambda m: run_tool_loops(m, lambda t: [answer] * len(t), Tok(), None), out, 1
        )
        rec = json.loads(out.read_text(encoding="utf-8"))
        assert rec["id"] == "a1-stub" and grade.parse_prediction(rec)["verdict"] == "positive"
    finally:
        out.unlink(missing_ok=True)
