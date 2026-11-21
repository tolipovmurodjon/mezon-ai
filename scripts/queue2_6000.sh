#!/usr/bin/env bash
# 6000 only. Waits for the "where" exam, then: Qwen closed book and FORCED closed book on the balanced 120
# (paired with Opus), then the internship SFT (793 rows, base model, one pass), then its exam with tools.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
until grep -q WHERE_ALL_DONE logs/tools_bench2.log 2>/dev/null; do sleep 60; done
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
$PY research/bench_run.py --model "$M" --per-family 30 --out data/bench/preds_base_closed30.jsonl
$PY research/bench_run.py --model "$M" --per-family 30 --force --out data/bench/preds_base_forced30.jsonl
echo CLOSED_DONE
$PY research/train_cpt.py --model "$M" --data data/train/internship_sft.jsonl --val data/train/internship_val.jsonl \
    --max-len 3072 --rank 64 --lr 1e-4 --accum 16 --out data/models/intern_v1
echo INTERN_TRAIN_DONE
A=data/models/intern_v1/final
$PY research/bench_tools_run.py --model "$M" --adapter $A --per-family 30 --out data/bench/preds_intern_tools30.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --bench data/bench/mezonbench_where_v1.jsonl --out data/bench/where_intern_tools.jsonl
$PY research/bench_run.py --model "$M" --adapter $A --per-family 30 --force --out data/bench/preds_intern_forced30.jsonl
echo QUEUE2_DONE
