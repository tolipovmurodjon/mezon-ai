#!/usr/bin/env bash
# 6000 only: strict-judge pilot, round 1 (expert iteration with tools). NOT run yet; the GPU is busy with exams.
#   bash scripts/judge_round_6000.sh [ADAPTER_DIR]     # policy adapter to sample from; empty = base model + tools
# 1 build questions (CPU) -> 2 sample k=8 with the tool loop -> 3 select (rejection sampling) -> 4 train_cpt on the
# selected rows -> 5 MezonBench with tools (30 per family) + where bench with tools. Resumable: sampling continues
# where it stopped; training uses train_cpt's own resume.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
PY="$HOME/mezon/.venv-train/bin/python -X utf8"
M="$HOME/models/Qwen3.8-27B"
ADAPTER="${1:-}"
AD=""
[ -n "$ADAPTER" ] && AD="--adapter $ADAPTER"
Q=data/train/judge_q_r1.jsonl
T=data/train/judge_traj_r1.jsonl
S=data/train/judge_sft_r1.jsonl
OUT=data/models/judge_r1

[ -s "$Q" ] || $PY -m research.judge_questions build || exit 1
$PY -m research.judge_sample --model "$M" $AD --questions "$Q" --out "$T" --k 8 --batch 16 || exit 1
$PY -m research.judge_select --traj "$T" --out "$S" || exit 1
[ -s "$S" ] || { echo "no selected rows"; exit 1; }
NV=$(( $(wc -l < "$S") / 20 ))   # last 5 % (shuffled) as held-out slice for train_cpt's val loss
head -n -"$NV" "$S" > data/train/judge_sft_r1_train.jsonl
tail -n "$NV" "$S" > data/train/judge_sft_r1_val.jsonl
$PY -m research.train_cpt --model "$M" --data data/train/judge_sft_r1_train.jsonl --val data/train/judge_sft_r1_val.jsonl     --out "$OUT" || exit 1

NEW="$OUT/final"
$PY research/bench_tools_run.py --model "$M" --adapter "$NEW" --per-family 30 --out data/bench/preds_judge_r1_tools30.jsonl || exit 1
$PY -m research.mezonbench score data/bench/preds_judge_r1_tools30.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter "$NEW" --bench data/bench/mezonbench_where_v1.jsonl \
    --out data/bench/preds_judge_r1_where.jsonl || exit 1
$PY -m research.mezonbench_where score data/bench/preds_judge_r1_where.jsonl
echo JUDGE_R1_DONE
