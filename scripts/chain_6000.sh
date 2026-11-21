#!/usr/bin/env bash
# 6000: the proper chain. Law school adapter (cpt_v11) keeps training on internship data, then the hard exam v2.1.
[ "$(uname -s)" = Linux ] || { echo "not Linux"; exit 1; }
cd "$HOME/mezon" || exit 1
PY="$HOME/mezon/.venv-train/bin/python -X utf8"; M="$HOME/models/Qwen3.8-27B"; B=data/bench/mezonbench_v2_1.jsonl
D=data/train/internship_sft.jsonl; [ -f data/train/internship_v2.jsonl ] && D=data/train/internship_v2.jsonl
echo "chain data: $D"
$PY research/train_cpt.py --model "$M" --init-adapter data/models/cpt_v11/final --data $D \
  --val data/train/internship_val.jsonl --out data/models/chain_v1 --lr 1e-4 --save-every-min 15 && echo CHAIN_TRAIN_DONE
A=data/models/chain_v1/final
$PY research/bench_run.py --model "$M" --adapter $A --bench $B --per-family 20 --out data/bench/v21_chain_closed20.jsonl
$PY research/bench_run.py --model "$M" --bench $B --per-family 20 --out data/bench/v21_base_closed20.jsonl
$PY research/bench_run.py --model "$M" --adapter data/models/cpt_v11/final --bench $B --per-family 20 --out data/bench/v21_law_closed20.jsonl
$PY research/bench_tools_run.py --model "$M" --adapter $A --bench $B --per-family 20 --out data/bench/v21_chain_tools20.jsonl
echo CHAIN_DONE
