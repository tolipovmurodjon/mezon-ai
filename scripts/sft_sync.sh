#!/usr/bin/env bash
# On the 6000 (spot): copy each new SFT checkpoint off the machine to R2, add-only, under its own step name, every 10 min.
# Never overwrites or deletes anything in R2. Run in tmux 'sftsync'.
cd "$HOME/mezon" || exit 1
while true; do
  for d in data/models/sft/latest data/models/sft/final; do
    [ -f "$d/state.json" ] || continue
    step=$(python3 -c "import json;print(json.load(open('$d/state.json'))['step'])")
    rclone copy "$d" "r2:mezon-data/mezon/models/sft/$(basename $d)-step$step" --ignore-existing --log-level ERROR \
      && echo "$(date -u '+%F %T') synced $(basename $d) step $step"
  done
  sleep 600
done
