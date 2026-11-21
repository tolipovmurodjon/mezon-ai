#!/usr/bin/env bash
# Mezon data -> Cloudflare R2 bucket mezon-data (Boss, 20.11.2026). Runs on the L40S (~/mezon), nightly by cron.
# ADD-ONLY: --ignore-existing never overwrites, nothing is ever deleted or moved (R2 rule). The crawl state changes,
# so it goes up as a new dated snapshot each run instead of overwriting. Log: logs/r2_sync.log.
set -u
cd "$HOME/mezon"
exec 9>/tmp/mezon_r2.lock; flock -n 9 || { echo "already running"; exit 0; }
B=r2:mezon-data/mezon
OPT=(--ignore-existing --transfers 32 --checkers 32 --log-level NOTICE --stats 10m --stats-one-line)
echo "=== $(date -u '+%F %T') start"
for d in data/cache/lexuz data/cache/sud data/raw/sud data/raw/hf data/raw/lexuz_offline data/interim; do
  [ -d "$d" ] && rclone copy "$d" "$B/$d" "${OPT[@]}" && echo "ok $d"
done
snap="/tmp/state-$(date -u +%Y%m%d-%H%M).sqlite"
python3 -c "import sqlite3,sys; s=sqlite3.connect('data/raw/lexuz_full/state.sqlite', timeout=60); d=sqlite3.connect(sys.argv[1]); s.backup(d)" "$snap" \
  && rclone copy "$snap" "$B/state/" "${OPT[@]}" && echo "ok state snapshot $(basename "$snap")"; rm -f "$snap"
echo "=== $(date -u '+%F %T') done; bucket total: $(rclone size "$B" --json 2>/dev/null)"
