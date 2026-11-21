#!/usr/bin/env bash
# Laptop: Opus 5.5 via Claude Code CLI on the frozen exam (balanced 30/family + where 60), tools and closed book.
cd D:/10_projects/mezon || exit 1
PY=".venv/Scripts/python.exe -X utf8 -m research.frontier_cli"
F=data/bench/frontier
W=data/bench/mezonbench_where_v1.jsonl
$PY --mode tools  --per-family 30 --out $F/opus55_tools30.jsonl
$PY --mode closed --per-family 30 --out $F/opus55_closed30.jsonl
$PY --mode tools  --bench $W --out $F/opus55_where_tools.jsonl
$PY --mode closed --bench $W --out $F/opus55_where_closed.jsonl
echo OPUS_ALL_DONE
