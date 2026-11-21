#!/usr/bin/env bash
# L40S only: the PaddleOCR-VL vLLM server environment (~/vllm-venv), separate from ~/ocr-venv.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
set -x
export PATH=$HOME/vllm-venv/bin:$HOME/.local/bin:$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
V="$HOME/vllm-venv/bin/python"
uv pip install -q --python "$V" pip
"$V" -m pip install -q -U "paddleocr[doc-parser]>=3.6.0" python-docx
"$HOME/vllm-venv/bin/paddleocr" install_genai_server_deps vllm
"$V" -c "import vllm; print('vllm-venv ok', vllm.__version__)"
echo VLLM_ENV_DONE
