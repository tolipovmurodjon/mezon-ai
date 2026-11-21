#!/bin/bash
# Law school v2: build the extra replay pool (needs pyarrow: repo .venv), then assemble one round of shards (needs tokenizers: retr-venv).
# usage: bash scripts/lsv2_assemble.sh [budget_tokens]     (CPU only, no GPU)
[ "$(uname)" = "Linux" ] || { echo "run on the L40S"; exit 1; }
set -e
cd ~/mezon
BUDGET="${1:-50000000}"
mkdir -p logs
if [ ! -f data/train/lawschool_v2/replay_extra.jsonl.gz ]; then
  .venv/bin/python -X utf8 -m research.law_school_v2 replay-extra
fi
~/retr-venv/bin/python -X utf8 -m research.law_school_v2 assemble --budget "$BUDGET"
echo LSV2_DONE
