"""Strict-judge pilot, step 4: rejection sampling. Keep only verified-good trajectories, write the SFT file.

    python -X utf8 -m research.judge_select --traj data/train/judge_traj_r1.jsonl --out data/train/judge_sft_r1.jsonl

Rules (internship_rl_pilot.md 2.4, adapted to the tool loop):
  * a trajectory is good when its reward is +1.0 (answerable) or +0.2 (unanswerable, warranted noaniq) and it did not
    need the forced tool-free turn;
  * binary families (flip, in_force, hierarchy) and unanswerable items need a question pass rate >= min_rate (default
    6/8 = 0.75: a coin-flipper passes 6 of 8 with probability 37/256 = 14 % per question, but a flip-only guesser also
    loses on the A/B twin, and the balance cap below removes a one-sided policy); lookup and where keep at any rate;
  * trajectories with more than max_calls tool calls (default 5) are dropped;
  * at most max_per_q (default 2) per question, fewest tool calls first, random tie-break;
  * answer balance: inside a binary family no gold class (A/B, ha/yo'q) exceeds max_share (default 0.55) of the kept
    answerable rows; the larger class is trimmed at random.
Output rows: {"kind": "instr", "messages": [...], "tools": true, "id", "family", "gold"}; "tools": true tells the trainer
to render with tools=mezon.tools.TOOLS (the internship row format). Messages hold the tool calls as assistant
`tool_calls` and the responses as role "tool" messages, exactly as the sampler ran them.
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ("flip", "in_force", "hierarchy")


def is_good(t: dict) -> bool:
    return t["outcome"] in ("right", "warranted_abstain") and not t.get("forced")


def to_sft_row(t: dict) -> dict:
    return {
        "kind": "instr",
        "messages": t["messages"],
        "tools": True,
        "id": t["id"],
        "family": t["family"],
        "gold": t["gold"] if t["family"] in BINARY else "",
    }


def select(
    rows: list[dict],
    k: int = 8,
    max_per_q: int = 2,
    max_calls: int = 5,
    min_rate: float = 6 / 8,
    max_share: float = 0.55,
    seed: int = 1,
) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    by_q: dict[str, list[dict]] = defaultdict(list)
    for t in rows:
        by_q[t["id"]].append(t)
    stats = Counter()
    kept: list[dict] = []
    for ts in by_q.values():
        stats["questions"] += 1
        good = [t for t in ts if is_good(t)]
        if not good:
            stats["no_good_sample"] += 1
            continue
        strict = ts[0]["family"] in BINARY or bool(ts[0].get("unans"))
        rate = sum(t["outcome"] in ("right", "warranted_abstain") for t in ts) / max(len(ts), k)
        if strict and rate < min_rate:
            stats["dropped_pass_rate"] += 1
            continue
        short = [t for t in good if t["n_calls"] <= max_calls]
        stats["dropped_calls"] += len(good) - len(short)
        if not short:
            continue
        rng.shuffle(short)
        short.sort(key=lambda t: t["n_calls"])
        kept += short[:max_per_q]
    # answer balance inside each binary family (answerable items only)
    final = [t for t in kept if t.get("unans") or t["family"] not in BINARY]
    for fam in BINARY:
        grp = [t for t in kept if t["family"] == fam and not t.get("unans")]
        while grp:
            c = Counter(t["gold"] for t in grp)
            top, n_top = c.most_common(1)[0]
            if n_top / len(grp) <= max_share or len(c) < 2:
                break
            victim = rng.choice([t for t in grp if t["gold"] == top])
            grp.remove(victim)
            stats["dropped_balance"] += 1
        final += grp
    final.sort(key=lambda t: (t["id"], t["sample"]))
    rng.shuffle(final)  # so the last rows can serve as a held-out slice
    stats["kept"] = len(final)
    return final, dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traj", default=str(ROOT / "data" / "train" / "judge_traj_r1.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "data" / "train" / "judge_sft_r1.jsonl"))
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--max-per-q", type=int, default=2)
    ap.add_argument("--max-calls", type=int, default=5)
    ap.add_argument("--min-rate", type=float, default=0.75)
    ap.add_argument("--max-share", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rows = [json.loads(x) for x in Path(a.traj).read_text(encoding="utf-8").split("\n") if x.strip()]
    kept, stats = select(rows, a.k, a.max_per_q, a.max_calls, a.min_rate, a.max_share, a.seed)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for t in kept:
            f.write(json.dumps(to_sft_row(t), ensure_ascii=False) + "\n")
    print(f"{a.traj}: {len(rows)} trajectories, {stats.get('questions', 0)} questions")
    print("outcomes:", dict(Counter(t["outcome"] for t in rows)))
    print("select stats:", stats)
    print("kept by family:", dict(Counter(t["family"] + ("/unans" if t.get("unans") else "") for t in kept)))
    for fam in BINARY:
        print(
            f"  gold shares {fam}:",
            dict(Counter(t["gold"] for t in kept if t["family"] == fam and not t.get("unans"))),
        )
    print("tool calls per kept row:", dict(sorted(Counter(t["n_calls"] for t in kept).items())))
    print(f"wrote {out}: {len(kept)} rows")


if __name__ == "__main__":
    main()
