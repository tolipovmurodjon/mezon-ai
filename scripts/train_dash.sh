#!/usr/bin/env bash
# Live terminal dashboard for the Mezon-LM GPU box: GPU bars, running jobs, training steps, held-out loss, exam files.
cd "$HOME/mezon" || exit 1
bar() { local v=$1 max=$2 w=40 n; n=$(( v * w / (max>0?max:1) )); printf '%s%s' "$(printf '#%.0s' $(seq 1 $n) 2>/dev/null)" "$(printf '.%.0s' $(seq 1 $((w-n))) 2>/dev/null)"; }
while true; do
  clear
  echo "MEZON-LM TRAINING  ·  $(hostname)  ·  $(date '+%H:%M:%S') UTC   (Ctrl+C to quit)"
  echo "================================================================================"
  IFS=, read -r util mem tot temp pw <<<"$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits | tr -d ' ')"
  printf "GPU busy   [%s] %3s %%\n" "$(bar ${util:-0} 100)" "$util"
  printf "GPU memory [%s] %s / %s GB\n" "$(bar ${mem:-0} ${tot:-1})" "$((mem/1024))" "$((tot/1024))"
  printf "temp %s C · power %s W\n\n" "$temp" "${pw%.*}"
  echo "JOBS RUNNING (tmux): $(tmux ls 2>/dev/null | cut -d: -f1 | tr '\n' ' ')"
  echo
  for f in logs/chain2.log logs/chain.log; do
    [ -f "$f" ] || continue
    echo "--- $f"
    tr '\r' '\n' < "$f" | grep -E "^step [0-9]+/" | tail -1 | cut -c1-100
    tr '\r' '\n' < "$f" | grep -E "held-out loss" | tail -3 | sed "s/held-out loss/  error on unseen/" | cut -c1-110
    tr '\r' '\n' < "$f" | grep -E "done,|_DONE" | tail -2 | cut -c1-100
  done
  echo
  echo "EXAM ANSWER FILES (lines = questions answered):"
  for p in data/bench/v21_*20.jsonl; do [ -f "$p" ] && printf "  %-40s %4s\n" "$(basename $p)" "$(wc -l < $p)"; done
  echo
  echo "Legend: 'error on unseen' = loss on lessons the model never trained on (lower = learned)."
  sleep 5
done
