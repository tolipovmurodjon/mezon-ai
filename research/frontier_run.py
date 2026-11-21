"""Frontier baseline: Claude Opus 5.5 on the FROZEN MezonBench, closed book and with the same Mezon tools.

    .venv/Scripts/python.exe -X utf8 -m research.frontier_run --mode closed --bench data/bench/mezonbench_v1_1.jsonl \
        --out data/bench/frontier/opus55_closed.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.frontier_run --mode tools  --bench data/bench/mezonbench_v1_1.jsonl \
        --out data/bench/frontier/opus55_tools.jsonl
    (and the same with --bench data/bench/mezonbench_where_v1.jsonl)

Approved by Boss (21 Nov 2026): only the exam's public lex.uz law questions are sent; no decision text, no personal
data. Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile); this script never
prints them. Settings recorded per line: model, effort. Thinking cannot be switched off on Opus 5.5; effort "medium"
(its default) is set explicitly so the run is reproducible. No server-side fallback: a refused item is recorded as a
refusal, never silently answered by another model (that would corrupt the comparison). Tools: mezon.tools.TOOLS run
locally against data/store/laws.sqlite, at most 5 tool rounds, then one final turn with tool_choice none. Resumable.
Score with research.mezonbench score / research.mezonbench_where score.
"""

import argparse
import json
import time
from pathlib import Path

import anthropic

from mezon import tools
from mezon.lawstore.store import LawStore

MODEL = "claude-opus-5-5"
EFFORT = "medium"
FINAL = "Endi vositalarsiz, faqat so'ralgan shaklda yakuniy javobni yozing."


def anthropic_tools() -> list[dict]:
    return [{"name": t["function"]["name"], "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]} for t in tools.TOOLS]


def text_of(content) -> str:
    return "".join(b.text for b in content if b.type == "text").strip()


def run_item(client, law, item: dict, mode: str, rounds: int = 5) -> dict:
    msgs = [{"role": "user", "content": item["prompt"]}]
    calls, usage_in, usage_out = [], 0, 0
    kw = {"model": MODEL, "max_tokens": 16000, "system": item["system"], "output_config": {"effort": EFFORT}}
    if mode == "tools":
        kw["tools"] = anthropic_tools()
    for rnd in range(rounds + 1):
        last = mode == "tools" and rnd == rounds
        extra = {"tool_choice": {"type": "none"}} if last else {}
        if last:
            msgs.append({"role": "user", "content": FINAL})
        r = client.messages.create(messages=msgs, **kw, **extra)
        usage_in += r.usage.input_tokens
        usage_out += r.usage.output_tokens
        if r.stop_reason == "refusal":
            cat = r.stop_details.category if r.stop_details else None
            return {"answer": "", "refusal": cat, "calls": calls, "in": usage_in, "out": usage_out}
        uses = [b for b in r.content if b.type == "tool_use"]
        if mode != "tools" or not uses or last:
            return {"answer": text_of(r.content), "calls": calls, "in": usage_in, "out": usage_out,
                    "stop": r.stop_reason}
        msgs.append({"role": "assistant", "content": r.content})  # keep thinking + tool_use blocks unchanged
        results = []
        for u in uses:
            res = tools.call(u.name, dict(u.input), law)
            calls.append({"name": u.name, "args": dict(u.input), "ok": "error" not in res})
            results.append({"type": "tool_result", "tool_use_id": u.id,
                            "content": json.dumps(res, ensure_ascii=False)[:4000], "is_error": "error" in res})
        msgs.append({"role": "user", "content": results})  # all results of one turn in a single message
    return {"answer": "", "calls": calls, "in": usage_in, "out": usage_out, "stop": "rounds"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["closed", "tools"], required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    client = anthropic.Anthropic(max_retries=6)
    law = LawStore()
    items = [json.loads(x) for x in Path(a.bench).read_text(encoding="utf-8").split("\n") if x.strip()]
    if a.limit:
        items = items[: a.limit]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").split("\n") if x.strip()} if out.exists() else set()
    t0, tin, tout = time.time(), 0, 0
    with out.open("a", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            if it["id"] in done:
                continue
            try:
                res = run_item(client, law, it, a.mode)
            except anthropic.BadRequestError as e:
                res = {"answer": "", "error": f"bad_request: {e.message}"[:300]}
            tin += res.get("in", 0)
            tout += res.get("out", 0)
            f.write(json.dumps({"id": it["id"], "model": MODEL, "effort": EFFORT, "mode": a.mode, **res},
                               ensure_ascii=False) + "\n")
            f.flush()
            if n % 20 == 0:
                cost = tin / 1e6 * 4 + tout / 1e6 * 20
                print(f"{n}/{len(items)} done, {time.time() - t0:.0f}s, tokens in {tin} out {tout}, ~${cost:.2f}",
                      flush=True)
    print(f"FRONTIER DONE {out}: tokens in {tin} out {tout}, ~${tin / 1e6 * 4 + tout / 1e6 * 20:.2f}", flush=True)


if __name__ == "__main__":
    main()
