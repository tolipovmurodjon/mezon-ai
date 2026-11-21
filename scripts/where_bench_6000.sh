#!/usr/bin/env bash
# 6000 only: after the tools exam (TOOLS_ALL_DONE), the "where" family (60 items, unseen half): base closed book,
# base + tools, v1.1 + tools. Grade on the laptop: python -m research.mezonbench_where score <file>.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
until grep -q TOOLS_ALL_DONE logs/tools_bench.log; do sleep 60; done
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
B=data/bench/mezonbench_where_v1.jsonl
$PY research/bench_run.py --model "$M" --bench $B --out data/bench/where_base.jsonl
$PY research/bench_tools_run.py --model "$M" --bench $B --out data/bench/where_base_tools.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter data/models/cpt_v11/final --bench $B --out data/bench/where_v11_tools.jsonl
echo WHERE_ALL_DONE
