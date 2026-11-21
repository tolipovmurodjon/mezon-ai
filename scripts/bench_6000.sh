#!/usr/bin/env bash
# On the 6000 only: MezonBench closed book, base Qwen then the run-1 adapter (no thinking), then base with thinking.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
P="$HOME/mezon/.venv-train/bin/python -X utf8 research/bench_run.py --model $HOME/models/Qwen3.8-27B"
$P --out data/bench/preds_base.jsonl
$P --adapter data/models/sft/final --out data/bench/preds_sft1.jsonl
$P --think --per-family 25 --out data/bench/preds_base_think.jsonl
echo ALL_BENCH_DONE
