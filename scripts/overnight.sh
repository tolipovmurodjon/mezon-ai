#!/usr/bin/env bash
# Mezon overnight data run on the AWS box. Start inside tmux:  tmux new -s mezon 'bash scripts/overnight.sh'
# One crawler at a time, ~1 request/s to lex.uz (research/polite_http.py spacing), resumable: rerun to continue.
# Never touches public.sud.uz, E-qaror bulk, or any cloud AI. Every count in the summary comes from the files/DBs.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
LOG=logs/overnight.log
export MEZON_FULL_HISTORY=1 PYTHONIOENCODING=utf-8
PY="uv run python -X utf8"
export PATH="$HOME/.local/bin:$PATH"
step() { echo "=== $(date '+%F %T') $*" | tee -a "$LOG"; "$@" >>"$LOG" 2>&1 || echo "!!! FAILED: $*" | tee -a "$LOG"; }

step $PY -m research.hf_corpus                                   # 1. open licensed corpora (HF, not lex.uz)
step $PY -m mezon.lawstore.build taxcode                         # 2. P1: every Tax Code edition (the 2020-2025 gap)
for k in $($PY -c "from mezon.lawstore.build import CORE; print(' '.join(c[0] for c in CORE if c[0]!='taxcode'))"); do
  step $PY -m mezon.lawstore.build "$k"                          #    then every edition of every other core act
done
step $PY -m mezon.lawstore.changelog                             # 3. change log from all editions
step $PY -m research.freshness --region 4                        # 4. P2: re-read flagged decisions, region 4 first
step $PY -m research.freshness
step $PY -m mezon.sync.lexuz_local                               # 5. P3: local decisions citing the LSP (respondents)
step $PY -m mezon.sync.lexuz_local --followups
[ -n "${MODEL_DIR:-}" ] && step $PY -m research.qwen_format "$MODEL_DIR"   # 6. read Qwen's real format files
step $PY -m research.overnight_summary                           # 7. exact counts -> logs/overnight_summary.md
# 8. Then the whole of lex.uz: runs for days; the summary above is ready by morning, rerun it any time.
step $PY -m research.lexuz_full seed                            #    the whole of lex.uz (resumable, ~1.2 s per request)
step $PY -m research.lexuz_full run
step $PY -m research.overnight_summary
echo "=== done $(date '+%F %T')" | tee -a "$LOG"
