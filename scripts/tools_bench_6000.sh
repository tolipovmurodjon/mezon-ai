#!/usr/bin/env bash
# 6000 only: after pilot v1.1 finishes (V11_ALL_DONE), MezonBench WITH tools: base, then v1.1 adapter.
# 30 items per family (120 each). Answers "is training worth it over base + tools?".
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
until grep -q V11_ALL_DONE logs/cpt_v11.log; do sleep 60; done
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
$PY research/bench_tools_run.py --model "$HOME/models/Qwen3.8-27B" --per-family 30 --out data/bench/preds_base_tools30.jsonl
$PY research/bench_tools_run.py --model "$HOME/models/Qwen3.8-27B" --adapter data/models/cpt_v11/final --per-family 30 \
    --out data/bench/preds_v11_tools30.jsonl
echo TOOLS_ALL_DONE
