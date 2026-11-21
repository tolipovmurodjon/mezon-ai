#!/usr/bin/env bash
# 6000 only: law-school pilot v1.1 (balanced true/false + in-force-on-date lessons). Same recipe as v1 (rank 128,
# lr 1e-4, ~6M law tokens + replay), own data and output paths. Then MezonBench closed book with the adapter.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
rclone copy r2:mezon-data/mezon/train/ data/train/ --include "mix_v11*.jsonl"
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
$PY -m research.train_cpt --model "$HOME/models/Qwen3.8-27B" --data data/train/mix_v11.jsonl \
    --val data/train/mix_v11_val.jsonl --out data/models/cpt_v11 || exit 1
step=$(python3 -c "import json;print(json.load(open('data/models/cpt_v11/final/state.json'))['step'])")
rclone copy data/models/cpt_v11/final "r2:mezon-data/mezon/models/cpt_v11/final-step$step" --ignore-existing
$PY research/bench_run.py --model "$HOME/models/Qwen3.8-27B" --adapter data/models/cpt_v11/final --out data/bench/preds_cpt_v11.jsonl
echo V11_ALL_DONE
