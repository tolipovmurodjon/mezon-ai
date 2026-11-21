#!/usr/bin/env bash
# L40S only: lex.uz pass 2 at 35 req/s (25 workers x 0.714 s), brake back to 30 req/s (0.833 s) on new errors.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux kill-session -t =watchdog 2>/dev/null
bash scripts/crawl_p2_restart.sh 0.714
tmux new -d -s watchdog "bash scripts/crawl_watchdog.sh x 0.833 >> logs/crawl_watchdog.log 2>&1"
sleep 3
echo "interval: $(tr '\0' '\n' < /proc/$(pgrep -f '^[^ ]*python[0-9.]* -X utf8 -m research[.]lexuz_full' | head -1)/environ | grep MEZON_HTTP) | sessions: $(tmux ls | cut -d: -f1 | tr '\n' ' ')"
