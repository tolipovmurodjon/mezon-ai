#!/usr/bin/env bash
# 6000: chain v2 = law school (cpt_v11) + internship v2 (1,132 rows, the skills Qwen slipped on), then v2.1 exams.
[ "$(uname -s)" = Linux ] || exit 1
cd "$HOME/mezon" || exit 1
until grep -q CHAIN_DONE logs/chain.log 2>/dev/null; do sleep 60; done
PY="$HOME/mezon/.venv-train/bin/python -X utf8"; M="$HOME/models/Qwen3.8-27B"; B=data/bench/mezonbench_v2_1.jsonl
$PY research/train_cpt.py --model "$M" --init-adapter data/models/cpt_v11/final --data data/train/internship_v2.jsonl \
  --val data/train/internship_v2_val.jsonl --out data/models/chain_v2 --lr 1e-4 --save-every-min 15 && echo CHAIN2_TRAIN_DONE
A=data/models/chain_v2/final
$PY research/bench_run.py --model "$M" --adapter $A --bench $B --per-family 20 --out data/bench/v21_chain2_closed20.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --bench $B --per-family 20 --out data/bench/v21_chain2_tools20.jsonl
echo CHAIN2_DONE
