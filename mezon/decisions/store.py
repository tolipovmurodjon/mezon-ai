"""Read-only access to the decision store."""

import json
import sqlite3
from pathlib import Path

from mezon.config import DECISIONS_DB


class DecisionStore:
    def __init__(self, db: Path = DECISIONS_DB):
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    def _row(self, r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        d["clauses"] = json.loads(d["clauses"] or "[]")
        d["stages"] = json.loads(d["stages"] or "{}")
        return d

    def get(self, decision_id: str) -> dict | None:
        return self._row(self.con.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone())

    def by_reg(self, reg_number: str) -> list[str]:
        """Ids carrying this registration number, decisions with text first."""
        cur = self.con.execute(
            "SELECT id FROM decisions WHERE reg_number=? ORDER BY length(text) DESC, id", (reg_number,)
        )
        return [r[0] for r in cur]

    def ids(self, role: str | None = None) -> list[str]:
        q, a = (
            ("SELECT id FROM decisions WHERE role=? ORDER BY id", (role,))
            if role
            else ("SELECT id FROM decisions ORDER BY id", ())
        )
        return [r[0] for r in self.con.execute(q, a)]

    def same_body(self, region: int, district: int, typ: str) -> list[dict]:
        cur = self.con.execute(
            "SELECT * FROM decisions WHERE region=? AND district=? AND type=? AND source='lex.uz' AND text != ''",
            (region, district, typ),
        )
        return [self._row(r) for r in cur]

    def drafts(self) -> list[dict]:
        return [self._row(r) for r in self.con.execute("SELECT * FROM decisions WHERE role='draft'")]
