#!/usr/bin/env bash
# Copy Mezon (code, stores, crawl state and every cached lex.uz page) to the AWS box, then start the overnight run
# in tmux there. Pages already cached are never fetched again on the box (the crawler is cache-first).
#   bash scripts/to_box.sh            # copy + start
# Needs: the box running (Boss starts it) and `ssh box` working. Never copies secrets, .venv or the Gemini folder.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST='~/10_projects/mezon'
EXTRA="$(cat data/cache_root.txt 2>/dev/null || true)"

ssh box "mkdir -p $DEST/data/cache"
echo "== code + stores + crawl state"
tar --exclude=.venv --exclude=gemini --exclude='*.pyc' --exclude=__pycache__ --exclude='data/cache' \
    --exclude='.env' --exclude='*secret*' --exclude='*token*' --exclude='*credential*' --exclude='*password*' \
    -czf - . | ssh box "tar -xzf - -C $DEST"
echo "== cached pages on D:"
tar -C data/cache -czf - . | ssh box "tar -xzf - -C $DEST/data/cache"
if [ -n "$EXTRA" ] && [ -d "$EXTRA" ]; then
  echo "== cached pages in the extra cache ($EXTRA)"
  tar -C "$EXTRA" -czf - . | ssh box "tar -xzf - -C $DEST/data/cache"
fi
echo "== LexUZ oflayn package (4.7 GB, official link from lex.uz/uz/offline) in tmux 'offline'"
ssh box "cd $DEST && mkdir -p logs && tmux new -d -s offline 'bash scripts/lexuz_offline_box.sh > logs/offline.log 2>&1'"
echo "== start (uv, then the overnight script in tmux 'mezon')"
ssh box "cd $DEST && rm -f data/cache_root.txt data/raw/lexuz_full/STOP && (command -v uv >/dev/null || [ -x ~/.local/bin/uv ] || python3 -m pip install --user -q uv)   && PATH=\$HOME/.local/bin:\$PATH uv sync -q && tmux new -d -s mezon 'PATH=\$HOME/.local/bin:\$PATH bash scripts/overnight.sh' && tmux ls"
echo "done: watch with  ssh box 'tail -f ~/10_projects/mezon/logs/overnight.log'"
