#!/usr/bin/env bash
# L40S only: N OCR workers (default 6) using the vLLM server on 127.0.0.1:8118, in tmux 'ocr'.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
N=${1:-6}
cd "$HOME/mezon" || exit 1
tmux kill-session -t =ocr 2>/dev/null
tmux new -d -s ocr "export OCR_SERVER=http://127.0.0.1:8118/v1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True; for k in \$(seq 0 $((N-1))); do ~/ocr-venv/bin/python -X utf8 research/ocr_scans.py run \$k/$N > logs/ocr_\$k.log 2>&1 & done; wait"
echo "started $N OCR workers on $(hostname)"
