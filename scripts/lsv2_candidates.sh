#!/bin/bash
# Law school v2: candidates for refinery batches finished since the last run (add-only, niced; CPU only, no GPU).
[ "$(uname)" = "Linux" ] || { echo "run on the L40S"; exit 1; }
cd ~/mezon
nice -n 19 .venv/bin/python -X utf8 -m research.law_school_v2 candidates
echo LSV2C_DONE
