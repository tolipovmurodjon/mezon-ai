#!/usr/bin/env bash
# L40S only: safety brake for lex.uz pass 2. Every 2 min it counts NEW server errors (5xx/429/timeouts) in the
# pass-2 logs since the previous check (total now minus total before, so old errors never count twice). If more than
# 5 new ones, or the error rows in the state db grew by more than 3, restart the workers slower ($2 s per worker).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
SLOW=${2:-2.0}
errs() { python3 -c "import sqlite3;print(sqlite3.connect('data/raw/lexuz_full/state.sqlite',timeout=60).execute(\"select count(*) from acts where status='error'\").fetchone()[0])"; }
total() { cat logs/lexuz_full_p2_*.log 2>/dev/null | grep -cE "Server error|'429|Too Many|timed out"; }
base=$(errs); prev=$(total)
while true; do
  sleep 120
  now=$(errs); t=$(total); new=$((t - prev)); prev=$t
  echo "$(date -u +%H:%M) errors_db=$now (start $base) new_server_errors_2min=$new"
  if [ "$now" -gt $((base + 3)) ] || [ "$new" -gt 5 ]; then
    echo "$(date -u +%H:%M) BRAKE: lex.uz is struggling, slowing to $SLOW s per worker"
    bash scripts/crawl_p2_restart.sh "$SLOW"
    exit 0
  fi
done
