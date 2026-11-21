"""Stage 08: mask citizens only (Boss's decision 2, 21 Nov 2026). Rules only, both scripts, no model, no network.

Masked: citizens' names, passport / personal ID numbers, phones, e-mails, bank accounts, cadastre numbers, car plates,
house and flat numbers, birth dates. Kept: officials with their role and the signature line (public office), places,
bodies, the President. Replacement tokens are stable inside one document ([FUQARO_1], [FUQARO_2]); the name-to-token
map lives only in memory, and the report stores counts per category, never strings."""

import re
from collections import Counter

from research.textnorm import fold

CAP = r"[A-ZА-ЯЁЎҚҒҲ][a-zа-яёўқғҳʻʼ‘’'`]+"
UPPER = r"[A-ZА-ЯЁЎҚҒҲ][A-ZА-ЯЁЎҚҒҲʻʼ‘’'`]{2,}"
NAME = rf"(?:{CAP}|{UPPER})"
PATRONYMIC = (
    r"(?:oʻgʻli|ogʻli|o‘g‘li|oʻgli|o'g'li|ogli|ugli|qizi|qiz|ўғли|ўгли|қизи|угли|кизи|"
    r"ovich|evich|ovna|evna|ович|евич|овна|евна)"
)
INITIALS = r"[A-ZА-ЯЁЎҚҒҲ]\.\s?(?:[A-ZА-ЯЁЎҚҒҲ]\.)?"
OFFICIAL = re.compile(
    r"(?:hokim\w*|prezident\w*|vazir\w*|raisi|rais\w*|prokuror\w*|direktor\w*|boshliq\w*|mudir\w*|bosh\s+\w+|"
    r"deputat\w*|senator\w*|rahbar\w*|ҳоким\w*|президент\w*|вазир\w*|раис\w*|прокурор\w*|директор\w*|"
    r"бошлиқ\w*|мудир\w*|депутат\w*|раҳбар\w*|hokimi|tuman\s+hokimi)\W{0,3}$",
    re.IGNORECASE,
)
TRIGGER = re.compile(
    r"(?i:fuqaro\w*|YaTT|tadbirkor\w*|jismoniy\s+shaxs\w*|oila\s+aʼzo\w*|oila\s+a'zo\w*|vasiy\w*|homiy\w*|"
    r"ariza\s+beruvchi\w*|merosxoʻr\w*|yer\s+egasi\w*|mulk\s+egasi\w*|фуқаро\w*|ЯТТ|тадбиркор\w*|"
    r"жисмоний\s+шахс\w*|оила\s+аъзо\w*|васий\w*|ҳомий\w*|мерос\w*|гражданин\w*|гражданк\w*)\s+"
    rf"\(?({NAME}(?:\s+{NAME}){{0,2}})"
)
SURNAME_SUFFIX = re.compile(
    r"(?:ov|ev|ova|eva|yev|yeva|zoda|qulov|boyev|xonov|ова|ев|ева|ов|зода|қулов|бойев)$", re.IGNORECASE
)
GUARDIANSHIP = re.compile(
    r"vasiylik|homiylik|voyaga\s+yetmagan|васийлик|ҳомийлик|вояга\s+етмаган|опека|попечител", re.IGNORECASE
)

_PATTERNS: dict[str, re.Pattern] = {
    "pinfl": re.compile(r"(?<!\d)\d{14}(?!\d)"),
    "passport": re.compile(r"(?<![A-Za-zА-Я])(?:[A-Z]{2}|[А-Я]{2})\s?\d{7}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "phone": re.compile(
        r"(?:\+?998[\s\-]?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})|"
        r"(?:(?<=tel[:.\s])|(?<=тел[:.\s]))\s*\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
        re.IGNORECASE,
    ),
    "account": re.compile(r"(?<!\d)\d{20}(?!\d)"),
    "cadastre": re.compile(r"(?<!\d)\d{2}:\d{2}:\d{2}:\d{2}:\d{2}:\d{4}(?!\d)"),
    "plate": re.compile(r"(?<![\dA-Z])\d{2}\s?[A-Z]\s?\d{3}\s?[A-Z]{2}(?![\dA-Z])"),
    "stir": re.compile(r"(?:STIR|INN|СТИР|ИНН|JShShIR|ЖШШИР)\D{0,12}\d{9,14}", re.IGNORECASE),
    "birth": re.compile(
        r"(?:tugʻilgan|tug‘ilgan|туғилган|рождения)[^.\n]{0,25}?\d{2}\.\d{2}\.\d{4}|"
        r"\d{2}\.\d{2}\.\d{4}\s*(?:yilda\s+)?(?:tugʻilgan|tug‘ilgan|туғилган)",
        re.IGNORECASE,
    ),
    "house": re.compile(
        r"\b\d{1,4}[A-Za-z]?\s*-?\s*(?:uy|xonadon|хонадон|уй)\b|"
        r"\b(?:uy|xonadon|хонадон|уй|dom|дом|kvartira|kv|кв)\.?\s*(?:raqami|рақами|№)?\s*\d{1,4}[A-Za-z]?\b",
        re.IGNORECASE,
    ),
}
_TOKEN = {
    "pinfl": "[RAQAM]",
    "passport": "[RAQAM]",
    "email": "[EMAIL]",
    "phone": "[TELEFON]",
    "account": "[RAQAM]",
    "cadastre": "[KADASTR]",
    "plate": "[RAQAM]",
    "stir": "[RAQAM]",
    "birth": "[SANA]",
    "house": "[MANZIL]",
}


def document_frequency(texts: list[str]) -> Counter:
    """Corpus document frequency of capitalised tokens (rare ones carrying a surname suffix are personal names)."""
    df: Counter = Counter()
    for t in texts:
        df.update(set(re.findall(CAP, t)))
    return df


def _is_official(context_before: str) -> bool:
    return bool(OFFICIAL.search(context_before[-45:]))


ROLE_NEAR = re.compile(
    r"hokim|rais|prezident|vazir|prokuror|direktor|boshliq|mudir|deputat|rahbar|oʻrinbosar|komissiya|markaz|boshqarma|bank|"
    r"inspeksiya|xizmat|boʻlim|qoʻmita|agentlik|kengash|mahkama|MChJ|korxona|tashkilot|"
    r"ҳоким|раис|президент|вазир|прокурор|директор|бошлиқ|мудир|депутат|раҳбар|ўринбосар|комиссия",
    re.IGNORECASE,
)
CITIZEN_NEAR = re.compile(
    r"fuqaro|YaTT|tadbirkor|jismoniy shaxs|ariza|vasiy|homiy|mulk egasi|yer egasi|merosxoʻr|"
    r"фуқаро|ЯТТ|тадбиркор|жисмоний шахс|ариза|васий|ҳомий|мулк эгаси|ер эгаси",
    re.IGNORECASE,
)


# A public position next to a name (commission table rows: "Karimov A. | tuman hokimi", "9 Aliyev V. aʼzosi").
# Stems cover the Latin and Cyrillic spellings and the case endings (boshligʻi, бошлиғи, бошлиқ, oʻrinbosari...).
POSITION = re.compile(
    r"hokim|oʻrinbosar|o'rinbosar|o‘rinbosar|muovin|boshlig|boshliq|rais|aʼzo|a'zo|a’zo|deputat|direktor|mudir|"
    r"rahbar|vazir(?!lar)|prokuror|kotib|"
    r"ҳоким|ўринбосар|муовин|бошлиғ|бошлиқ|раис|аъзо|депутат|директор|мудир|раҳбар|вазир(?!лар)|прокурор|котиб|"
    r"председател|начальник|заместител|директор|член\s+комисси",
    re.IGNORECASE,
)


_INSTITUTION_END = re.compile(
    r"(?:markazi|boʻlimi|bulimi|boshqarmasi|inspeksiyasi|qoʻmitasi|agentligi|tahririyati|gazetasi|"
    r"маркази|бўлими|бўлинмаси|бошқармаси|инспекцияси|қўмитаси|агентлиги|таҳририяти|газетаси)\s*\(\s*$",
    re.IGNORECASE,
)
_LINE_START = re.compile(r"^[\s\d.)(•\-–—|]{0,15}$")
_SEP_THEN_TITLE = re.compile(r"^\s*[,–—\-:(|]\s*\S")


def official_by_position(s: str, start: int, end: int) -> bool:
    """True when the name at s[start:end] is a person named with a public position: (1) any other cell of its table
    row names a position; (2) it opens a numbered list line ('9. Name – Tuman X boʻlimi boshligʻi'); (3) a separator
    and a position follow within 70 characters ('Name, tuman hokimi'); (4) a position comes right before it
    ('hokimning oʻrinbosari Name'); (5) it stands in brackets after an institution name. A citizen word right
    before the name (fuqaro, YaTT, ariza beruvchi ...) always wins: it stays masked. A plain 'Name ga ... hokimining
    qaroriga asosan' is not a position and is masked as before."""
    a = max(s.rfind("\n", 0, start), s.rfind("\x00", 0, start)) + 1
    ends = [i for i in (s.find("\n", end), s.find("\x00", end)) if i >= 0]
    b = min(ends) if ends else len(s)
    line, before, after = s[a:b], s[a:start], s[end:b]
    if CITIZEN_NEAR.search(before[-50:]):
        return False
    rest = before + " " + after
    if " | " in line:
        return bool(POSITION.search(rest))
    if _LINE_START.match(before) and len(line) < 300 and POSITION.search(after):
        return True
    if _SEP_THEN_TITLE.match(after) and POSITION.search(after[:70]):
        return True
    near_before = re.split(r"[.;:!?]", before[-45:])[-1]
    if POSITION.search(near_before):
        return True
    return bool(_INSTITUTION_END.search(before[-60:]))


def _citizen_context(before: str, sensitive: bool, after: str = "") -> bool:
    """Initials-names and rare name pairs are masked only when the text around them is about a citizen: a citizen
    word within 80 characters, or the whole document is a land / housing / social-support decision; a role word
    (hokim, rais, komissiya...) within 80 characters means an official, who stays."""
    near = before[-80:]
    if ROLE_NEAR.search(near) or ROLE_NEAR.search(after[:60]):  # the role may follow the name (a table row)
        return False
    return sensitive or bool(CITIZEN_NEAR.search(near))


def _sig_line_spans(text: str) -> list[tuple[int, int]]:
    """Lines that are signature blocks: a role word and a short line (kept)."""
    spans, pos = [], 0
    for line in re.split(r"[\n\x00]", text):
        if len(line) < 90 and re.search(
            r"hokim|rais|prezident|vazir|prokuror|direktor|ҳоким|раис|президент|вазир|"
            r"прокурор|директор",
            line,
            re.IGNORECASE,
        ):
            spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def mask(
    text: str,
    level: str,
    df: Counter | None = None,
    strong_only: bool = False,
    names: dict[str, int] | None = None,
    sensitive: bool = False,
) -> tuple[str, dict]:
    """Return (masked text, counts per category). level 'national' masks only numbers, phones and e-mails
    (officials and signatories are public); 'local' also masks citizen names and house numbers."""
    counts: Counter = Counter()
    names = {} if names is None else names
    span_cache: dict[str, list[tuple[int, int]]] = {}

    def in_keep(i: int, s: str) -> bool:
        spans = span_cache.get(s)
        if spans is None:
            spans = span_cache[s] = _sig_line_spans(s)
        return any(a <= i < b for a, b in spans)

    def tok_name(span: str) -> str:
        k = fold(span)
        if k not in names:
            names[k] = len(names) + 1
        return f"[FUQARO_{names[k]}]"

    out = text
    # numbers and strings first (all levels except house numbers, which are local only)
    for cat, rx in _PATTERNS.items():
        if cat == "house" and level == "national":
            continue
        if strong_only and cat in {"house", "birth", "stir"}:
            continue

        def sub(m: re.Match, cat=cat) -> str:
            counts[cat] += 1
            return _TOKEN[cat]

        out = rx.sub(sub, out)
    if level != "national":
        # 1. patronymic-anchored names (1-3 capitalised tokens before the patronymic)
        def sub1(m: re.Match) -> str:
            if (
                in_keep(m.start(), m.string)
                or _is_official(out[max(0, m.start() - 45) : m.start()])
                or official_by_position(m.string, m.start(), m.end())
            ):
                return m.group(0)
            counts["name_patronymic"] += 1
            return tok_name(m.group(0))

        out = re.sub(rf"(?<![\wʻʼ])({NAME}(?:\s+{NAME}){{0,2}}\s+{PATRONYMIC})\b", lambda m: sub1(m), out)

        # 1b. Russian-style patronymic glued to the last token (Rustamovich, Алишерович)
        def sub1b(m: re.Match) -> str:
            last = m.group(0).split()[-1]
            if not re.search(r"(?:ovich|evich|ovna|evna|ович|евич|овна|евна)$", last, re.IGNORECASE):
                return m.group(0)
            if (
                in_keep(m.start(), m.string)
                or _is_official(out[max(0, m.start() - 45) : m.start()])
                or official_by_position(m.string, m.start(), m.end())
            ):
                return m.group(0)
            counts["name_patronymic"] += 1
            return tok_name(m.group(0))

        out = re.sub(rf"(?<![\wʻʼ\[])({NAME}(?:\s+{NAME}){{1,2}})(?![\wʻʼ\]])", sub1b, out)

        # 2. trigger words then a capitalised span
        def sub2(m: re.Match) -> str:
            if in_keep(m.start(1), m.string):
                return m.group(0)
            counts["name_trigger"] += 1
            return m.group(0)[: m.start(1) - m.start(0)] + tok_name(m.group(1))

        out = TRIGGER.sub(sub2, out)

        # 2b. initials next to a surname
        def sub2b(m: re.Match) -> str:
            if (
                in_keep(m.start(), m.string)
                or official_by_position(m.string, m.start(), m.end())
                or not _citizen_context(m.string[: m.start()], sensitive, m.string[m.end() :])
                or re.search(r"F\.\s?I|Ф\.\s?И", m.group(0))
            ):
                return m.group(0)
            counts["name_initials"] += 1
            return tok_name(m.group(0))

        out = re.sub(rf"(?<![\wʻʼ])(?:{INITIALS}\s?{CAP}|{CAP}\s{INITIALS}(?!\s?{CAP}))", sub2b, out)
        # 3. rare capitalised pairs with a surname suffix (needs the document-frequency table)
        if df is not None and not strong_only:

            def sub3(m: re.Match) -> str:
                a, b = m.group(1), m.group(2)
                if (
                    in_keep(m.start(), m.string)
                    or official_by_position(m.string, m.start(), m.end())
                    or not _citizen_context(m.string[: m.start()], sensitive, m.string[m.end() :])
                ):
                    return m.group(0)
                if (
                    df.get(a, 0) < 30
                    and df.get(b, 0) < 30
                    and (SURNAME_SUFFIX.search(a) or SURNAME_SUFFIX.search(b))
                ):
                    counts["name_rare_pair"] += 1
                    return tok_name(m.group(0))
                return m.group(0)

            out = re.sub(rf"(?<![\w\[ʻʼ])({CAP})\s({CAP})(?![\wʻʼ\]])", sub3, out)
    return out, dict(counts)


def second_pass(masked: str, level: str, topics_text: str, df: Counter | None) -> dict:
    """Run the strong detectors again on the masked text. For guardianship / minors documents any remaining hit
    removes the document from the training set (kept only as a statistics row)."""
    _, residual = mask(masked, level, df, strong_only=True)
    guard = bool(GUARDIANSHIP.search(topics_text) or GUARDIANSHIP.search(masked[:6000]))
    hits = {k: v for k, v in residual.items()}
    return {"guardianship": guard, "residual": hits, "exclude": guard and bool(hits)}


def context_samples(original: str, masked: str, limit: int = 40, width: int = 40) -> list[str]:
    """Each mask with `width` characters of context on both sides (never the original string)."""
    out = []
    for m in re.finditer(r"\[(?:FUQARO_\d+|MANZIL|RAQAM|TELEFON|KADASTR|EMAIL|SANA)\]", masked):
        a, b = max(0, m.start() - width), min(len(masked), m.end() + width)
        out.append(masked[a:b].replace("\n", " "))
        if len(out) >= limit:
            break
    return out
