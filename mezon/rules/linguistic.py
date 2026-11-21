"""Linguistic expertise (VMQ-662, annex 1, cl. 9: spelling, style, grammar and orthography rules).

Today one precise check: words that mix Latin and Cyrillic letters ("TАRKIBI" with a Cyrillic А). They break search
on lex.uz and in E-qaror and are spelling errors under the state-language rules. Measured 19.11.2026: 112 of 1,066
decisions. Reported in its own section, never as a legality flag, so spelling never buries a legal defect.
"""

import re

LAT = re.compile(r"[A-Za-z]")
CYR = re.compile(r"[А-Яа-яЁёЎўҚқҒғҲҳ]")
WORD = re.compile(r"[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳʻʼ'‘’`-]{3,}")
# Cyrillic letters that look like Latin ones, and back: the usual cause of a mixed word.
TO_LAT = str.maketrans({**dict(zip("АВЕКМНОРСТХаеорсухЁё", "ABEKMHOPCTXaeopcyxEe")), "Ъ": "ʼ", "ъ": "ʼ"})
TO_CYR = str.maketrans("ABEKMHOPCTXaeopcyx", "АВЕКМНОРСТХаеорсух")
NORM = ("linguistic662", "annex:1/cl:9", "imlo, uslubiy, grammatik va orfografiya")


def mixed_words(text: str, limit: int = 12) -> list[dict]:
    """Each distinct mixed-script word once, with the likely intended spelling and a few words of context."""
    out, seen = [], set()
    for m in WORD.finditer(text or ""):
        w = m.group(0)
        core = re.sub(r"[ʻʼ'‘’`-]", "", w)
        if w in seen or not (LAT.search(core) and CYR.search(core)) or re.fullmatch(r"[IVXLC]+", core):
            continue
        seen.add(w)
        lat, cyr = len(LAT.findall(core)), len(CYR.findall(core))
        fixed = w.translate(TO_LAT) if lat >= cyr else w.translate(TO_CYR)
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 40): m.end() + 40]).strip()
        out.append({"word": w, "fixed": fixed, "context": ctx})
        if len(out) >= limit:
            break
    return out


def section(text: str, law=None, on: str = "") -> dict:
    found = mixed_words(text)
    norm = None
    if law is not None and found:
        unit = law.get_unit(NORM[0], NORM[1], on) if on else None
        if unit and NORM[2] in unit["text"]:
            norm = {"act": "VMQ-662 (lingvistik ekspertiza to'g'risidagi Nizom)", "clause": "9-band",
                    "quote": NORM[2] + " qoidalari", "url": unit.get("url", "")}
    return {"findings": found, "norm": norm, "checked": bool(text)}
