#!/usr/bin/env bash
# L40S only. Two environments so the fast OCR server and PaddlePaddle do not fight over CUDA libraries:
#   ~/vllm-venv : the PaddleOCR-VL vLLM server only (no paddlepaddle inside)
#   ~/ocr-venv  : the paddleocr client, with the CUDA libraries paddlepaddle-gpu 3.2.1 pins restored
# Guard: refuses to run anywhere but Linux (a Windows laptop must never run this).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
set -x
export PATH=$HOME/.local/bin:$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
uv venv -q --python 3.12 "$HOME/vllm-venv"
"$HOME/vllm-venv/bin/python" -m ensurepip -q || true
"$HOME/vllm-venv/bin/python" -m pip install -q -U "paddleocr[doc-parser]>=3.6.0" python-docx
"$HOME/vllm-venv/bin/paddleocr" install_genai_server_deps vllm
"$HOME/vllm-venv/bin/python" -c "import vllm; print('vllm-venv ok', vllm.__version__)"
O="$HOME/ocr-venv/bin/python"
"$O" -m pip uninstall -y -q vllm
"$O" -m pip install -q --force-reinstall --no-deps paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
"$O" -m pip install -q "nvidia-cublas-cu12==12.6.4.1" "nvidia-cuda-cupti-cu12==12.6.80" "nvidia-cuda-nvrtc-cu12==12.6.77" \
  "nvidia-cuda-runtime-cu12==12.6.77" "nvidia-cudnn-cu12==9.5.1.17" "nvidia-cufft-cu12==11.3.0.4" "nvidia-cufile-cu12==1.11.1.6"
"$O" -m pip check 2>&1 | grep -i paddle | head -5
"$O" -c "import paddle; paddle.utils.run_check()" 2>&1 | tail -1
echo SPLIT_SETUP_DONE
