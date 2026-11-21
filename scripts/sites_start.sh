#!/usr/bin/env bash
# L40S only: one polite crawler per public site, each 1 req/s, each in its own tmux session (site_<name>).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
for s in govuz mygovuz ombudsman statsud eqaror_resp; do
  tmux has-session -t "=site_$s" 2>/dev/null || tmux new -d -s "site_$s" "nice -n 10 .venv/bin/python -X utf8 -m research.site_crawl $s 1.0 >> logs/site_$s.log 2>&1"
done
sleep 60
for s in govuz mygovuz ombudsman statsud eqaror_resp; do echo "$s: $(wc -l < data/raw/sites/$s/index.jsonl 2>/dev/null) urls | $(tail -c 150 logs/site_$s.log 2>/dev/null | tr '\n' ' ')"; done
echo "sessions: $(tmux ls | cut -d: -f1 | tr '\n' ' ')"
