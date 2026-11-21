#!/usr/bin/env bash
# L40S only: regulation.gov.uz full download, 4 workers in tmux 'regul' (exact-name checks only).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux has-session -t =regul 2>/dev/null && { echo "already running"; exit 0; }
tmux new -d -s regul "export PYTHONIOENCODING=utf-8; for k in 0 1 2 3; do MEZON_SHARD=\$k/4 MEZON_HTTP_INTERVAL=1.2 nice -n 10 .venv/bin/python -X utf8 -m research.regulation_full --max 118400 >> logs/regulation_\$k.log 2>&1 & done; wait"
sleep 30; tail -qn2 logs/regulation_[0-3].log | cut -c1-160; ls data/cache/regulation | wc -l; echo "on $(hostname)"
