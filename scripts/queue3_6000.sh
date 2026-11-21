#!/usr/bin/env bash
# 6000 only: after queue2, the internship adapter on the HARD exam v2.1 public (with tools, then closed book).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
until grep -q QUEUE2_DONE logs/queue2b.log 2>/dev/null; do sleep 60; done
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
A=data/models/intern_v1/final
B=data/bench/mezonbench_v2_1.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --bench $B --out data/bench/v21_intern_tools.jsonl
$PY research/bench_run.py --model "$M" --adapter $A --bench $B --out data/bench/v21_intern_closed.jsonl
echo QUEUE3_DONE
