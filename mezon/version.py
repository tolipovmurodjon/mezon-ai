"""Which rules and which law-store state produced an output, so any conclusion can be reproduced later.

The version is a short hash of the rule code and the knowledge files the rules read, plus the law store's newest
edition date. Two outputs with the same version came from the same rules on the same law; a region report only
compares snapshots of the same version, so a change in our rules can never look like a fix by adliya.
"""

import hashlib
import sqlite3
from functools import lru_cache
from pathlib import Path

from mezon.config import LAW_DB

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [*sorted((ROOT / "mezon" / "rules").glob("*.py")), ROOT / "mezon" / "plain.py", ROOT / "mezon" / "api" / "main.py",
          *sorted((ROOT / "data" / "knowledge").glob("*.csv")), *sorted((ROOT / "data" / "knowledge").glob("*.json"))]


@lru_cache(maxsize=1)
def ruleset() -> str:
    h = hashlib.sha256()
    for path in INPUTS:
        if path.exists():
            h.update(path.name.encode())
            h.update(path.read_bytes())
    law = "nolaw"
    try:
        con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
        newest, units = con.execute("SELECT max(valid_from), (SELECT count(*) FROM units) FROM editions WHERE valid_from <= date('now')").fetchone()
        law = f"{newest}:{units}"
        h.update(law.encode())
    except sqlite3.Error:
        pass
    return f"{h.hexdigest()[:8]} (qonun bazasi {law.split(':')[0]})"
