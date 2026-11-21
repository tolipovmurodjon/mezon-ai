#!/usr/bin/env bash
cd D:/10_projects/mezon || exit 1
until grep -q OPUS_V21_DONE logs/frontier_opus_v21.log 2>/dev/null; do sleep 60; done
.venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode tools --bench data/bench/mezonbench_v3.jsonl --out data/bench/frontier/opus55_v3_tools.jsonl
echo OPUS_V3_DONE
