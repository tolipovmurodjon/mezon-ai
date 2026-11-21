#!/usr/bin/env bash
# 6000 only: tools exam v2 (balanced 30 per family, forced final answer). Base + tools, v1.1 + tools, then the
# "where" family (base closed book, base + tools, v1.1 + tools).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
A=data/models/cpt_v11/final
$PY research/bench_tools_run.py --model "$M" --per-family 30 --out data/bench/preds_base_tools30b.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --per-family 30 --out data/bench/preds_v11_tools30b.jsonl
echo TOOLS2_DONE
W=data/bench/mezonbench_where_v1.jsonl
$PY research/bench_run.py --model "$M" --bench $W --out data/bench/where_base.jsonl
$PY research/bench_tools_run.py --model "$M" --bench $W --out data/bench/where_base_tools.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --bench $W --out data/bench/where_v11_tools.jsonl
echo WHERE_ALL_DONE
