#!/usr/bin/env bash
# L40S only: make sure the OCR server is up (start it if not), then start N workers (default 4). Exact tmux names.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
N=${1:-4}
if ! curl -s -m 5 http://127.0.0.1:8118/v1/models | grep -q PaddleOCR; then
  tmux kill-session -t =ocrsrv 2>/dev/null
  tmux new -d -s ocrsrv "PATH=$HOME/vllm-venv/bin:\$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True paddlex_genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm --host 127.0.0.1 --port 8118 --backend_config $HOME/ocr_vllm_backend.yaml >> $HOME/mezon/logs/ocr_server.log 2>&1"
  for i in $(seq 1 60); do curl -s -m 5 http://127.0.0.1:8118/v1/models | grep -q PaddleOCR && break; sleep 10; done
fi
curl -s -m 5 http://127.0.0.1:8118/v1/models | grep -q PaddleOCR || { echo "server did not come up"; exit 1; }
tmux kill-session -t =ocr 2>/dev/null
tmux new -d -s ocr "export OCR_SERVER=http://127.0.0.1:8118/v1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True; for k in \$(seq 0 $((N-1))); do ~/ocr-venv/bin/python -X utf8 research/ocr_scans.py run \$k/$N > logs/ocr_\$k.log 2>&1 & done; wait"
sleep 5; tmux ls | cut -d: -f1 | tr "\n" " "; echo "| server up, $N workers on $(hostname)"
