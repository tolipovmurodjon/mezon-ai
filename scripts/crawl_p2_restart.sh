#!/usr/bin/env bash
# L40S only: restart the lex.uz crawl as pass 2 only (pass 1 is finished): 25 workers x 1 req/s (project cap),
# national acts first, no printable PDF. Workers stop between documents; a half-done document is simply redone.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
W=${MEZON_WORKERS:-25}; IV=${1:-1.0}
tmux kill-session -t =crawl 2>/dev/null
# only the python workers: a bare "-f research.lexuz_full" pattern also matches the tmux SERVER (it keeps the
# command line of the first session), and killing it kills every session on the box (21.11.2026).
pkill -f "^[^ ]*python[0-9.]* -X utf8 -m research[.]lexuz_full"; sleep 8
pgrep -f "^[^ ]*python[0-9.]* -X utf8 -m research[.]lexuz_full" >/dev/null && { echo "old workers still alive, not starting"; exit 1; }
rm -f data/raw/lexuz_full/*.lock
tmux new -d -s crawl "export PATH=$HOME/.local/bin:\$PATH PYTHONIOENCODING=utf-8 MEZON_PASS=2 MEZON_SKIP_PRINT_PDF=1 MEZON_P2_NATIONAL_FIRST=1; \
  for k in \$(seq 0 $((W-1))); do MEZON_SHARD=\$k/$W MEZON_HTTP_INTERVAL=$IV .venv/bin/python -X utf8 -m research.lexuz_full run >> logs/lexuz_full_p2_\$k.log 2>&1 & done; wait"
sleep 20
echo "pass-2 workers: $(pgrep -f '^[^ ]*python[0-9.]* -X utf8 -m research[.]lexuz_full' | wc -l) on $(hostname)"
