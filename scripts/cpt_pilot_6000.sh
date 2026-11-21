#!/usr/bin/env bash
# 6000 only: law-school pilot. Pull the mix from R2, train (research/train_cpt.py), copy the adapter to R2, then
# MezonBench closed book (no thinking) with the adapter. Resumable: rerun after a spot stop continues from latest.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
rclone copy r2:mezon-data/mezon/train/ data/train/ --include "mix_pilot*.jsonl"
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
$PY -m research.train_cpt --model "$HOME/models/Qwen3.8-27B" || exit 1
step=$(python3 -c "import json;print(json.load(open('data/models/cpt_pilot/final/state.json'))['step'])")
rclone copy data/models/cpt_pilot/final "r2:mezon-data/mezon/models/cpt_pilot/final-step$step" --ignore-existing
$PY research/bench_run.py --model "$HOME/models/Qwen3.8-27B" --adapter data/models/cpt_pilot/final --out data/bench/preds_cpt_pilot.jsonl
echo PILOT_ALL_DONE
