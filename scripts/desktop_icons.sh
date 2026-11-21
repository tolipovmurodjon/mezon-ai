#!/usr/bin/env bash
# Desktop icons on the GPU box's XFCE desktop: dashboard, GPU, data, code, logs, exams.
[ "$(uname -s)" = Linux ] || exit 1
until grep -q DESKTOP_READY ~/mezon/logs/desktop.log 2>/dev/null; do sleep 10; done
D=~/Desktop; mkdir -p $D
mk() { printf '[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nIcon=%s\nTerminal=false\n' "$1" "$2" "$3" > "$D/$4.desktop"; chmod +x "$D/$4.desktop"; gio set "$D/$4.desktop" metadata::trusted true 2>/dev/null || true; }
T="xfce4-terminal --geometry=150x45"
mk "1 Training dashboard" "$T --title=Training -x bash $HOME/mezon/scripts/train_dash.sh" utilities-system-monitor dash
mk "2 GPU live" "$T --title=GPU -x watch -n 2 nvidia-smi" video-display gpu
mk "3 Training log live" "$T --title=Log -x bash -c 'tail -f ~/mezon/logs/chain2.log ~/mezon/logs/chain.log'" text-x-generic log
mk "4 Data folders" "thunar $HOME/mezon/data" folder data
mk "5 Code (terminal in repo)" "$T --title=Code --working-directory=$HOME/mezon" utilities-terminal code
mk "6 Exam answers" "$T --title=Exams -x bash -c 'cd ~/mezon/data/bench; wc -l v21_*.jsonl v3_*.jsonl 2>/dev/null; exec bash'" accessories-text-editor exams
mk "7 Jobs (tmux list)" "$T --title=Jobs -x bash -c 'tmux ls; exec bash'" system-run jobs
echo ICONS_READY
