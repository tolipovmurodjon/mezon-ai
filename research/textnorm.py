"""Uzbek legal text normalization shared by all research scripts."""

import re

APOSTROPHES = "ʻ‘’ʼ´`'"
_APOS_RE = re.compile(f"[{re.escape(APOSTROPHES)}]")

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ь": "", "ы": "i",
    "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}


def to_latin(text: str) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in _CYR:
            lat = _CYR[low]
            out.append(lat.capitalize() if ch != low and lat else lat)
        else:
            out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """Latin script, one apostrophe form, letters and digits unglued, whitespace collapsed."""
    t = _APOS_RE.sub("'", to_latin(text))
    t = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fold(text: str) -> str:
    """Lowercase, no apostrophes, only letters/digits/spaces; `o‘z`, `o`z`, `oz` and `ўз` all become `oz`."""
    t = _APOS_RE.sub("", to_latin(text).lower())
    t = re.sub(r"[^\w\s]|_", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_OPERATIVE_RE = re.compile(r"q\s*a\s*r\s*o\s*r\s*q\s*i\s*l\s*(?:a\s*m\s*a\s*n|a\s*d\s*i)\s*:?", re.IGNORECASE)
_ANNEX_RE = re.compile(r"qaror\w*\s+\d+\s*-\s*ilova\b", re.IGNORECASE)
_CLAUSE_RE = re.compile(r"(?:^|\s)(\d{1,2})\s*\.\s+(?=\S)")


_PAGE_ARTEFACTS = re.compile(r"e-qaror\.gov\.uz\s+\d{2}\.\d{2}\.\d{4}|^\s*\d{1,3}\s*$", re.IGNORECASE | re.MULTILINE)
_SIGNATURE_RE = re.compile(r"\b(?:tuman|shahar|viloyat)\s+hokimi\b|\bkengashi?\s+raisi\b|\bhokim\s+o'rinbosari\b", re.IGNORECASE)


def split_decision(text: str) -> dict:
    """Split a decision into preamble, operative part, numbered clauses and annex; every part is folded."""
    t = normalize(_PAGE_ARTEFACTS.sub(" ", text))
    m = _OPERATIVE_RE.search(t)
    if not m:
        return {"preamble": fold(t), "operative": "", "clauses": [], "annex": ""}
    preamble, rest = t[: m.start()], t[m.end():]
    a = _ANNEX_RE.search(rest)
    operative, annex = (rest[: a.start()], rest[a.start():]) if a else (rest, "")
    marks = list(_CLAUSE_RE.finditer(operative))
    if marks:
        sig = _SIGNATURE_RE.search(operative, marks[-1].end())
        if sig:
            operative = operative[: sig.start()]
    clauses = []
    for i, mk in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(operative)
        clauses.append((int(mk.group(1)), fold(operative[mk.end():end])))
    return {"preamble": fold(preamble), "operative": fold(operative), "clauses": clauses, "annex": fold(annex)}


def shingles(text: str, k: int = 5) -> set[str]:
    s = re.sub(r"\s+", "", fold(text))
    return {s[i: i + k] for i in range(max(len(s) - k + 1, 1))} if s else set()


def similarity(a: str, b: str, k: int = 5) -> float:
    """Jaccard on character k-shingles of folded, whitespace-free text: immune to glued words and broken tables."""
    sa, sb = shingles(a, k), shingles(b, k)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def bag_similarity(a: str, b: str) -> float:
    """Jaccard on word sets: order-free, for annex tables that pdftotext breaks into column fragments."""
    wa, wb = set(fold(a).split()), set(fold(b).split())
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0
