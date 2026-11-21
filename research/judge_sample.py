"""Strict-judge pilot, step 3: sample k tool-loop answers per question and score each with the reward. One GPU.

    python -X utf8 -m research.judge_sample --model ~/models/Qwen3.8-27B [--adapter data/models/X/final] \
        [--questions data/train/judge_q_r1.jsonl] [--out data/train/judge_traj_r1.jsonl] [--k 8] [--batch 16]

Policy = the tools exam's loop (research.bench_tools_run.run_tool_loops: Qwen tool template, mezon/tools.py, XML or JSON
calls via parse_call, forced tool-free final answer), sampled at temperature 1.0, top_p 0.95. Every trajectory is one JSONL
line: id, sample, family, gold, unans, answer, reward, outcome, n_calls, forced, calls, messages (system+user, tool calls,
tool responses, final answer). Resumable per trajectory (rerun continues; a half batch is simply redone), batch = number
of conversations stepped together. Nothing leaves the machine; no model is called except the local one.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.bench_tools_run import HINT
from research.judge_reward import reward

QUESTIONS = ROOT / "data" / "train" / "judge_q_r1.jsonl"
OUT = ROOT / "data" / "train" / "judge_traj_r1.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").split("\n") if x.strip()]


def initial_messages(item: dict) -> list[dict]:
    return [{"role": "system", "content": item["system"] + HINT}, {"role": "user", "content": item["prompt"]}]


def pending(items: list[dict], have: Counter, k: int) -> list[tuple[dict, int]]:
    """(question, sample index) still to do, interleaved so every question gets samples early."""
    todo = [(it, j) for j in range(k) for it in items if j >= have[it["id"]]]
    return todo


def record(item: dict, j: int, r: dict) -> dict:
    rew, outcome = reward(item, r["answer"])
    return {
        "id": item["id"],
        "sample": j,
        "family": item["family"],
        "gold": item["answer"],
        "unans": item.get("unans", ""),
        "answer": r["answer"],
        "reward": rew,
        "outcome": outcome,
        "n_calls": len(r["calls"]),
        "forced": r["forced"],
        "calls": r["calls"],
        "messages": r["messages"],
    }


def sample_all(items: list[dict], k: int, out: Path, run_batch, batch: int = 16, log=print) -> int:
    """run_batch(list of message lists) -> list of {"answer", "calls", "messages", "forced"}. Returns trajectories written."""
    have = Counter(t["id"] for t in read_jsonl(out))
    todo = pending(items, have, k)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0, n = time.time(), 0
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for s in range(0, len(todo), batch):
            chunk = todo[s : s + batch]
            results = run_batch([initial_messages(it) for it, _ in chunk])
            # sample index = how many of this question are already stored (stable under resume)
            for (it, _), r in zip(chunk, results):
                j = have[it["id"]]
                have[it["id"]] += 1
                f.write(json.dumps(record(it, j, r), ensure_ascii=False) + "\n")
                n += 1
            f.flush()
            log(f"{n}/{len(todo)} trajectories, {time.time() - t0:.0f}s", flush=True)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default="")
    ap.add_argument("--questions", default=str(QUESTIONS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: first N questions")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    import torch

    from mezon.lawstore.store import LawStore
    from research.bench_tools_run import load_model, make_generate, run_tool_loops

    torch.manual_seed(a.seed)
    items = read_jsonl(Path(a.questions))
    if a.limit:
        items = items[: a.limit]
    law = LawStore()
    tok, model = load_model(a.model, a.adapter)
    generate = make_generate(model, tok, sample=True, temperature=1.0, top_p=0.95)

    def run_batch(msgs):
        return run_tool_loops(msgs, generate, tok, law, a.rounds)

    n = sample_all(items, a.k, Path(a.out), run_batch, a.batch)
    rows = read_jsonl(Path(a.out))
    print("outcomes:", dict(Counter(r["outcome"] for r in rows)))
    print(f"JUDGE SAMPLE DONE {a.out}: wrote {n}, total {len(rows)}")


if __name__ == "__main__":
    main()
