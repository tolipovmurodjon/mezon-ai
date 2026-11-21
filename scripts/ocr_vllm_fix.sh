#!/usr/bin/env bash
# L40S only: finish the PaddleOCR-VL vLLM server env (flash-attn against the installed torch, then the plugin).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
set -x
export PATH=$HOME/vllm-venv/bin:$HOME/.local/bin:$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True MAX_JOBS=8
V="$HOME/vllm-venv/bin/python"
"$V" -c "import torch; print('torch', torch.__version__, torch.version.cuda)"
"$V" -m pip install -q packaging ninja wheel
"$V" -m pip install flash-attn --no-build-isolation 2>&1 | tail -3
"$HOME/vllm-venv/bin/paddleocr" install_genai_server_deps vllm 2>&1 | tail -3
"$V" -c "from paddlex.utils.deps import is_genai_engine_plugin_available as a; print('plugin vllm:', a('vllm'))"
echo VLLM_FIX_DONE
