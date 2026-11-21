#!/usr/bin/env bash
# On the 6000 only: thinking-mode MezonBench on 25 items per family (keeps the 20 already done).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux kill-session -t bench 2>/dev/null; sleep 5
tmux new -d -s bench "$HOME/mezon/.venv-train/bin/python -X utf8 research/bench_run.py --model $HOME/models/Qwen3.8-27B --think --per-family 25 --out data/bench/preds_base_think.jsonl > logs/bench_think.log 2>&1; echo ALL_BENCH_DONE >> logs/bench_think.log"
echo "restarted on $(hostname)"
