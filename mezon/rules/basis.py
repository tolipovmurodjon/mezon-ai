"""Legal basis: every national act cited in the preamble must be in force on the decision date."""

import json
import re
from functools import lru_cache
from pathlib import Path

from mezon.report import Evidence, Flag
from mezon.rules.common import SafeLaw, cite, preamble, text_evidence
from research.regulation_window import MONTHS
from research.textnorm import fold, normalize

ACT = re.compile(r"\b(PQ|PF|VMQ|O'?RQ)\s*[-–—­]?\s*(\d{1,5})\b", re.IGNORECASE)
_DATE = re.compile(rf"\b(20\d\d) yil (\d{{1,2}}) ({'|'.join(sorted(MONTHS, key=len, reverse=True))})\w*")


def _iso(m: re.Match) -> str:
    return f"{m[1]}-{MONTHS[m[3]]:02d}-{int(m[2]):02d}"


# Preambles mostly cite acts the long way: "Vazirlar Mahkamasining 2017-yil 15-martdagi 140-sonli qarori", or by name
# ("Soliq kodeksi"). Short forms alone found a basis in 458 of 1,066 adopted decisions; with these, 1,037 (19.11.2026).
VMQ_LONG = re.compile(r"vazirlar mahkamasining\s+(?:19|20)\d\d\W*yil\W*\d{1,2}\W*\w+\s+(\d{1,4})\W*son")
NAMED = {
    "taxcode": re.compile(r"soliq kodeks"),
    "budgetcode": re.compile(r"b[yu]?u?dj?et kodeks"),
    "landcode": re.compile(r"yer kodeks"),
    "lsp": re.compile(r"mahalliy davlat hokimiyati togrisida"),
    "nla": re.compile(r"normativ-huquqiy hujjatlar togrisida"),
}


def references(text: str) -> list[tuple[str, str]]:
    """(normalized act number, or "@<store key>" for an act cited by name; the preamble sentence that cites it)."""
    pre = preamble(text)
    out, seen = [], set()

    def add(num: str, s: str) -> None:
        if num not in seen:
            seen.add(num)
            out.append((num, s))

    for s in re.split(r"(?<=[.;])\s+", pre):
        for m in ACT.finditer(s):
            kind = m[1].upper().replace("'", "")
            kind = "O'RQ" if kind == "ORQ" else kind
            add(f"{kind}-{m[2]}", s)
        f = fold(s)
        for m in VMQ_LONG.finditer(f):
            add(f"VMQ-{m[1]}", s)
        for key, rx in NAMED.items():
            if rx.search(f):
                add(f"@{key}", s)
    return out


_ARTICLES = re.compile(r"((?:\d+(?:-\d+)?-?[\s,;]{1,3}(?:va\s{1,3})?)*\d+(?:-\d+)?)\s?-?\s?modda\w*")
_NEXT_ACT = re.compile(r"togrisida|kodeks|qarori|farmoni|qonuni(?!ning|ga)")


_SUPERSCRIPT = str.maketrans({"¹": "-1", "²": "-2", "³": "-3", "⁴": "-4", "⁵": "-5", "⁶": "-6", "⁷": "-7",
                              "⁸": "-8", "⁹": "-9"})


def split_article_numbers(group: str, key: str, exists=None) -> list[str]:
    """Article numbers in one "N, M va K"-style list. pdftotext loses the superscript of "16-2" and "21-1" and
    leaves "16 2" or "16²": two numbers separated by whitespace only (a real list uses a comma or "va") are one
    article N-M when `exists(key, "art:N-M")` says the store has it; without `exists` they stay separate."""
    out = []
    for part in re.split(r"\s*(?:[,;]|\bva\b)\s*", group):
        toks = re.findall(r"\d+(?:-\d+)?", part)
        i = 0
        while i < len(toks):
            if (i + 1 < len(toks) and exists is not None and "-" not in toks[i] and "-" not in toks[i + 1]
                    and exists(key, f"art:{toks[i]}-{toks[i + 1]}")):
                out.append(f"{toks[i]}-{toks[i + 1]}")
                i += 2
            else:
                out.append(toks[i])
                i += 1
    return out


def cited_articles(text: str, exists=None) -> list[tuple[str, str, str]]:
    """(store key, article path, the words) for articles named right after an act cited by its name.
    `exists(key, path) -> bool` (optional) lets "16 2" / "16²" read as article 16-2 when the store has that article."""
    # Hyphens must survive ("21-1-moddasi" is one article), so this reads normalized text, not fold(); the evidence
    # returned is the ORIGINAL preamble sentence, verbatim.
    out, seen = [], set()
    for sentence in re.split(r"(?<=[.;])\s+", preamble(text)):
        f = re.sub(r"[‘’ʻʼ'`]", "", normalize(re.sub(r"(?<=\d)\s?([¹²³⁴⁵⁶⁷⁸⁹])", r"\1", sentence).translate(_SUPERSCRIPT)).lower())
        for key, rx in NAMED.items():
            for m in rx.finditer(f):
                window = f[m.end(): m.end() + 140]
                stop = _NEXT_ACT.search(window, 12)
                window = window[: stop.start()] if stop else window
                for a in _ARTICLES.finditer(window):
                    for num in split_article_numbers(a.group(1), key, exists):
                        if (key, num) not in seen:
                            seen.add((key, num))
                            out.append((key, f"art:{num}", sentence.strip()))
    return out


def _around(sentence: str, num: str, width: int = 170) -> str:
    """The part of a long preamble sentence that names this article, verbatim."""
    m = re.search(rf"(?<![\d-]){re.escape(num)}(?!-\d)\s?-?\s?modda", sentence)
    if not m:
        return sentence
    start = max(0, m.start() - width)
    start = sentence.rfind(" ", 0, start) + 1 if start else 0
    return ("…" if start else "") + sentence[start: m.end() + 40].strip()


REPEAL_NOTES = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "repeal_notes.json"


@lru_cache(maxsize=1)
def _repeal_notes() -> dict:
    """lex.uz's own note on each repealed article (research/repeal_notes.py); empty if not built yet."""
    try:
        return json.loads(REPEAL_NOTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ever_existed(law: SafeLaw, key: str, path: str) -> bool:
    store = getattr(law, "store", None)
    con = getattr(store, "con", None)
    if con is None:
        return False
    return con.execute("SELECT 1 FROM units WHERE act_key=? AND path=? LIMIT 1", (key, path)).fetchone() is not None


def check(d: dict, law: SafeLaw) -> list:
    if not law or not d.get("text") or not d.get("adopted"):
        return []
    on = d["adopted"]
    flags = []
    for num, sentence in references(d["text"]):
        named = num.startswith("@")
        key = num[1:] if named else law.find_act(num)
        if not key:
            continue
        act = law.act(key) or {}
        adopted = act.get("adopted") or ""
        # Presidential act numbers restart every year since 2022, so a number alone can resolve to a different act:
        # trust the match only if that act already existed on the decision date and any date cited with it agrees.
        # An act cited by its name (a code, a named law) is unambiguous, so it skips the date match.
        if not adopted or adopted > on:
            continue
        cited_dates = {_iso(m) for m in _DATE.finditer(fold(sentence))}
        if not named and cited_dates and adopted not in cited_dates:
            continue
        if law.in_force(key, on) is False:
            flags.append(
                Flag(
                    check="R_basis",
                    title=f"Rests on {num.lstrip("@")}, which wasn't in force on {on}",
                    explanation=(
                        f"The preamble cites {num} as its basis, but the law store shows it was not in force on "
                        f"the decision date {on}. A decision can't rest on a lost act; the legal force of acts "
                        "follows their hierarchy and dates (NLA art. 18)."
                    ),
                    severity="medium",
                    evidence=[text_evidence(d, "preamble", sentence)],
                    citations=[cite(law, "nla", "art:18/part:3", on)],
                )
            )
    # An article of a law cited by its name that had lost force by the decision date (e.g. Law on Local State Power
    # art. 25, lost force under O'RQ-976 of 17.10.2024, still cited by decisions adopted in 2025).
    for key, path, words in cited_articles(d["text"]):
        if not _ever_existed(law, key, path) or law.get_unit(key, path, on):
            continue
        num = path.split(":")[1]
        flags.append(
            Flag(
                check="R_basis",
                title=f"Cites article {num} of {key}, which was not in force on {on}",
                explanation=(
                    f"The preamble names article {num} as a basis, but in the edition in force on {on} that article "
                    "no longer exists (it lost force or was repealed). A decision cannot rest on a norm that is not "
                    "in force (NLA art. 18); the drafter should cite the article now in force."
                ),
                severity="medium",
                evidence=[text_evidence(d, "preamble", _around(words, num))] + (
                    [Evidence(source="lexuz", locator=f"lex.uz: {num}-modda holati", quote=note["note"],
                              url=note["url"])]
                    if (note := _repeal_notes().get(key, {}).get(num)) else []),
                citations=[cite(law, "nla", "art:18/part:3", on)],
            )
        )
    return flags
