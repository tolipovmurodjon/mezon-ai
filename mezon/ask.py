"""Understanding a question to Mezon AI without a language model: the decision it is about, what the person wants to
know, and, when they do not know the number, which decisions match the place and topic they wrote."""

import re
from functools import lru_cache

from mezon.conclusion import _unit
from research.regnum import find_all
from research.textnorm import fold

# Registration numbers typed in Cyrillic: only letters that occur in them.
_CYR = str.maketrans({"К": "K", "к": "K", "Қ": "Q", "қ": "Q", "Ф": "F", "ф": "F", "В": "V", "в": "V", "І": "I",
                      "Х": "X", "х": "X", "Ю": "IU"})
_NUMBERISH = re.compile(r"[\w/-]*\d[\w/-]*")

INTENTS = [
    ("action", re.compile(r"qayerga|murojaat|shikoyat|nima qilay|nima qilish|kimga")),
    ("meaning", re.compile(r"nima degani|menga|biznesim|tadbirkor|ta.?siri|zarar|meni")),
    ("why", re.compile(r"nega|nima uchun|sabab|qaysi modda|asos")),
]
STOP = {"qaror", "qarori", "qarorlar", "haqida", "bormi", "qanday", "nima", "degani", "menga", "uchun", "tuman", "tumani",
        "tumanida", "shahar", "shahri", "viloyat", "viloyati", "hokim", "hokimi", "hokimligi", "kengash", "kengashi"}


def numbers(q: str) -> list[str]:
    """Registration numbers in the question, also when typed in Cyrillic."""
    fixed = _NUMBERISH.sub(lambda m: m.group(0).translate(_CYR), q or "")
    return [h["raw"] for h in find_all(fixed)]


def intent(q: str) -> str:
    f = fold(q or "")
    return next((name for name, rx in INTENTS if rx.search(f)), "overview")


def _stem(w: str) -> str:
    return w[:6] if len(w) > 6 else w


@lru_cache(maxsize=1)
def _index(con_id: int, con) -> list[tuple]:
    rows = con.execute("SELECT id, reg_number, title, body, adopted FROM decisions "
                       "WHERE role='adopted' AND length(coalesce(text,'')) > 0").fetchall()
    return [(r[0], r[1], r[2] or "", r[3] or "", r[4] or "", fold(f"{r[2] or ''} {r[3] or ''}").replace("'", ""))
            for r in rows]


def search(q: str, decisions, limit: int = 5) -> list[dict]:
    """Decisions whose title and issuing body contain every meaningful word of the question (by stem), newest first."""
    words = [_stem(w) for w in re.findall(r"[a-z]{4,}", fold(q or "").replace("'", "")) if w not in STOP]
    if not words:
        return []
    hits = [r for r in _index(id(decisions.con), decisions.con) if all(w in r[5] for w in words)]
    hits.sort(key=lambda r: r[4], reverse=True)
    return [{"reg_number": r[1], "title": r[2], "body": r[3], "adopted": r[4]} for r in hits[:limit]]


_NOTE = re.compile(r"(\d+(?:-\d+)?)-modda\s.*?(\d{4})-yil\s(\d{1,2})-(\w+?)dagi\s(\S+?)-sonli")


def specific(f: dict) -> str:
    """The decision's own problem in one plain sentence, built from the evidence the flag already carries."""
    if f.get("check") == "R_basis":
        note = next((e["quote"] for e in f.get("evidence") or [] if e.get("source") == "lexuz"), "")
        m = _NOTE.search(note)
        if m:
            return (f"Bu qaror qonunning {m[1]}-moddasiga tayanadi, lekin bu modda {m[2]}-yil {m[3]}-{m[4]}dagi "
                    f"{m[5]} bilan kuchini yo'qotgan. Shuning uchun qarorning huquqiy asosini ekspert tekshirishi kerak.")
    title = f.get("title_uz") or ""
    if title:
        plain = f.get("plain_uz") or ""
        return f"Bu qarorda: {title[0].lower() + title[1:]}." + (f" {plain}" if plain else "")
    return ""


def lead(kind: str, flags: list[dict], who: str) -> str:
    """One sentence that answers the question first, before the details."""
    if not flags:
        return "Avtomatik tekshiruvlarda kamchilik topilmadi; ekspert qolgan masalalarni ko'radi."
    f = flags[0]
    if who != "expert" and kind in ("overview", "meaning", "why") and (s := specific(f)):
        return s
    title = f.get("title_uz") or f.get("title", "")
    cite = (f.get("citations") or [{}])[0]
    basis = f"{cite.get('act_title', '')}, {_unit(cite.get('article', ''))}".strip(", ")
    if kind == "why":
        return f"Belgilanish sababi: {title.lower()}. Asos: {basis}."
    if kind == "action":
        ch = (f.get("channels") or [{}])[0]
        return f"Birinchi qadam: {ch.get('name', 'tuman adliya bo`limi')} ({ch.get('why', '')}). Murojaat matni tayyor."
    if kind == "meaning" or who != "expert":
        return f.get("plain_uz") or title
    return f"{title}. Asos: {basis}."
