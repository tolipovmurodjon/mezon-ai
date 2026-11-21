#!/usr/bin/env bash
# L40S only (21.11 ~02:25): crawl 25 -> 30 req/s with a brake back to 25; OCR 4 -> 8 workers; pdftotext for all
# text PDFs (3 low-priority processes). Exact tmux names; check every session after.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux kill-session -t =watchdog 2>/dev/null
bash scripts/crawl_p2_restart.sh 0.833
tmux new -d -s watchdog "bash scripts/crawl_watchdog.sh x 1.0 >> logs/crawl_watchdog.log 2>&1"
bash scripts/ocr_go.sh 8
tmux has-session -t =pdftext 2>/dev/null || tmux new -d -s pdftext "for k in 0 1 2; do nice -n 15 .venv/bin/python -X utf8 -m research.pdf_text_all \$k/3 >> logs/pdftext_\$k.log 2>&1 & done; wait"
sleep 5
echo "sessions: $(tmux ls | cut -d: -f1 | tr '\n' ' ')"
echo "crawl interval: $(tr '\0' '\n' < /proc/$(pgrep -f '^[^ ]*python[0-9.]* -X utf8 -m research[.]lexuz_full' | head -1)/environ | grep MEZON_HTTP)"
echo "ocr workers: $(pgrep -f '[r]esearch/ocr_scans.py run' | wc -l) | pdftext workers: $(pgrep -f '[r]esearch[.]pdf_text_all' | wc -l)"
