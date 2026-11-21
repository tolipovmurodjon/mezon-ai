import json

from research import judge_reward as jr
from research import judge_select as js

FLIP = {"family": "flip", "answer": "A", "unans": ""}
INF = {"family": "in_force", "answer": "yo'q", "unans": ""}
LOOK = {
    "family": "lookup",
    "answer": "Bu modda matni juda uzun va aniq bir jumla bo'lib, kamida oltmish belgidan iborat.",
    "unans": "",
}
UNANS = {"family": "in_force", "answer": "noaniq", "unans": "gap"}
WHERE = {
    "family": "where",
    "answer": "x",
    "article": "40",
    "act_number": "O'RQ-682",
    "act_title": "Normativ-huquqiy hujjatlar",
    "unans": "",
}


def test_reward_levels():
    assert jr.reward(FLIP, "A") == (1.0, "right")
    assert jr.reward(FLIP, "B") == (-1.5, "wrong")
    assert jr.reward(FLIP, "noaniq") == (-0.25, "lazy_abstain")
    assert jr.reward(INF, "yo'q") == (1.0, "right")
    assert jr.reward(INF, "ha") == (-1.5, "wrong")
    assert jr.reward(INF, "Noaniq.") == (-0.25, "lazy_abstain")


def test_unanswerable():
    assert jr.reward(UNANS, "noaniq") == (0.2, "warranted_abstain")
    assert jr.reward(UNANS, "ha") == (-1.5, "wrong")
    assert jr.reward(UNANS, "yo'q") == (-1.5, "wrong")


def test_broken():
    assert jr.reward(FLIP, "") == (-1.0, "broken")
    assert jr.reward(FLIP, "<tool_call>x</tool_call>") == (-1.0, "broken")
    assert jr.reward(INF, "balki") == (-1.0, "broken")
    assert jr.reward(FLIP, "A" + " juda uzun" * 80) == (-1.0, "broken")
    assert jr.reward(UNANS, "") == (-1.0, "broken")


def test_lookup_and_where():
    assert jr.reward(LOOK, LOOK["answer"][:80]) == (1.0, "right")
    assert (
        jr.reward(
            LOOK, "butunlay boshqa matn, bu modda yo'q bo'lgan gap, yetmish belgidan ko'proq uzunlikda."
        )[0]
        == -1.5
    )
    assert jr.reward(WHERE, "O'RQ-682, 40-modda") == (1.0, "right")
    assert jr.reward(WHERE, "O'RQ-682, 41-modda")[0] == -1.5


import itertools

_c = itertools.count()


def _traj(qid, fam, ans, rew, outcome, calls=1, gold="A", unans=""):
    return {
        "id": qid,
        "sample": next(_c),
        "family": fam,
        "gold": gold,
        "unans": unans,
        "answer": ans,
        "reward": rew,
        "outcome": outcome,
        "n_calls": calls,
        "forced": False,
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "user", "content": qid},
            {"role": "assistant", "content": ans},
        ],
    }


def test_select_rules(tmp_path):
    rows = []
    # flip q1: 7/8 right -> kept (max 2); q2: 5/8 right -> dropped; lookup l1: 1/8 right -> kept
    rows += [_traj("q1", "flip", "A", 1.0, "right") for _ in range(7)] + [
        _traj("q1", "flip", "B", -1.5, "wrong")
    ]
    rows += [_traj("q2", "flip", "A", 1.0, "right") for _ in range(5)] + [
        _traj("q2", "flip", "B", -1.5, "wrong") for _ in range(3)
    ]
    rows += [_traj("l1", "lookup", "txt", 1.0, "right", gold="txt")] + [
        _traj("l1", "lookup", "x", -1.5, "wrong", gold="txt") for _ in range(7)
    ]
    # too many tool calls
    rows += [_traj("q3", "in_force", "ha", 1.0, "right", calls=6, gold="ha") for _ in range(8)]
    # unanswerable: warranted abstentions 7/8
    rows += [
        _traj("u1", "in_force", "noaniq", 0.2, "warranted_abstain", gold="noaniq", unans="gap")
        for _ in range(7)
    ]
    rows += [_traj("u1", "in_force", "ha", -1.5, "wrong", gold="noaniq", unans="gap")]
    kept, stats = js.select(rows, k=8, max_per_q=2, max_calls=5, min_rate=6 / 8, max_share=0.55, seed=1)
    ids = [r["id"] for r in kept]
    assert (
        ids.count("q1") == 2
        and "q2" not in ids
        and ids.count("l1") == 1
        and "q3" not in ids
        and ids.count("u1") == 2
    )
    assert stats["dropped_pass_rate"] >= 1 and stats["dropped_calls"] >= 1


def test_balance_cap():
    rows = []
    for i in range(30):
        rows += [_traj(f"a{i}", "flip", "A", 1.0, "right") for _ in range(8)]
    for i in range(5):
        rows += [_traj(f"b{i}", "flip", "B", 1.0, "right", gold="B") for _ in range(8)]
    kept, _ = js.select(rows, k=8, max_per_q=2, max_calls=5, min_rate=0.75, max_share=0.55, seed=1)
    a = sum(r["gold"] == "A" for r in kept)
    assert a / len(kept) <= 0.55 + 1e-9


def test_sft_row_format(tmp_path):
    r = _traj("q1", "flip", "A", 1.0, "right")
    row = js.to_sft_row(r)
    assert row["tools"] is True and row["kind"] == "instr" and row["messages"][-1]["role"] == "assistant"
    json.dumps(row)


def test_sample_resume(tmp_path):
    from research import judge_sample as sm

    items = [
        {"id": "q1", "family": "flip", "answer": "A", "system": "s", "prompt": "p", "unans": ""},
        {"id": "q2", "family": "in_force", "answer": "ha", "system": "s", "prompt": "p", "unans": ""},
    ]
    out = tmp_path / "t.jsonl"
    calls = []

    def fake(msgs_list):
        calls.append(len(msgs_list))
        return [
            {
                "answer": "A",
                "calls": [],
                "forced": False,
                "messages": [*m, {"role": "assistant", "content": "A"}],
            }
            for m in msgs_list
        ]

    assert sm.sample_all(items, 3, out, fake, batch=4, log=lambda *a, **k: None) == 6
    assert (
        sm.sample_all(items, 3, out, fake, batch=4, log=lambda *a, **k: None) == 0
    )  # resumable: nothing left
    assert (
        sm.sample_all(items, 4, out, fake, batch=4, log=lambda *a, **k: None) == 2
    )  # k raised: only the extras
    rows = sm.read_jsonl(out)
    assert len(rows) == 8 and sorted(r["sample"] for r in rows if r["id"] == "q1") == [0, 1, 2, 3]
    assert {r["outcome"] for r in rows if r["id"] == "q1"} == {"right"} and rows[0]["reward"] == 1.0


def test_tool_loop_fake_model():
    from mezon.lawstore.store import LawStore
    from research.bench_tools_run import run_tool_loops

    class Tok:
        def apply_chat_template(self, msgs, tools=None, **kw):
            return json.dumps({"n": len(msgs), "tools": tools is not None})

    call = ("<tool_call><function=law_as_of><parameter=act>O'RQ-682</parameter><parameter=article>40</parameter>"
            "<parameter=date>2025-10-23</parameter></function></tool_call>")

    def gen(texts):
        # a conversation with no tool message yet calls the tool; one that has had it answers; "tools": false = forced turn
        return [call if json.loads(t)["n"] == 2 else "ha" for t in texts]

    m = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    r = run_tool_loops([m, m], gen, Tok(), LawStore(), rounds=4)
    assert [x["answer"] for x in r] == ["ha", "ha"] and all(len(x["calls"]) == 1 and not x["forced"] for x in r)
    assert r[0]["messages"][2]["tool_calls"][0]["function"]["name"] == "law_as_of" and r[0]["messages"][3]["role"] == "tool"
    # a model that always calls tools is forced to answer after the rounds are used up
    r2 = run_tool_loops([m], lambda ts: [call] * len(ts), Tok(), LawStore(), rounds=2)[0]
    assert r2["forced"] is True and len(r2["calls"]) == 3
