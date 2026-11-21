#!/usr/bin/env bash
# Ohio GPU (mezon-ohio1) only: pull the base model + training venv from R2, unpack the repo, check the GPU stack.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
set -e
mkdir -p ~/models/Qwen3.8-27B ~/mezon
rclone copy --transfers 16 --multi-thread-streams 8 r2:mezon-data/mezon/base/Qwen3.8-27B/ ~/models/Qwen3.8-27B/
rclone copy r2:mezon-data/mezon/env/venv-train.tar /tmp/
tar -C ~/mezon -xf /tmp/venv-train.tar && rm -f /tmp/venv-train.tar
tar -C ~/mezon -xzf ~/repo.tgz
du -sh ~/models/Qwen3.8-27B ~/mezon/.venv-train
~/mezon/.venv-train/bin/python -c "import torch,transformers,peft; print(torch.__version__, transformers.__version__, peft.__version__, torch.cuda.get_device_name(0))"
echo OHIO_SETUP_DONE
