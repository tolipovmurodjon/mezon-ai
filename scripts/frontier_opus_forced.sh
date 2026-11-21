#!/usr/bin/env bash
# Laptop: after the first Opus queue, the FORCED closed-book run (no "noaniq" allowed) on the same balanced 120.
cd D:/10_projects/mezon || exit 1
until grep -q OPUS_ALL_DONE logs/frontier_opus.log 2>/dev/null; do sleep 60; done
.venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode forced --per-family 30 --out data/bench/frontier/opus55_forced30.jsonl
echo OPUS_FORCED_DONE
