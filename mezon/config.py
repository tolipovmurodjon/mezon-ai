"""Paths and endpoints, all overridable by environment variables."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STORE = Path(os.environ.get("MEZON_STORE", DATA / "store"))
LAW_DB = STORE / "laws.sqlite"
DECISIONS_DB = STORE / "decisions.sqlite"

LLM_BASE_URL = os.environ.get("MEZON_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
LLM_MODEL = os.environ.get("MEZON_LLM_MODEL", "")
LLM_TIMEOUT_S = float(os.environ.get("MEZON_LLM_TIMEOUT_S", "120"))
