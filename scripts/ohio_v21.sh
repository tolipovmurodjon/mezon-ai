#!/usr/bin/env bash
# Ohio (mezon-ohio1): base Qwen3.8-27B on MezonBench v2.1 public, closed book then with tools.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
B=data/bench/mezonbench_v2_1.jsonl
$PY research/bench_run.py --model "$M" --bench $B --out data/bench/v21_base_closed.jsonl
$PY research/bench_tools_run.py --model "$M" --bench $B --out data/bench/v21_base_tools.jsonl
echo OHIO_V21_DONE
