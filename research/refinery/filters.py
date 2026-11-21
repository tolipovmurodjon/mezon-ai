"""Stage 07: quality signals first (all kept as columns, nothing deleted), then the decision from config (design 6b)."""

import re
from collections import Counter

from research.refinery import config
from research.refinery.extract_ocr import ocr_quality
from research.refinery.normalize import mixed_script_words, script_share

_WORD = re.compile(r"[^\W\d_]{2,}")


def build_vocab(texts: list[str], min_count: int = 5, min_docs: int = 3) -> set[str]:
    """Vocabulary from clean HTML acts: tokens with count >= 5 in >= 3 documents."""
    cnt: Counter = Counter()
    dfc: Counter = Counter()
    for t in texts:
        w = [x.lower() for x in _WORD.findall(t)]
        cnt.update(w)
        dfc.update(set(w))
    return {w for w, c in cnt.items() if c >= min_count and dfc[w] >= min_docs}


def repetition(text: str) -> tuple[float, float]:
    """(share of duplicated non-empty lines, share of the most frequent 5-gram)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    dup = 1 - len(set(lines)) / len(lines) if lines else 0.0
    w = text.lower().split()
    grams = Counter(" ".join(w[i : i + 5]) for i in range(max(len(w) - 4, 0)))
    top = grams.most_common(1)[0][1] / max(sum(grams.values()), 1) if grams else 0.0
    return round(dup, 4), round(top, 4)


def signals(
    text: str,
    kind: str,
    expected_lang: dict | None,
    lang: dict,
    vocab: set[str] | None = None,
    n_table_chars: int = 0,
    table_numeric_share: float = 0.0,
) -> dict:
    body = text
    if kind in {"pdf_text", "ocr"}:
        # the e-qaror cover block (date, number, body: "2022 - yil 29 - yanvar | VI-48-... | Yangiyo'l shahar hokimligi")
        # is Latin even on Cyrillic decisions; it must not decide the script purity of a short document
        lines = text.split("\n")
        body = "\n".join(lines[3:]) if len(lines) > 6 else text
    lat, cyr = script_share(body)
    words = text.split()
    n_letters_main = max(lat, cyr)
    dup_lines, top5 = repetition(text)
    sig = {
        "n_chars": len(text),
        "n_words": len(words),
        "script_purity": round(n_letters_main, 4),
        "mixed_words": mixed_script_words(text),
        "mixed_share": round(mixed_script_words(text) / max(len(words), 1), 5),
        "dup_line_share": dup_lines,
        "top5gram_share": top5,
        "n_table_chars": n_table_chars,
        "table_numeric_share": table_numeric_share,
        "lang_mismatch": bool(
            expected_lang and expected_lang.get("script") and expected_lang["script"] != lang["script"]
        ),
        "chars_per_word": round(len(text) / max(len(words), 1), 2),
    }
    if kind in {"ocr", "pdf_text"} and vocab:
        sig.update(ocr_quality(text, vocab))
    return sig


def decide(sig: dict, source_kind: str, ocr_partial: bool = False) -> tuple[str, str]:
    """('keep'|'drop', reason). Tier is assigned elsewhere; flags that only lower the tier are in `flags`."""
    if sig["n_chars"] < config.MIN_CHARS:
        return "drop", "too_short"
    if ocr_partial:
        return "drop", "ocr_partial"
    if source_kind == "ocr":
        if sig.get("oov_rate", 0) > config.OOV_MAX:
            return "drop", "ocr_oov"
        if sig.get("nonalnum_share", 0) > 0.25:
            return "drop", "ocr_nonalnum"
    if source_kind in {"ocr", "pdf_text"} and (
        sig["dup_line_share"] > config.REPEAT_LINES_MAX or sig["top5gram_share"] > config.REPEAT_5GRAM_MAX
    ):
        return "drop", "repetition"
    if sig["script_purity"] < config.SCRIPT_PURITY or sig["mixed_share"] > config.MIXED_WORD_MAX:
        return "drop", "script_impure"
    return "keep", ""


def flags(sig: dict) -> list[str]:
    f = []
    if sig["n_chars"] < config.STUB_CHARS:
        f.append("stub")
    if sig["lang_mismatch"]:
        f.append("lang_mismatch")
    if sig["n_chars"] > config.MAX_DOC_CHARS:
        f.append("huge")
    if sig["n_table_chars"] > config.TABLE_BIG and sig["table_numeric_share"] > config.TABLE_NUMERIC:
        f.append("numeric_table")
    if sig["chars_per_word"] > 14:
        f.append("glued")
    return f


def tier(source_kind: str, level: str, fl: list[str]) -> str:
    if source_kind in {"ocr", "html_fallback"} or "stub" in fl or "lang_mismatch" in fl or "glued" in fl:
        return "C"
    if source_kind == "html" and level == "national" and not fl:
        return "A"
    return "B"
