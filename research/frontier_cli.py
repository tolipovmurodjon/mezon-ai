"""Frontier baseline through the Claude Code CLI (Boss's approval, 21 Nov 2026: "for Opus use Claude Code CLI").

    .venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode closed --per-family 30 --out data/bench/frontier/opus55_closed30.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode tools  --per-family 30 --out data/bench/frontier/opus55_tools30.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode closed --bench data/bench/mezonbench_where_v1.jsonl --out ...

Fairness: the same items (research.bench_tools_run.balanced_subset, seed 5), the same system prompt (+ the same tools
HINT in tools mode), the same 5 law tools as Qwen (research.mezon_mcp). Clean context:
--setting-sources "" (no CLAUDE.md, no memory, no hooks), --tools "" (no shell, files or web), --strict-mcp-config,
run from an empty folder. Only public lex.uz law questions are sent. Resumable; 2 workers (laptop RAM is small).
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.bench_run import FORCE
from research.bench_tools_run import HINT, balanced_subset

MODEL = "claude-opus-5-5"
EFFORT = "medium"
EMPTY = Path(tempfile.gettempdir()) / "mezon_frontier_empty"
MCP = {"mcpServers": {"mezon": {"command": str(ROOT / ".venv" / "Scripts" / "python.exe"),
                                "args": ["-X", "utf8", str(ROOT / "research" / "mezon_mcp.py")]}}}


def ask(item: dict, mode: str) -> dict:
    cmd = ["claude", "-p", "--model", MODEL, "--effort", EFFORT, "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--no-session-persistence", "--output-format", "json", "--max-turns", "8",
           "--system-prompt", item["system"] + (HINT if mode == "tools" else "") + (FORCE if mode == "forced" else "")]
    if mode == "tools":
        cfg = EMPTY / "mcp.json"
        cmd += ["--mcp-config", str(cfg), "--allowedTools", ("mcp__mezon__law_as_of,mcp__mezon__list_editions,"
                "mcp__mezon__search_law,mcp__mezon__verify_quote,mcp__mezon__get_decision")]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=item["prompt"], check=False, capture_output=True, text=True, encoding="utf-8",
                           cwd=EMPTY, timeout=600)
        r = json.loads(p.stdout)
        return {"answer": (r.get("result") or "").strip(), "turns": r.get("num_turns"), "cost_usd": r.get("total_cost_usd"),
                "is_error": r.get("is_error"), "secs": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001 - recorded, never silently dropped
        return {"answer": "", "error": f"{type(e).__name__}: {e}"[:300], "secs": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["closed", "tools", "forced"], required=True)
    ap.add_argument("--bench", default=str(ROOT / "data" / "bench" / "mezonbench_v1.jsonl"))
    ap.add_argument("--per-family", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    EMPTY.mkdir(exist_ok=True)
    (EMPTY / "mcp.json").write_text(json.dumps(MCP), encoding="utf-8")
    items = [json.loads(x) for x in Path(a.bench).read_text(encoding="utf-8").split("\n") if x.strip()]
    if a.per_family:
        items = balanced_subset(items, a.per_family)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").split("\n") if x.strip()} if out.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    print(f"{len(items)} items, {len(todo)} to do, mode {a.mode}", flush=True)
    t0, cost = time.time(), 0.0
    with out.open("a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as pool:
        for n, (it, res) in enumerate(zip(todo, pool.map(lambda x: ask(x, a.mode), todo)), 1):
            cost += res.get("cost_usd") or 0
            f.write(json.dumps({"id": it["id"], "family": it["family"], "model": MODEL, "effort": EFFORT,
                                "mode": a.mode, **res}, ensure_ascii=False) + "\n")
            f.flush()
            if n % 10 == 0:
                print(f"{n}/{len(todo)} done, {time.time() - t0:.0f}s, api-equivalent ${cost:.2f}", flush=True)
    print(f"FRONTIER DONE {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
