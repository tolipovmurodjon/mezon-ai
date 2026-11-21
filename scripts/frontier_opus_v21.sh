#!/usr/bin/env bash
# Laptop: Opus 5.5 on MezonBench v2.1 public (324 items), with tools and closed book. Boss's yes 21 Nov 11:20:
# public lex.uz decision texts may go to Opus for this benchmark (no personal data in the quoted preambles).
cd D:/10_projects/mezon || exit 1
B=data/bench/mezonbench_v2_1.jsonl
.venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode tools  --bench $B --out data/bench/frontier/opus55_v21_tools.jsonl
.venv/Scripts/python.exe -X utf8 -m research.frontier_cli --mode closed --bench $B --out data/bench/frontier/opus55_v21_closed.jsonl
echo OPUS_V21_DONE
