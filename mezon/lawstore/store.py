"""Point-in-time law store: which text of which act was in force on a given date."""

import re
import sqlite3
from datetime import date
from pathlib import Path

from mezon.config import LAW_DB
from research.textnorm import fold

SCHEMA = """
CREATE TABLE IF NOT EXISTS acts(
  act_key TEXT PRIMARY KEY, lex_id TEXT, title TEXT, type TEXT, number TEXT, adopted TEXT,
  lost_force TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS editions(
  act_key TEXT, ondate TEXT, valid_from TEXT, seq INTEGER, valid_to TEXT, provisional INTEGER DEFAULT 0,
  PRIMARY KEY(act_key, ondate));
CREATE TABLE IF NOT EXISTS units(
  id INTEGER PRIMARY KEY, act_key TEXT, path TEXT, heading TEXT, text TEXT, element_id TEXT, notes TEXT,
  seq_from INTEGER, seq_to INTEGER, valid_from TEXT, valid_to TEXT, ondate TEXT);
CREATE INDEX IF NOT EXISTS units_lookup ON units(act_key, path, seq_from, seq_to);
CREATE TABLE IF NOT EXISTS relations(
  from_act TEXT, panel TEXT, to_lex_id TEXT, title TEXT, date TEXT, kind_guess TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS units_fts USING fts5(heading, body, unit_id UNINDEXED, tokenize='unicode61');
"""
HEADING_WEIGHT = 5.0


def iso(d: str | date) -> str:
    """'dd.mm.yyyy', 'yyyy-mm-dd' or a date → 'yyyy-mm-dd'."""
    if isinstance(d, date):
        return d.isoformat()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else d[:10]


def connect(path: Path = LAW_DB) -> sqlite3.Connection:
    """Writer connection (build only): creates the schema, WAL so readers keep the old snapshot meanwhile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


_STOP = set(
    "qonun qonuni qonunning qonunga qonunida qonunlar kodeks kodeksi kodeksning kodeksining kodeksida togrisida togrisidagi "
    "haqida haqidagi ozbekiston respublikasi respublikasining respublikasi sonli son nomli the law of act "
    "moddasi modda zakon закон kuchdami".split()
)
_ALIASES = {
    "lsp": "lsp", "nla": "nla", "nhh": "nla", "nhh qonun": "nla", "tax": "taxcode", "soliq": "taxcode",
    "land": "landcode", "yer": "landcode", "budget": "budgetcode", "budjet": "budgetcode", "byudjet": "budgetcode",
    "constitution": "constitution", "konstitutsiya": "constitution", "konstitutsiyasi": "constitution",
    "adminproc": "adminproc", "mahalliy hokimiyat": "lsp", "local state power": "lsp",
}


class LawStore:
    def __init__(self, path: Path = LAW_DB):
        if not Path(path).exists():
            raise FileNotFoundError(f"law store not built: {path} (run python -m mezon.lawstore.build)")
        self.con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    def act(self, act_key: str) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM acts WHERE act_key=?", (act_key,)).fetchone()

    def find_act(self, query: str) -> str | None:
        """Act key by key, number (O'RQ-682, PQ-3666, 913-XII) or title words."""
        # the way questions name acts: «Title» (Kodeks), "Title", Title (Qonun, O'RQ-457): drop quotes and the type note,
        # but keep a number inside the parentheses as a second try
        paren = re.findall(r"\(([^)]*)\)", query)
        q = re.sub(r"\([^)]*\)", " ", query)
        q = re.sub(r"[«»\"“”„]", " ", q).strip(" ,.;")
        q = re.sub(r"\s+", " ", q)
        if not q and paren:
            q = paren[-1]
        hit = self._find(q)
        if hit is None:
            hit = self._resolve(q)
        if hit is None:
            for p in paren:  # only numbers here: a bare type word ("Kodeks", "Qonun") must not title-match some code
                for part in p.split(","):
                    if not re.search(r"\d", part):
                        continue
                    hit = self._find(part.strip())
                    if hit:
                        return hit
        return hit

    def _find(self, q: str) -> str | None:
        if not q:
            return None
        row = self.con.execute("SELECT act_key FROM acts WHERE act_key=?", (q,)).fetchone()
        if row:
            return row[0]
        num = re.sub(r"[^0-9a-z]", "", fold(q))
        # Cabinet resolutions are stored with a bare number ("140") under the key "vmq140", so "VMQ-140" matches the key.
        row = self.con.execute("SELECT act_key FROM acts WHERE act_key=?", (num,)).fetchone() if num else None
        if row:
            return row[0]
        for r in self.con.execute("SELECT act_key, number, title FROM acts"):
            if num and re.sub(r"[^0-9a-z]", "", fold(r["number"] or "")) == num:
                return r["act_key"]
        fq = fold(q)
        for r in self.con.execute("SELECT act_key, title FROM acts"):
            if fq and fq in fold(r["title"] or ""):
                return r["act_key"]
        return None

    def _resolve(self, q: str) -> str | None:
        """Forgiving fallback: aliases, numbers inside the phrase, then token overlap with titles (min score)."""
        fq = fold(q)
        if not fq:
            return None
        toks = [t for t in fq.split() if t not in _STOP]
        key = " ".join(toks)
        if key in _ALIASES and self.act(_ALIASES[key]):
            return _ALIASES[key]
        for t in toks:
            if t in _ALIASES and len(toks) == 1 and self.act(_ALIASES[t]):
                return _ALIASES[t]
        for m in re.finditer(r"(?<![0-9a-z])(?:[a-z]{1,4}\s*)?\d{1,5}(?:\s*[- ]\s*(?:xii|xi|x|iv|v?i{0,3}))?(?![0-9a-z])", fq):
            hit = self._find(m.group(0).strip())
            if hit:
                return hit
        if not toks:
            return None
        best, best_sc = None, 0.0
        for r in self.con.execute("SELECT act_key, title FROM acts"):
            tt = [t for t in fold(r["title"] or "").split() if t not in _STOP]
            if not tt:
                continue
            hit = sum(1 for t in toks if any(t[:5] == u[:5] and (len(t) >= 4 or t == u) for u in tt))
            sc = hit / len(toks) * 0.7 + hit / len(tt) * 0.3
            if hit / len(toks) >= 0.75 and (hit >= 2 or len(toks) == 1) and sc > best_sc:
                best, best_sc = r["act_key"], sc
        return best

    def editions(self, act_key: str) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM editions WHERE act_key=? ORDER BY seq", (act_key,)).fetchall()

    def edition_on(self, act_key: str, on: str | date) -> sqlite3.Row | None:
        """The latest edition that started on or before `on` (None before the act existed)."""
        return self.con.execute(
            "SELECT * FROM editions WHERE act_key=? AND valid_from<=? ORDER BY valid_from DESC, seq DESC LIMIT 1",
            (act_key, iso(on)),
        ).fetchone()

    def edition_gap(self, act_key: str, on: str | date, days: int = 365) -> tuple[str, str] | None:
        """(edition used, next stored edition) when the store skipped editions around `on` (the build keeps only
        recent editions of very large codes, e.g. the Tax Code before 2025-06), so the text may be out of date."""
        ed = self.edition_on(act_key, on)
        if ed is None:
            return None
        nxt = self.con.execute("SELECT valid_from FROM editions WHERE act_key=? AND valid_from>? ORDER BY valid_from LIMIT 1",
                               (act_key, ed["valid_from"])).fetchone()
        # The build keeps the first edition plus editions from a floor date on, so a skip can only follow seq 0;
        # a long quiet stretch later on is a real period without amendments, not missing data.
        if ed["seq"] == 0 and nxt and (date.fromisoformat(nxt[0]) - date.fromisoformat(ed["valid_from"])).days > days                 and iso(on) < nxt[0]:
            return ed["valid_from"], nxt[0]
        return None

    def in_force(self, act_key: str, on: str | date) -> tuple[bool, sqlite3.Row | None]:
        ed = self.edition_on(act_key, on)
        act = self.act(act_key)
        lost = act["lost_force"] if act else None
        return (ed is not None and not (lost and lost <= iso(on))), ed

    def url(self, act_key: str, ondate: str, element_id: str = "") -> str:
        act = self.act(act_key)
        if act is None:
            return ""
        d, n = ondate.split()
        return f"https://lex.uz/uz/docs/{act['lex_id']}?ONDATE={d}%20{n}" + (f"#{element_id}" if element_id else "")

    def get_unit(self, act_key: str, path: str, on: str | date) -> dict | None:
        """Text of one unit (e.g. 'art:18/part:6', 'annex:1/cl:92') as in force on `on`."""
        ed = self.edition_on(act_key, on)
        if ed is None:
            return None
        row = self.con.execute(
            "SELECT * FROM units WHERE act_key=? AND path=? AND seq_from<=? AND seq_to>=?",
            (act_key, path, ed["seq"], ed["seq"]),
        ).fetchone()
        if row is None:
            return None
        return {
            "act_key": act_key,
            "path": path,
            "heading": row["heading"],
            "text": row["text"],
            "notes": row["notes"],
            "edition": ed["ondate"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
            "provisional": bool(ed["provisional"]),
            "url": self.url(act_key, ed["ondate"], row["element_id"]),
        }

    def search(self, query: str, on: str | date, k: int = 8, act_key: str | None = None) -> list[dict]:
        """Units in force on `on` matching the query (Latin/Cyrillic and apostrophes folded), best first."""
        terms = [t for t in fold(query).split() if len(t) > 2]
        if not terms:
            return []
        out: list[dict] = []
        for joiner in (" AND ", " OR "):
            match = joiner.join(f'"{t}"*' for t in terms)
            rows = self.con.execute(
                f"""SELECT u.act_key, u.path, bm25(units_fts, {HEADING_WEIGHT}, 1.0) AS score
                   FROM units_fts JOIN units u ON u.id = units_fts.unit_id
                   WHERE units_fts MATCH ? AND u.valid_from <= ? AND (u.valid_to IS NULL OR u.valid_to > ?)
                   AND (? IS NULL OR u.act_key = ?)
                   ORDER BY score LIMIT ?""",
                (match, iso(on), iso(on), act_key, act_key, k * 3),
            ).fetchall()
            seen = {(r["act_key"], r["path"]) for r in out}
            for r in rows:
                if (r["act_key"], r["path"]) in seen:
                    continue
                unit = self.get_unit(r["act_key"], r["path"], on)
                if unit:
                    unit["score"] = r["score"]
                    out.append(unit)
                    seen.add((r["act_key"], r["path"]))
            if len(out) >= k:
                break
        return out[:k]
