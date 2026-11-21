"""Every threshold and path in one place (design section 2: config.yaml; plain Python so there is no extra dependency)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("REFINERY_CACHE", ROOT / "data" / "cache" / "lexuz"))
OCR_DIR = Path(os.environ.get("REFINERY_OCR", ROOT / "data" / "ocr"))
DOCTEXT_DIR = Path(os.environ.get("REFINERY_DOCTEXT", ROOT / "data" / "doctext"))
STATE_DB = Path(os.environ.get("REFINERY_STATE", ROOT / "data" / "raw" / "lexuz_full" / "state.sqlite"))
OUT = Path(os.environ.get("REFINERY_OUT", ROOT / "data" / "refinery"))
BENCH = ROOT / "data" / "bench" / "mezonbench_v1.jsonl"
CORE_ACTS = ROOT / "data" / "knowledge" / "core_acts.csv"

# Boss's decision 4 (21 Nov 2026): editions and decisions dated on or after this day stay out of training.
TIME_CUT = "2026-10-01"
SEED = 20261121

MIN_CHARS = 150  # drop below this
STUB_CHARS = 400  # 150-400 = stub, kept at tier C
MAX_DOC_CHARS = 400_000
MAX_CHUNK_WORDS = 1000  # about 4,096 tokens at 4.03 tokens per word
SCRIPT_PURITY = 0.95
MIXED_WORD_MAX = 0.005
REPEAT_LINES_MAX = 0.30
REPEAT_5GRAM_MAX = 0.15
OOV_MAX = 0.12
OCR_GOOD_PAGES = 0.90
SCAN_CHARS = 200  # fewer characters on pages 1-3 = scanned PDF
TABLE_NUMERIC = 0.70
TABLE_BIG = 20_000

TWIN_YES = 0.90
TWIN_NO = 0.60
MINHASH_PERM = 112  # 14 bands x 8 rows (FineWeb)
MINHASH_BANDS = 14
MINHASH_ROWS = 8
NEAR_DUP_JACCARD = 0.80
CLUSTER_KEEP = 3
BOILERPLATE_DF = 50  # a clause seen in more than this many documents
BOILERPLATE_MIN_WORDS = 20
A0_SIMILARITY = 0.97  # original edition kept in full only below this

LEAK_NGRAM = 13
SHARD_DOCS = 5000

GOLDEN_IDS = {
    "-6986157": "qarshi",
    "-6961952": "qarshi",
    "-7026714": "qarshi_cancel",
    "-6832596": "yangiyol",
    "-7326620": "xatirchi",
    "-7395552": "xatirchi_cancel",
}
GOLDEN_REG = {
    "231-4-59-Q/24": "golden",
    "207-4-59-Q/24": "golden",
    "161-4-59-Q/23": "golden",
    "261-4-59-Q/24": "cancelling_act",
    "VI-76-4-10-146-K/24": "golden",
    "VI-76-21-10-146-K/24": "golden",
    "VII-3-1-5-77-K/25": "golden",
    "VII-4-12-5-77-K/25": "cancelling_act",
}
