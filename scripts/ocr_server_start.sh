#!/usr/bin/env bash
# L40S only: start the PaddleOCR-VL-1.6 vLLM server on 127.0.0.1:8118 (tmux ocrsrv), ~60 % of the GPU.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
export PATH=$HOME/vllm-venv/bin:$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
cat > "$HOME/ocr_vllm_backend.yaml" <<'YAML'
gpu-memory-utilization: 0.6
max-num-seqs: 64
YAML
tmux kill-session -t =ocr 2>/dev/null; sleep 3
pkill -f "[r]esearch/ocr_scans.py run" ; sleep 3
tmux new -d -s ocrsrv "PATH=$HOME/vllm-venv/bin:\$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True paddlex_genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm --host 127.0.0.1 --port 8118 --backend_config $HOME/ocr_vllm_backend.yaml > $HOME/mezon/logs/ocr_server.log 2>&1"
echo "server starting on $(hostname)"
