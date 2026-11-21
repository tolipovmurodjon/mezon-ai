"""Pilot A data and encoder: masking logic with a stub tokenizer, gates on synthetic rows, and (if built) the real files."""

import json
import re
from pathlib import Path

import pytest

from research.internship_data import (
    BENCH,
    art_root,
    check_gates,
    load_exam,
    load_exam_exact,
    quote_of,
    show_decision,
)
from research.internship_encode import assistant_spans, encode_multi

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train" / "internship_sft.jsonl"
VAL = ROOT / "data" / "train" / "internship_val.jsonl"

RENDERED = (
    "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nQ<|im_end|>\n"
    "<|im_start|>assistant\n<think>\nplan\n</think>\n\n<tool_call>\n<function=f>\n</function>\n</tool_call><|im_end|>\n"
    "<|im_start|>user\n<tool_response>\n{}\n</tool_response><|im_end|>\n"
    "<|im_start|>assistant\n<think>\nread\n</think>\n\nanswer<|im_end|>\n"
)


class CharTok:
    """One token per character; enough to test which characters get a label."""

    def apply_chat_template(self, messages, tools=None, tokenize=False):
        return RENDERED

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        return {"input_ids": [ord(c) for c in text], "offset_mapping": [(i, i + 1) for i in range(len(text))]}


def test_spans_cover_assistant_turns_only():
    spans = assistant_spans(RENDERED)
    assert len(spans) == 2
    texts = [RENDERED[s:e] for s, e in spans]
    assert texts[0].startswith("plan") and texts[0].endswith("<|im_end|>")
    assert texts[1].startswith("read") and texts[1].endswith("<|im_end|>")
    assert all("<|im_start|>" not in t for t in texts)


def test_encode_multi_masks_everything_else():
    ids, labels = encode_multi(CharTok(), [], None, 10_000)
    got = "".join(chr(t) for t in labels if t != -100)
    assert "plan" in got and "<tool_call>" in got and "answer" in got and got.endswith("<|im_end|>")
    for banned in ("<tool_response>", "{}", "S<|im_end|>", "Q", "<|im_start|>"):
        assert banned not in got
    assert len(ids) == len(labels) == len(RENDERED)


def test_encode_multi_rejects_too_long_instead_of_cutting():
    assert encode_multi(CharTok(), [], None, 50) is None


def test_quote_of_is_verbatim_prefix_in_range():
    import random

    t = "Bu juda uzun modda matni " * 30
    q = quote_of(t, random.Random(1))
    assert t.startswith(q) and 60 <= len(q) <= 220


def test_art_root():
    assert art_root("art:73/part:2") == "art:73"
    assert art_root("annex:1/cl:92") == "annex:1"
    assert art_root("art:12-1") == "art:12-1"


def _row(fam, final, calls=2, **kw):
    return {
        "kind": "legal",
        "family": fam,
        "final": final,
        "calls": calls,
        "messages": [{}, {"content": f"{fam}-{final}-{kw.get('i', 0)}"}],
        "tags": {"reason": kw.get("reason")},
        **kw,
    }


def test_gates_catch_a_collapsed_binary_family():
    rows = [_row("in_force", "ha", i=i) for i in range(90)] + [
        _row("in_force", "yo'q", i=i + 90) for i in range(10)
    ]
    assert any("in_force" in f for f in check_gates(rows))


def test_gates_pass_balanced_rows():
    rows = []
    for i in range(60):
        rows.append(_row("in_force", "ha" if i % 2 else "yo'q", calls=1 + i % 2, i=i))
        rows.append(_row("flip", "A" if i % 2 else "B", calls=2, i=i + 100))
        rows.append(_row("abstain", "noaniq", calls=2, reason=f"r{i % 3}", i=i + 200))
    rows += [
        {"kind": "replay", "family": "replay_tulu", "messages": [{}, {"content": str(i)}], "tags": {}}
        for i in range(300)
    ]
    assert check_gates(rows) == []


def test_show_decision_keeps_flagged_clause_and_marks_cut():
    dec = {
        "reg_number": "1-1-1-Q/24",
        "adopted": "2024-01-01",
        "body": "b",
        "title": "t",
        "preamble": "p" * 300,
        "url": "u",
        "clauses": [f"Band {i}. " + "matn " * 80 for i in range(12)],
    }
    out = json.loads(show_decision(dec, ["Band 9. matn matn matn matn matn matn matn"]))
    assert out["kesilgan"] is True and any(c.startswith("Band 9.") for c in out["clauses"])
    assert out["clauses"] == sorted(out["clauses"], key=lambda c: int(re.match(r"Band (\d+)", c).group(1)))


def test_exam_loader_counts_both_frozen_files():
    if not all(p.exists() for p in BENCH):
        pytest.skip("frozen exam files missing")
    arts, pairs = load_exam()
    assert len(arts) > 250 and len(pairs) >= 30


@pytest.mark.skipif(not TRAIN.exists(), reason="run research.internship_data first")
def test_built_files_have_no_exam_article_and_valid_calls():
    arts, _ = load_exam()
    exact = load_exam_exact()
    rows = [
        json.loads(x)
        for x in TRAIN.read_text(encoding="utf-8").split("\n") + VAL.read_text(encoding="utf-8").split("\n")
        if x.strip()
    ]
    assert rows
    for r in rows:
        if r["kind"] not in ("legal", "audit_dev"):
            continue
        names = []
        for m in r["messages"]:
            if m["role"] == "tool":
                body = json.loads(m["content"])
                for h in [body, *body.get("hits", [])]:
                    if (
                        r["family"] in ("audit", "audit_dev") or r["kind"] == "audit_dev"
                    ):  # audit: exact (act, path) rule
                        assert (h.get("act_key"), h.get("path", "")) not in exact
                    else:  # every other slice: the stricter article-level rule
                        assert (h.get("act_key"), art_root(h.get("path", ""))) not in arts
            if m["role"] == "assistant":
                assert 15 <= len(m["reasoning_content"].split()) <= 120 or r["family"] == "audit"
                names += [tc["function"]["name"] for tc in m.get("tool_calls", [])]
        assert names == [m["tool_calls"][0]["function"]["name"] for m in r["messages"] if m.get("tool_calls")]
        assert r["messages"][-1]["role"] == "assistant" and not r["messages"][-1].get("tool_calls")


# ---------------------------------------------------------------------------------------------- internship v2
V2_TRAIN = ROOT / "data" / "train" / "internship_v2.jsonl"
V2_VAL = ROOT / "data" / "train" / "internship_v2_val.jsonl"
V2_FAMILIES = ("dead_date", "name_recover", "name_recover_quote", "chain_date")


def _v2_rows(*paths):
    return [json.loads(x) for p in paths for x in p.read_text(encoding="utf-8").split("\n") if x.strip()]


def test_v2_leak_sets_cover_every_bench_file():
    from research.internship_v2 import bench_files, load_leak_sets

    arts, regs, n = load_leak_sets()
    assert n == len(bench_files()) and n >= 20
    assert len(arts) >= 400 and "231-4-59-Q/24" in regs and len(regs) > 100


def test_v2_dead_date_grades_with_the_exam_grader():
    from research.internship_v2 import lost_phrase
    from research.mezonbench_v2 import grade

    item = {"family": "dead_cite", "verdict": "yo'q", "gold_date": "2024-10-19"}
    for tail in ("iso", "short", "dmy", "iso2"):
        assert grade(item, lost_phrase("iso", "2024-10-19", tail)) == "right"
    assert grade(item, "yo'q") == "wrong"  # the date is required: the base model's failure mode
    assert (
        grade(
            {"family": "dead_cite", "verdict": "ha", "gold_date": None}, "ha, amalda (tahrir: 01.01.2024 00)"
        )
        == "right"
    )


@pytest.mark.skipif(not V2_TRAIN.exists(), reason="run research.internship_v2 first")
def test_v2_files_new_families_clean_and_procedural():
    from research.internship_v2 import load_leak_sets
    from research.mezonbench_v2 import dates_in

    arts, regs, _ = load_leak_sets()
    rows = _v2_rows(V2_TRAIN, V2_VAL)
    new = [r for r in rows if r["family"] in V2_FAMILIES]
    assert {r["family"] for r in new} == set(V2_FAMILIES)
    assert any(r["family"] == "name_recover" and r["calls"] >= 4 for r in new)
    for r in rows:
        blob = json.dumps(r["messages"], ensure_ascii=False)
        assert not any(
            g in blob for g in regs
        )  # no bench or golden registration number anywhere, v1 rows included
        for m in r["messages"]:
            if m["role"] == "tool":
                body = json.loads(m["content"])
                for h in [body, *body.get("hits", [])]:
                    assert (h.get("act_key"), art_root(h.get("path", ""))) not in arts or r["family"] in (
                        "audit",
                        "audit_dev",
                    )
    for r in new:
        names = [tc["function"]["name"] for m in r["messages"] for tc in m.get("tool_calls", [])]
        assert names and r["messages"][-1]["role"] == "assistant"
        if r["final"].startswith(
            "yo'q,"
        ):  # a dead answer carries its date and it was found by list_editions + probes
            assert "list_editions" in names and dates_in(r["final"])
            assert r["calls"] >= 3
        if r["family"].startswith("name_recover"):
            assert json.loads(next(m for m in r["messages"] if m["role"] == "tool")["content"])[
                "error"
            ].startswith("act not in")
        if r["family"] == "chain_date" and r["final"].startswith("Ha."):
            assert len(r["final"]) - 4 >= 60
    mid = [r for r in new if r["family"] != "name_recover_quote"]
    ha = sum(1 for r in mid if r["final"].lower().startswith(("ha",)))
    assert 0.40 <= ha / len(mid) <= 0.60
