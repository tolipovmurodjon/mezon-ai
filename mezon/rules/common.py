"""Helpers shared by the rules: law citations through the (optional) law store, verbatim quotes, dates."""

import calendar
import datetime as dt
import re

from mezon.report import Citation, Evidence
from research import textnorm

# Logical law references: (act number as the store knows it, display title).
LAW = {
    "nla": ("O'RQ-682", "Normativ-huquqiy hujjatlar to'g'risida Qonun (O'RQ-682)"),
    "lsp": ("913-XII", "Mahalliy davlat hokimiyati to'g'risida Qonun (913-XII)"),
    "o3333": ("3333", "Adliya vazirligining 3333-son buyrug'i: mahalliy loyihalar qoidalari"),
    "vmq390": ("VMQ-390", "Vazirlar Mahkamasining 390-son qarori (E-qaror nizomi)"),
    "pf6243": ("PF-6243", "Prezidentning PF-6243-son Farmoni (yer munosabatlari)"),
    # The Tax Code has no number in the store, so its store key stands in for one.
    "taxcode": ("taxcode", "O'zbekiston Respublikasining Soliq kodeksi"),
    "anticorruption860": ("O'RQ-860", "Normativ-huquqiy hujjatlarning korrupsiyaga qarshi ekspertizasi to'g'risida Qonun (O'RQ-860)"),
}


class SafeLaw:
    """Wraps the law store so that any missing method or runtime error degrades to "unknown", never a crash."""

    def __init__(self, store):
        self.store = store

    def __bool__(self) -> bool:
        return self.store is not None

    def _call(self, name, *args, default=None):
        fn = getattr(self.store, name, None)
        if fn is None:
            return default
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 - a broken law store must degrade to unknown, never crash an audit
            return default

    def find_act(self, number_or_title):
        return self._call("find_act", number_or_title)

    def in_force(self, act_key, date) -> bool | None:
        res = self._call("in_force", act_key, date)
        return res[0] if isinstance(res, tuple) else res

    def edition_on(self, act_key, date):
        return self._call("edition_on", act_key, date)

    def act(self, act_key) -> dict | None:
        row = self._call("act", act_key)
        return dict(row) if row is not None else None

    def get_unit(self, act_key, unit_path, on_date) -> dict | None:
        return self._call("get_unit", act_key, unit_path, on_date)


def cite(law: SafeLaw, ref: str, unit: str, on_date: str, needle: str | None = None) -> Citation:
    """A citation to `unit` of a known act as in force on `on_date`; the quote comes from the store when it can."""
    number, title = LAW[ref]
    key = (law.find_act(number) if law else None) or number
    u = law.get_unit(key, unit, on_date) if law else None
    quote, url = "", ""
    if u and u.get("text"):
        url = u.get("url", "")
        quote = best_sentence(u["text"], needle) if needle else whole_sentences(u["text"])
    return Citation(act_id=key, act_title=title, article=unit, quote=quote, on_date=on_date, url=url)


def whole_sentences(text: str, limit: int = 400) -> str:
    """Leading sentences of a legal text, never cut mid-sentence: the first sentence always, more while under `limit`."""
    sentences = re.split(r"(?<=[.;:])\s+", re.sub(r"\s+", " ", text).strip())
    out = sentences[0]
    for s in sentences[1:]:
        if len(out) + 1 + len(s) > limit:
            break
        out = f"{out} {s}"
    return out


def best_sentence(text: str, needle: str | None) -> str:
    sentences = re.split(r"(?<=[.;:])\s+", re.sub(r"\s+", " ", text).strip())
    if needle:
        n = squash(needle)
        for s in sentences:
            if n in squash(s):
                return s[:300]
    return sentences[0][:300] if sentences else ""


def squash(text: str) -> str:
    """Folded and without any whitespace: the comparison form for verbatim checks."""
    return re.sub(r"\s+", "", textnorm.fold(text))


def operative_clauses(text: str) -> list[tuple[int, str]]:
    """Numbered clauses of the operative part, in normalized (not folded) form, so they can be quoted."""
    t = textnorm.normalize(text)
    m = textnorm._OPERATIVE_RE.search(t)
    body = t[m.end() :] if m else t
    a = textnorm._ANNEX_RE.search(body)
    body = body[: a.start()] if a else body
    marks = list(textnorm._CLAUSE_RE.finditer(body))
    return [
        (
            int(mk.group(1)),
            body[mk.end() : (marks[i + 1].start() if i + 1 < len(marks) else len(body))].strip(),
        )
        for i, mk in enumerate(marks)
    ]


def preamble(text: str) -> str:
    t = textnorm.normalize(text)
    m = textnorm._OPERATIVE_RE.search(t)
    return t[: m.start()] if m else ""


def clip(s: str, n: int = 280) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0]


def text_evidence(decision: dict, locator: str, quote: str) -> Evidence:
    source = "draft" if decision.get("role") == "draft" else "decision"
    return Evidence(source=source, locator=locator, quote=clip(quote), url=decision.get("url") or "")


def date(s: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s) if s else None
    except ValueError:
        return None


def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def stage(decision: dict, needle: str) -> int | None:
    """The done (1) / skipped (0) value of the E-qaror stage whose name contains `needle`, if recorded."""
    for name, done in (decision.get("stages") or {}).items():
        if needle in textnorm.fold(name):
            return int(done)
    return None
