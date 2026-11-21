#!/usr/bin/env bash
# Ohio: wait for the chain_v1 adapter in R2, pull it, restart the API so mezon-lm is served.
[ "$(uname -s)" = Linux ] || exit 1
D=~/mezon/data/models/chain_v1/final; mkdir -p $D
until rclone lsf r2:mezon-data/mezon/models/chain_v1/ 2>/dev/null | grep -q UPLOAD_DONE; do sleep 30; done

rm -f $D/adapter_model.safetensors
rclone copy --transfers 8 --exclude optimizer.pt r2:mezon-data/mezon/models/chain_v1/final $D && echo PULL_DONE
tmux kill-session -t =serve 2>/dev/null
tmux new -d -s serve "cd ~/mezon && .venv-train/bin/python -m research.serve_api 2>&1 | tee serve.log"
echo SERVE_RESTARTED
