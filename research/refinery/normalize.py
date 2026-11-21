"""Training-text normalisation (design section 6b). Unlike `research.textnorm` (matching only: it transliterates and
deletes apostrophes) this keeps the original script and the official apostrophe forms: U+02BB after o/g, U+02BC
elsewhere inside a word."""

import re
import unicodedata

_APOS = "ʻ‘’ʼ´`'"
_L = r"[^\W\d_]"
_APOS_INSIDE = re.compile(rf"(?<={_L})[{re.escape(_APOS)}](?={_L})")
_WORD = re.compile(rf"(?:{_L}|(?<={_L})[{re.escape(_APOS)}](?={_L}))+")
_GLUE = re.compile(r"(?<=[a-zʻʼ]{3})(\d{2,})")
_CYR = re.compile(r"[Ѐ-ӿ]")
_LAT = re.compile(r"[A-Za-z]")

# Cyrillic letters that look like Latin ones and the reverse (a e o c p x y k plus capitals)
C2L = dict(zip("аеорсхук" + "АВЕКМНОРСТХУ", "aeopcxyk" + "ABEKMHOPCTXY", strict=True))
L2C = {v: k for k, v in C2L.items()}
_UZ_CYR = set("ўқғҳЎҚҒҲ")
_UZ_WORDS = {
    "va",
    "bilan",
    "uchun",
    "tugrisida",
    "qaror",
    "hamda",
    "moddasi",
    "toʻgʻrisida",
    "etiladi",
    "boʻyicha",
    "qilish",
    "tartibi",
    "asosida",
    "belgilash",
    "tasdiqlash",
    "tuman",
    "hokimi",
    "kengashi",
}
_EN_WORDS = {"the", "and", "of", "shall", "law", "to", "in", "for", "with", "this", "is"}


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def script_counts(text: str) -> tuple[int, int]:
    return len(_LAT.findall(text)), len(_CYR.findall(text))


def script_share(text: str) -> tuple[float, float]:
    """(latin share, cyrillic share) among the Latin and Cyrillic letters."""
    lat, cyr = script_counts(text)
    n = lat + cyr
    return (lat / n, cyr / n) if n else (0.0, 0.0)


def fix_homoglyphs(text: str) -> tuple[str, int]:
    """Words that mix both scripts: map the minority script's look-alike letters to the majority script."""
    fixed = 0

    def repair(m: re.Match) -> str:
        nonlocal fixed
        w = m.group(0)
        lat, cyr = len(_LAT.findall(w)), len(_CYR.findall(w))
        if not lat or not cyr:
            return w
        table = C2L if lat >= cyr else L2C
        new = "".join(table.get(ch, ch) for ch in w)
        if new != w:
            fixed += 1
        return new

    return _WORD.sub(repair, text), fixed


def mixed_script_words(text: str) -> int:
    return sum(1 for w in _WORD.findall(text) if _LAT.search(w) and _CYR.search(w))


def canon_apostrophes(text: str) -> str:
    """After o/g before a letter = U+02BB; any other apostrophe inside a word = U+02BC. Quotes around words stay."""
    return _APOS_INSIDE.sub(lambda m: "ʻ" if m.string[m.start() - 1] in "oOgG" else "ʼ", text)


def repair_glue(text: str) -> str:
    """Letters glued to a number ('boʻlimining2022'): split on that boundary only."""
    return _GLUE.sub(r" \1", text)


def normalise(text: str, latin: bool | None = None) -> tuple[str, dict]:
    """NFKC, homoglyph repair, apostrophes (Latin text only), glue repair, whitespace. Returns (text, stats).
    `latin` is the document-level script decision (short blocks would be misjudged); None = decide from this text."""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", nfkc(text))  # NUL and other control characters from PDFs
    t = t.replace(" ", " ").replace("\u200b", "").replace("﻿", "")
    before = mixed_script_words(t)
    t, fixed = fix_homoglyphs(t)
    if latin is None:
        lat, cyr = script_counts(t)
        latin = lat >= cyr
    if latin:
        t = canon_apostrophes(t)
        t = repair_glue(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t, {"mixed_before": before, "homoglyph_fixed": fixed, "mixed_after": mixed_script_words(t)}


def detect_lang(text: str) -> dict:
    """Rules on the text, not on the URL: Cyrillic share, Uzbek-only letters, Uzbek or English stopwords."""
    _, cyr_s = script_share(text)
    if cyr_s >= 0.5:
        uz = sum(1 for ch in text if ch in _UZ_CYR)
        if uz >= 2:
            return {"lang": "uz", "script": "Cyrl", "lang_conf": "cyrl+uz_letters"}
        return {"lang": "ru", "script": "Cyrl", "lang_conf": "cyrl_no_uz_letters"}
    words = [w.lower() for w in re.findall(r"[A-Za-zʻʼ‘’']+", text[:20000])]
    if not words:
        return {"lang": "unknown", "script": "Latn", "lang_conf": "no_words"}
    uz_hits = sum(1 for w in words if w in _UZ_WORDS)
    en_hits = sum(1 for w in words if w in _EN_WORDS)
    marks = len(re.findall("[ʻʼ‘’]", text[:20000]))
    if en_hits > uz_hits * 2 and marks < len(words) * 0.01:
        return {"lang": "en", "script": "Latn", "lang_conf": "en_stopwords"}
    return {
        "lang": "uz",
        "script": "Latn",
        "lang_conf": "latn_uz_markers" if uz_hits or marks else "latn_default",
    }
