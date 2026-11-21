#!/usr/bin/env bash
# 6000 only: put the base model and the training venv in R2 (add-only, new paths) so the Ohio GPUs can start fast.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
set -e
cd "$HOME"
tar -C "$HOME/mezon" -cf /tmp/venv-train.tar .venv-train
rclone copy --ignore-existing --transfers 8 /tmp/venv-train.tar r2:mezon-data/mezon/env/
rclone copy --ignore-existing --transfers 16 --s3-upload-concurrency 8 "$HOME/models/Qwen3.8-27B" r2:mezon-data/mezon/base/Qwen3.8-27B/
rm -f /tmp/venv-train.tar
rclone size r2:mezon-data/mezon/base/Qwen3.8-27B/
echo R2_UP_DONE
