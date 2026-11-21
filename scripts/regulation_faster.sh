#!/usr/bin/env bash
# L40S only: regulation.gov.uz 4 -> 10 workers (1.2 s each = ~8 req/s), resumable (already-fetched ids are kept).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux kill-session -t =regul 2>/dev/null
pkill -f "^[^ ]*python[0-9.]* -X utf8 -m research[.]regulation_full"; sleep 5
N=10
# re-shard: each new shard skips ids already present in ANY drafts_*.jsonl (merged into one done list)
cat data/raw/regulation/drafts_*.jsonl > data/raw/regulation/_done_before_reshard.jsonl
tmux new -d -s regul "export PYTHONIOENCODING=utf-8; for k in \$(seq 0 $((N-1))); do MEZON_SHARD=\$k/$N MEZON_HTTP_INTERVAL=1.2 nice -n 10 .venv/bin/python -X utf8 -m research.regulation_full --max 118400 >> logs/regulation10_\$k.log 2>&1 & done; wait"
sleep 20; echo "regulation workers: $(pgrep -f "^[^ ]*python[0-9.]* -X utf8 -m research[.]regulation_full" | wc -l) | sessions: $(tmux ls | cut -d: -f1 | tr "\n" " ")"
