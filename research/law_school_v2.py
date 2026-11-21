"""Law school v2 data: a token-budgeted continued-pre-training mix from the refinery output (no model, no cloud).

    python -X utf8 -m research.law_school_v2 candidates   # incremental: index + raw text + core-act lessons per finished batch
    python -X utf8 -m research.law_school_v2 assemble --budget 50000000   # exclusions, balance, budget, replay -> shards
    python -X utf8 -m research.law_school_v2 estimate     # GPU-hour estimate only

Why v2 (pilot v1.1: each fact seen once, in one form: it learned the language of law and hierarchy, not recall of the
wording in force on a date). Allen-Zhu & Li (Physics of LMs 3.1): a fact becomes extractable only after many diverse
rewrites. So the mix has four parts:
  raw_latest    latest edition of every national act, header (title, number, date, status) on every chunk
  raw_editions  every distinct article chunk of every edition of the CORE acts (unchanged chunks are not repeated)
  lessons       per article-edition 5-9 diverse forms: verbatim, address->text at a date, text->address, cloze, since,
                in-force on a date (Ha/Yo'q 50/50), what changed, true/false vs an old edition (50/50); plus act-level
                hierarchy and conflict items (NLA art. 6 and 18), in Uzbek Latin, Uzbek Cyrillic (transliterated
                frames) and Russian frames, chosen by the act's own script
  replay        kind web + instr rows of data/train/mix_pilot.jsonl (FineWeb-2 uzn_Latn, Tulu 3)
Candidates are written per refinery batch and never rewritten once finished (add-only state in cand/state.sqlite), so a
re-run only does new batches. Exclusion of the exam happens in `assemble`, against every data/bench/mezonbench*.jsonl
present at that moment (v1, v1.1, where, v2, and any later file): every (act, article) of the exam is dropped from all
lessons AND raw chunks of that act, all editions. Re-run `assemble` when a new bench file appears.

Core acts: data/knowledge/core_acts.csv, plus the constitution and codes, plus a fill to N_CORE by rank. lex.uz cite
counts (cited_by_n) are 0 for every act in the refinery extract (the respondents panels were not crawled), so the rank
is (type, number of editions, number of units), and uses cited_by_n instead as soon as it is non-zero.
"""

import argparse
import datetime as dt
import gzip
import hashlib
import json
import random
import re
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "refinery" / "full"
OUT = ROOT / "data" / "train" / "lawschool_v2"
CAND = OUT / "cand"
BENCH_DIR = ROOT / "data" / "bench"
MIX_PILOT = ROOT / "data" / "train" / "mix_pilot.jsonl"
CORE_CSV = ROOT / "data" / "knowledge" / "core_acts.csv"
TOKENIZER = Path.home() / "models" / "Qwen3.8-27B"
SEED = 20261121
N_CORE = 300
CUT = "2026-10-01"
TODAY = dt.date(2026, 11, 21)
TOK_PER_SEC = 620
NATIONAL_SKIP = {"court"}   # rulings carry citizens' data; raw national acts only
RANK_TYPE = {"constitution": 0, "code": 1, "law": 2, "pf": 3, "pq": 4, "vmq": 5}
FORCE = {"constitution": 7, "law": 6, "code": 6, "chamber": 5, "pf": 4, "pq": 4, "f": 4, "vmq": 3, "ministry": 2, "local_hokim": 1,
         "local_kengash": 1}
SHARE = {"lessons": 0.40, "raw_latest": 0.25, "raw_editions": 0.10, "replay": 0.225, "hierarchy": 0.025}
LANG = {"uz_latn": "lat", "uz_cyrl": "cyr", "ru": "ru"}
LESSON_TYPE = {"constitution": "constitution", "law": "law", "code": "code", "pf": "pf", "pq": "pq", "vmq": "vmq",
               "ministry_order": "ministry", "local_hokim_qaror": "local_hokim", "local_kengash_qaror": "local_kengash",
               "local_farmoyish": "local_hokim", "court": "court", "f": "f", "chamber_resolution": "chamber", "other": "other"}
MAX_TPL_SHARE, MAX_ANS_SHARE, BAL_LO, BAL_HI = 0.03, 0.005, 0.45, 0.55
ACT_SHARE = {"lessons": 0.03, "raw_editions": 0.04}   # max share of a kind's budget that one act may fill
ROOT_CAP = 6          # lesson rows kept per (act, article root): editions x views x scripts, chosen by hash
MAX_ACT_ROWS_GEN = 60000   # candidate lesson rows kept per act per batch (new batches only; b000-b009 were written uncapped)
LESSON_LANG_SHARE = {"lat": 0.40, "cyr": 0.35, "ru": 0.25}   # of the lesson tokens, per script (Uzbek is the target)
OVERSHOOT = 1.35      # lessons are selected with this slack, then balanced/capped, then trimmed to budget
REPLAY_EXTRA = OUT / "replay_extra.jsonl.gz"


# ---------------------------------------------------------------- small helpers

def _lines(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _write(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    n = 0
    with open(tmp, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
            n += 1
    tmp.replace(path)
    return n


def root_of(path: str) -> str:
    """Article root of a unit path: 'art:5/part:2' -> 'art:5'; 'annex:1/cl:3' -> 'annex:1'."""
    pieces = (path or "").split("/")
    for i, p in enumerate(pieces):
        if p.startswith("art:"):
            return "/".join(pieces[: i + 1])
    return pieces[0]


def _rng(*parts) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, parts)).encode()) ^ SEED)


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ʻ", "'").replace("’", "'").replace("‘", "'").replace("ʼ", "'")).strip(" .;:,\"'«»")


def _nat_key(p: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"(\d+)", p or "") if x != ""]


# ---------------------------------------------------------------- Uzbek Latin -> Cyrillic (frames only, approximate)

_C1 = {"o'": "ў", "O'": "Ў", "g'": "ғ", "G'": "Ғ", "sh": "ш", "Sh": "Ш", "ch": "ч", "Ch": "Ч", "ng": "нг",
       "yo": "ё", "yu": "ю", "ya": "я", "ye": "е"}
_C2 = dict(zip("abdefghijklmnopqrstuvxyz", "абдефгҳижклмнопқрстувхйз", strict=True))
_C2.update({"c": "ц", "w": "в", "'": "ъ"})


def to_cyr(s: str) -> str:
    out, i, word_start = [], 0, True
    while i < len(s):
        if s[i] == "{":   # placeholder: copy verbatim
            j = s.index("}", i)
            out.append(s[i:j + 1])
            i = j + 1
            word_start = False
            continue
        two = s[i:i + 2]
        if two in _C1:
            out.append(_C1[two])
            i += 2
        else:
            ch = s[i]
            low = ch.lower()
            if low == "e" and word_start:
                m = "э"
            else:
                m = _C2.get(low, ch)
            out.append(m.upper() if ch.isupper() and m != ch else m)
            i += 1
        word_start = not s[i - 1].isalpha() and s[i - 1] != "'"
    return "".join(out)


# ---------------------------------------------------------------- templates (frame wording only; facts come from the store)
# type -> list of core question frames; the final template id is (core, label style, preamble), >= 60 per type.
CORES_LAT = {
    "addr2text": ["{a} {w} {d} sanadagi tahririda qanday yozilgan?", "{d} holatiga ko'ra {a} {w}ning matni qanday?",
                  "{a}: {w} — {d} sanada amalda bo'lgan matnni keltiring.", "{d} sanada kuchda bo'lgan {w} ({a}) matnini yozing.",
                  "{w} ({a}) {d} dagi tahrirda nima deyiladi?"],
    "text2addr": ["«{s}» — bu qaysi hujjat, qaysi modda va qaysi tahrir?", "Quyidagi norma qayerdan olingan va qaysi tahrirda: «{s}»?",
                  "Matn manbasini ko'rsating (hujjat, modda, tahrir): «{s}»", "«{s}»: hujjat nomi, joyi va tahrir sanasi?",
                  "Ushbu gap qaysi hujjatning qaysi qismida va qaysi sanadan kuchda: «{s}»"],
    "cloze": ["{a}, {w}. Tushirib qoldirilgan so'zlarni tiklang: «{q}»", "Bo'sh joyni (____) matn bo'yicha to'ldiring ({a}, {w}): «{q}»",
              "{w} ({a}) matnidagi tushib qolgan qismni yozing: «{q}»", "To'ldiring: «{q}» ({a}, {w})",
              "{a} {w} da quyidagi gapda nima yetishmayapti: «{q}»"],
    "since": ["{a}, {w}: quyidagi matn qaysi sanadan kuchga kirgan? «{s}»", "«{s}» — bu tahrir qachondan beri amalda ({a}, {w})?",
              "{w} ({a}): ushbu so'zlar bilan yozilgan tahrir qaysi sanadan boshlangan? «{s}»",
              "Qaysi sanadan kuchga kirgan tahrirda shunday yozilgan ({a}, {w}): «{s}»", "{a}, {w}: «{s}» matnining kuchga kirish sanasi?"],
    "inforce": ["{a}, {w}: «{s}» — bu matn {d} sanada amalda bo'lganmi?", "{d} sanada {w} ({a}) shunday edimi: «{s}»? Ha yoki yo'q.",
                "«{s}» ({a}, {w}) {d} holatiga ko'ra kuchda edimi?", "{d} sanada quyidagi tahrir amal qilganmi ({a}, {w}): «{s}»",
                "Shu matn ({a}, {w}) {d} sanada qonuniy kuchda bo'lganmi: «{s}»"],
    "change": ["{a}, {w}: {d1} dan keyingi tahrirda {d0} dagi matndan nima o'zgardi?", "{w} ({a}) {d0} dan {d1} ga o'tishda qanday o'zgargan?",
               "{d1} dagi tahrir {d0} dagisidan nimasi bilan farq qiladi ({a}, {w})?", "{a} {w}: {d1} sanada nima o'zgartirildi?",
               "Oldingi ({d0}) va yangi ({d1}) tahrirni solishtiring: {a}, {w}."],
    "tf": ["{a}, {w}, {d} dan amal qiluvchi tahrir bo'yicha to'g'rimi: «{s}»", "Matnga ko'ra to'g'rimi yoki noto'g'rimi ({a}, {w}, tahrir {d}): «{s}»",
           "«{s}» — {w} ({a}) {d} dagi tahriri bilan mos keladimi?", "To'g'ri/noto'g'ri: {a}, {w} ({d} dan): «{s}»",
           "{d} dan kuchda bo'lgan {w} ({a}) tahririda shunday yozilganmi: «{s}»"],
    "verbatim": ["{a}, {w} ({d} dan{e}) matni:", "{a}. {w}. Tahrir: {d} dan{e}. Matn:", "Hujjat: {a}. Joyi: {w}. {d} dan{e} amalda bo'lgan matn:",
                 "{w} ({a}), {d} dan{e} kuchda bo'lgan tahrir:", "Norma matni — {a}, {w}, tahrir {d} dan{e}:"],
    "hier": ["Agar {a1} va {a2} o'rtasida ziddiyat chiqsa, qaysi biri ustun?", "{a1} va {a2}: ziddiyat bo'lganda qaysi hujjat yuridik kuchi bo'yicha ustun turadi?",
             "Yuridik kuch bo'yicha solishtiring: {a1} va {a2}. Ziddiyatda qaysi biri qo'llanadi?",
             "{a1} bilan {a2} bir-biriga zid bo'lsa, qaysi biriga amal qilinadi?", "Ikki hujjatdan qaysi biri ustun: {a1} yoki {a2}?"],
}
CORES_RU = {
    "addr2text": ["{a}, {w}: как звучит редакция, действовавшая на {d}?", "Приведите текст {w} ({a}) по состоянию на {d}.",
                  "{w} ({a}) в редакции на {d}: какой текст?", "Какой текст имела {w} ({a}) на дату {d}?", "{a}: {w}, редакция на {d}."],
    "text2addr": ["«{s}» — из какого акта, какой статьи и какой редакции?", "Укажите источник (акт, место, дата редакции): «{s}»",
                  "Откуда эта норма и с какой даты она действует: «{s}»?", "«{s}»: название акта, место и дата редакции?",
                  "В каком акте и в какой его части сказано: «{s}»?"],
    "cloze": ["{a}, {w}. Восстановите пропущенные слова: «{q}»", "Заполните пропуск (____) по тексту ({a}, {w}): «{q}»",
              "{w} ({a}): какие слова пропущены: «{q}»", "Дополните: «{q}» ({a}, {w})", "Чего не хватает в тексте {w} ({a}): «{q}»"],
    "since": ["{a}, {w}: с какой даты действует редакция «{s}»?", "«{s}» — с какого числа действует эта редакция ({a}, {w})?",
              "{w} ({a}): когда вступила в силу редакция с текстом «{s}»?", "С какой даты применялась такая редакция ({a}, {w}): «{s}»",
              "{a}, {w}: дата начала действия текста «{s}»?"],
    "inforce": ["{a}, {w}: действовал ли этот текст на {d}? «{s}»", "На {d} {w} ({a}) звучала так: «{s}»? Да или нет.",
                "«{s}» ({a}, {w}) — действовало ли это по состоянию на {d}?", "Была ли на {d} в силе такая редакция ({a}, {w}): «{s}»",
                "Применялся ли на {d} следующий текст ({a}, {w}): «{s}»"],
    "change": ["{a}, {w}: что изменилось в редакции от {d1} по сравнению с {d0}?", "{w} ({a}): как изменился текст при переходе от {d0} к {d1}?",
               "Чем редакция {d1} отличается от редакции {d0} ({a}, {w})?", "{a}, {w}: что изменили {d1}?",
               "Сравните редакции {d0} и {d1}: {a}, {w}."],
    "tf": ["{a}, {w}, редакция с {d}: верно ли, что «{s}»?", "Верно или неверно по тексту ({a}, {w}, редакция {d}): «{s}»",
           "«{s}» — соответствует ли редакции {w} ({a}) от {d}?", "Верно/неверно: {a}, {w} (с {d}): «{s}»",
           "Так ли сказано в {w} ({a}) в редакции с {d}: «{s}»"],
    "verbatim": ["{a}, {w} (с {d}{e}) — текст:", "{a}. {w}. Редакция с {d}{e}. Текст:", "Акт: {a}. Место: {w}. Текст, действовавший с {d}{e}:",
                 "{w} ({a}), редакция с {d}{e}:", "Текст нормы — {a}, {w}, редакция с {d}{e}:"],
    "hier": ["Если {a1} и {a2} противоречат друг другу, какой из них имеет приоритет?", "{a1} и {a2}: какой акт выше по юридической силе при коллизии?",
             "Сравните по юридической силе: {a1} и {a2}. Какой применяется при противоречии?",
             "При коллизии {a1} с {a2} какой акт применяется?", "Какой из двух актов приоритетен: {a1} или {a2}?"],
}
CORES = {"lat": CORES_LAT, "cyr": {k: [to_cyr(x) for x in v] for k, v in CORES_LAT.items()}, "ru": CORES_RU}
LABELS = {"lat": [("Savol", "Javob"), ("S", "J"), ("So'rov", "Natija")], "cyr": [("Савол", "Жавоб"), ("С", "Ж"), ("Сўров", "Натижа")],
          "ru": [("Вопрос", "Ответ"), ("В", "О"), ("Запрос", "Результат")]}
PREAMBLES = {"lat": ["", "Yuridik savol. ", "O'zbekiston qonunchiligi. ", "Qonun hujjatlari bo'yicha. "],
             "cyr": ["", "Юридик савол. ", "Ўзбекистон қонунчилиги. ", "Қонун ҳужжатлари бўйича. "],
             "ru": ["", "Юридический вопрос. ", "Законодательство Узбекистана. ", "По нормативным актам. "]}
WORDS = {"lat": {"art": "modda", "part": "qism", "cl": "band", "annex": "ilova", "ch": "bob", "sec": "bo'lim", "sub": "kichik band", "pre": "kirish qismi"},
         "cyr": {"art": "модда", "part": "қисм", "cl": "банд", "annex": "илова", "ch": "боб", "sec": "бўлим", "sub": "кичик банд", "pre": "кириш қисми"},
         "ru": {"art": "статья", "part": "часть", "cl": "пункт", "annex": "приложение", "ch": "глава", "sec": "раздел", "sub": "подпункт", "pre": "преамбула"}}
KIND = {"lat": {"law": "Qonun", "code": "Kodeks", "constitution": "Konstitutsiya", "pf": "Prezident Farmoni", "pq": "Prezident qarori",
                "vmq": "Vazirlar Mahkamasi qarori", "ministry": "vazirlik hujjati", "chamber": "palata qarori", "f": "Prezident farmoyishi",
                "other": "hujjat", "local_hokim": "hokim qarori", "local_kengash": "Kengash qarori", "court": "sud hujjati"},
        "ru": {"law": "Закон", "code": "Кодекс", "constitution": "Конституция", "pf": "Указ Президента", "pq": "Постановление Президента",
               "vmq": "Постановление Кабинета Министров", "ministry": "акт министерства", "chamber": "постановление палаты",
               "f": "Распоряжение Президента", "other": "акт", "local_hokim": "постановление хокима",
               "local_kengash": "решение Кенгаша", "court": "судебный акт"}}
KIND["cyr"] = {k: to_cyr(v) for k, v in KIND["lat"].items()}
NUMS = {"bir": "ikki", "ikki": "uch", "uch": "olti", "besh": "o'n", "o'n": "o'n besh", "o'n besh": "o'ttiz", "olti": "uch", "o'ttiz": "o'n"}
NUMS_RU = {"один": "два", "два": "три", "три": "шесть", "пять": "десять", "десять": "пятнадцать", "пятнадцать": "тридцать", "шесть": "три"}
NUMS_CYR = {to_cyr(k): to_cyr(v) for k, v in NUMS.items()}
YES = {"lat": ("Ha", "Yo'q"), "cyr": ("Ҳа", "Йўқ"), "ru": ("Да", "Нет")}
TF = {"lat": ("To'g'ri", "Noto'g'ri"), "cyr": ("Тўғри", "Нотўғри"), "ru": ("Верно", "Неверно")}
WHY = {"lat": {"yes": "bu tahrir {span} amalda bo'lgan", "before": "bu tahrir {d} dan keyin kuchga kirgan", "after": "bu tahrir {d} da o'z kuchini yo'qotgan"},
       "ru": {"yes": "эта редакция действовала {span}", "before": "эта редакция вступила в силу позже, с {d}", "after": "эта редакция утратила силу {d}"}}
WHY["cyr"] = {k: to_cyr(v) for k, v in WHY["lat"].items()}


def human_path(path: str, lang: str) -> str:
    w = WORDS[lang]
    out = []
    for piece in path.split("/"):
        kind, _, num = piece.partition(":")
        out.append(f"{w.get(kind, kind)} {num}" if lang == "ru" else f"{num}-{w.get(kind, kind)}")
    return ", ".join(out) if lang == "ru" else " ".join(out)


def act_name(a: dict, lang: str) -> str:
    kind = KIND[lang].get(a["type"], KIND[lang]["other"])
    num = (a.get("number") or "").strip()
    return f"«{a['title']}» ({kind}{', ' + num if num else ''})"


def frame(rng, lang: str, typ: str, **kw):
    """-> (template id, question text). Id = core x label x preamble."""
    cores = CORES[lang][typ]
    ci, li, pi = rng.randrange(len(cores)), rng.randrange(3), rng.randrange(4)
    return f"{typ}:{ci}.{li}.{pi}", li, PREAMBLES[lang][pi] + cores[ci].format(**kw)


def render(lang: str, li: int, q: str, ans: str) -> str:
    ql, al = LABELS[lang][li]
    return f"{ql}: {q}\n{al}: {ans}"


# ---------------------------------------------------------------- lesson items for one article interval

def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if 60 <= len(s.strip()) <= 400]


def changed_words(old: str, new: str) -> tuple[str, str]:
    a, b = old.split(), new.split()
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return " ".join(a[i:len(a) - j])[:300], " ".join(b[i:len(b) - j])[:300]


def lesson_row(u: dict, prev: dict | None, other: str | None, lang: str, view: int) -> dict | None:
    """One lesson: the address header plus 5-9 diverse items, all answers copied from the store."""
    a = {"type": u["type"], "title": u["title"], "number": u["number"]}
    name, where, vf, vt = act_name(a, lang), human_path(u["path"], lang), u["valid_from"], u["valid_to"]
    fd = _date(vf)
    if fd is None or not u["text"].strip():
        return None
    end = _date(vt) or TODAY
    rng = _rng(u["act_key"], u["path"], vf, view)
    text = u["text"].strip()
    sents = sentences(text)
    items: list[dict] = []

    def add(typ, ans, cls="", **kw):
        tpl, li, q = frame(rng, lang, typ, **kw)
        items.append({"t": typ, "tpl": tpl, "ans": ans, "cls": cls, "txt": render(lang, li, q, ans)})

    e = ""
    if vt:
        e = f" {vt} gacha" if lang != "ru" else f" по {vt}"
    if lang == "cyr":
        e = to_cyr(e)
    tpl, _, ver = frame(rng, lang, "verbatim", a=name, w=where, d=vf, e=e)
    if view == 0:
        body = text if len(text) <= 1800 else text[:1800].rsplit(" ", 1)[0] + " ..."
        items.append({"t": "verbatim", "tpl": tpl, "ans": body, "cls": "", "txt": f"{ver}\n{body}"})
    dmid = fd + dt.timedelta(days=rng.randint(0, max(0, (end - fd).days - (1 if vt else 0))))
    add("addr2text", text[:1200], a=name, w=where, d=dmid.isoformat())
    if sents:
        s = rng.choice(sents)
        add("text2addr", f"{name}, {where} ({vf} dan{e})" if lang != "ru" else f"{name}, {where} (с {vf}{e})", s=s[:240])
        words = s.split()
        if len(words) >= 10:
            k = rng.randint(3, len(words) - 4)
            n = min(4, len(words) - k - 1)
            add("cloze", " ".join(words[k:k + n]), a=name, w=where, q=" ".join(words[:k] + ["____"] + words[k + n:]))
        add("since", vf, a=name, w=where, s=s[:240])
        # in-force on a date, Ha/Yo'q 50/50
        span = f"{vf} .. {vt if vt else TODAY.isoformat()}"
        opts = []
        if fd > dt.date(1992, 1, 1):
            opts.append(("before", fd - dt.timedelta(days=rng.randint(1, 900))))
        if vt:
            opts.append(("after", end + dt.timedelta(days=rng.randint(1, 900))))
        want_yes = rng.random() < 0.5
        if want_yes or not opts:
            d_in = fd + dt.timedelta(days=rng.randint(0, max(0, (end - fd).days - (1 if vt else 0))))
            add("inforce", f"{YES[lang][0]}: {WHY[lang]['yes'].format(span=span)}.", cls=YES[lang][0], a=name, w=where, d=d_in.isoformat(), s=s[:240])
        else:
            kind, d_out = rng.choice(opts)
            add("inforce", f"{YES[lang][1]}: {WHY[lang][kind].format(d=vf if kind == 'before' else vt)}.", cls=YES[lang][1], a=name, w=where,
                d=d_out.isoformat(), s=s[:240])
        # true / false against this edition (false: changed number, previous edition's wording, or a foreign sentence)
        nums = NUMS if lang == "lat" else NUMS_CYR if lang == "cyr" else NUMS_RU
        m = next((w for w in nums if re.search(rf"\b{re.escape(w)}\b", s)), None)
        old = [x for x in sentences(prev["text"]) if _fold(x) not in _fold(text)] if prev else []
        if rng.random() < 0.5 and (m or old or other):
            if m and (rng.random() < 0.5 or not (old or other)):
                shown, why = re.sub(rf"\b{re.escape(m)}\b", nums[m], s, count=1)[:300], {"lat": f"matnda «{m}»", "cyr": f"матнда «{m}»", "ru": f"в тексте «{m}»"}[lang]
            elif old:
                shown, why = rng.choice(old)[:300], {"lat": f"bu oldingi tahrir ({prev['valid_from']}) matni", "cyr": f"бу олдинги таҳрир ({prev['valid_from']}) матни",
                                                     "ru": f"это текст предыдущей редакции ({prev['valid_from']})"}[lang]
            else:
                shown, why = other[:300], {"lat": "bu gap ushbu normada yo'q", "cyr": "бу гап ушбу нормада йўқ", "ru": "этого предложения в норме нет"}[lang]
            add("tf", f"{TF[lang][1]}: {why}.", cls=TF[lang][1], a=name, w=where, d=vf, s=shown)
        else:
            add("tf", f"{TF[lang][0]}.", cls=TF[lang][0], a=name, w=where, d=vf, s=s[:300])
    if prev is not None and _fold(prev["text"]) != _fold(text):
        o, n = changed_words(prev["text"], text)
        if o or n:
            add("change", f"«{o or '—'}» → «{n or '—'}»", a=name, w=where, d0=prev["valid_from"], d1=vf)
    if len(items) < 5:
        return None
    rng.shuffle(items)
    return {"act": u["act_key"], "lex_id": u["lex_id"], "path": u["path"], "root": root_of(u["path"]), "vf": vf, "lang": lang,
            "view": view, "items": items, "head": f"{name}, {where}" + (f". {u['heading']}" if u.get("heading") else "")}


# ---------------------------------------------------------------- state + candidates

def _db() -> sqlite3.Connection:
    CAND.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CAND / "state.sqlite", timeout=60)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS raw_done(batch TEXT PRIMARY KEY, src TEXT, n INTEGER);
    CREATE TABLE IF NOT EXISTS core_done(batch TEXT, lex_id TEXT, PRIMARY KEY(batch, lex_id));
    CREATE TABLE IF NOT EXISTS idx(lex_id TEXT PRIMARY KEY, batch TEXT, type TEXT, level TEXT, title TEXT, number TEXT, adopted TEXT,
        status TEXT, lang TEXT, n_editions INTEGER, n_chars INTEGER, cited INTEGER);
    CREATE TABLE IF NOT EXISTS hashes(h TEXT PRIMARY KEY);
    """)
    return con


def _hash(text: str) -> str:
    return hashlib.sha1(_fold(text).encode()).hexdigest()[:20]


def core_map() -> dict[str, str]:
    """lex_id (signed) -> act_key from core_acts.csv."""
    import csv
    if not CORE_CSV.exists():
        return {}
    with open(CORE_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["lex_id"]: r["act_key"] for r in csv.DictReader(f) if r.get("lex_id")}


def finished_batches(phase: str) -> list[str]:
    return sorted(p.name.split("_")[1].split(".")[0] for p in (REF / "markers").glob(f"{phase}_b*._DONE"))


def _tag(meta) -> tuple[str, str]:
    return {"uz_latn": ("uz", "Latn"), "uz_cyrl": ("uz", "Cyrl"), "ru": ("ru", "Cyrl"), "en": ("en", "Latn")}.get(meta.get("catalog_lang"), ("uz", "Latn"))


def chunk_roots(blocks: list[dict], chunks: list[dict]) -> list[list[str]]:
    """Article roots inside each chunk (chunks are consecutive partitions of the blocks): linear walk."""
    out, i = [], 0
    for ch in chunks:
        pos, roots = 0, set()
        while i < len(blocks):
            j = ch["text"].find(blocks[i]["text"], pos)
            if j < 0:
                break
            pos = j + len(blocks[i]["text"])
            rt = blocks[i].get("art") or (root_of(blocks[i]["path"]) if blocks[i].get("path") else None)
            if rt:
                roots.add(rt)
            i += 1
        out.append(sorted(roots))
    return out


def pass_raw(con, b: str, src: str) -> None:
    """Index every act of the batch; write the latest edition of every national act (chunked, header on each chunk)."""
    from research.refinery import export
    rows, idx = [], []
    cm = core_map()
    p3 = {}
    if src == "p3":   # refinery P3 cpt_docs: already masked, filtered, deduplicated, leak-checked
        for f in sorted((REF / "07_train" / "cpt_docs").glob(f"{b}-*.jsonl.gz")):
            for r in _lines(f):
                p3.setdefault(r["lex_id"], []).append(r)
    for r in _lines(REF / "01_extract" / "acts" / f"{b}-000.jsonl.gz"):
        m = r["meta"]
        lang, script = _tag(m)
        n_chars = sum(len(x["text"]) for x in r["blocks"])
        idx.append((r["lex_id"], b, LESSON_TYPE.get(m["act_type"], "other"), m["level"], m.get("title", ""), m.get("number") or "",
                    m.get("adopted") or "", m["status"], f"{lang}-{script}", len(r.get("editions") or []), n_chars, int(r.get("cited_by_n") or 0)))
        if m["level"] != "national" or m["act_type"] in NATIONAL_SKIP:
            continue
        if src == "p3":
            for c in p3.get(r["lex_id"], []):
                if c.get("level") == "national" and c["text"].strip():
                    rows.append({"lex_id": r["lex_id"], "act": cm.get(r["lex_id"], r["lex_id"]), "type": LESSON_TYPE.get(c["act_type"], "other"), "lang": f"{c['lang']}-{c['script']}",
                                 "vf": c.get("valid_from"), "roots": [], "text": c["text"], "src": "p3"})
            continue
        if r["source_kind"] == "ocr" or r.get("ocr_pending"):
            continue   # unrestored OCR text is not safe without the refinery's letter restoration
        blocks = [b_ for b_ in r["blocks"] if b_["text"].strip()]
        body = "\n".join(x["text"] for x in blocks)
        if len(body) < 400 or len(body) > 400_000:
            continue
        h = _hash(body)
        if con.execute("SELECT 1 FROM hashes WHERE h=?", (h,)).fetchone():
            continue
        con.execute("INSERT OR IGNORE INTO hashes VALUES (?)", (h,))
        eds = r.get("editions") or []
        v_from = eds[-1]["valid_from"] if eds else m.get("adopted")
        hdr = export.header(m, lang, script, v_from, None, "provisional" if m.get("provisional") else m["status"])
        chunks = export.chunk_by_article(blocks, hdr)
        for ch, roots in zip(chunks, chunk_roots(blocks, chunks), strict=True):
            rows.append({"lex_id": r["lex_id"], "act": cm.get(r["lex_id"], r["lex_id"]), "type": LESSON_TYPE.get(m["act_type"], "other"),
                         "lang": f"{lang}-{script}", "vf": v_from, "roots": roots, "text": ch["text"], "src": "p1"})
    con.executemany("INSERT OR REPLACE INTO idx VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", idx)
    n = _write(CAND / "raw_latest" / f"{b}.jsonl.gz", rows)
    con.execute("INSERT OR REPLACE INTO raw_done VALUES (?,?,?)", (b, src, n))
    con.commit()
    print(f"raw {b} ({src}): {len(idx)} acts indexed, {n} raw chunks", flush=True)


def select_core(con, n_core: int = N_CORE) -> dict[str, str]:
    """lex_id -> act_key (store key for the bench acts, else lex_id)."""
    cm = core_map()
    chosen = {lid: ak for lid, ak in cm.items() if con.execute("SELECT 1 FROM idx WHERE lex_id=?", (lid,)).fetchone()}
    for (lid,) in con.execute("SELECT lex_id FROM idx WHERE level='national' AND type IN ('constitution','code')"):
        chosen.setdefault(lid, lid)
    rest = con.execute("SELECT lex_id,type,n_editions,n_chars,cited FROM idx WHERE level='national' AND type IN ('law','pf','pq','vmq') "
                       "AND n_editions>1").fetchall()
    use_cites = any(r[4] for r in rest)
    rest.sort(key=lambda r: (-r[4], RANK_TYPE[r[1]], -r[2]) if use_cites else (RANK_TYPE[r[1]], -r[2], -r[3]))
    for r in rest:
        if len(chosen) >= n_core:
            break
        chosen.setdefault(r[0], r[0])
    return chosen


def pass_core(con, b: str, core: dict[str, str], views: int) -> None:
    """Edition documents + lessons for the core acts of one batch (from 01_extract/unit_versions)."""
    from research.refinery import export
    todo = {lid for lid in core if con.execute("SELECT 1 FROM idx WHERE lex_id=? AND batch=?", (lid, b)).fetchone()
            and not con.execute("SELECT 1 FROM core_done WHERE batch=? AND lex_id=?", (b, lid)).fetchone()}
    if not todo:
        return
    units: dict[str, list[dict]] = defaultdict(list)
    for u in _lines(REF / "01_extract" / "unit_versions" / f"{b}-000.jsonl.gz"):
        if u["lex_id"] in todo and u.get("valid_from"):
            units[u["lex_id"]].append(u)
    metas = {}
    for r in _lines(REF / "01_extract" / "acts" / f"{b}-000.jsonl.gz"):
        if r["lex_id"] in todo:
            metas[r["lex_id"]] = {"meta": r["meta"], "editions": r.get("editions") or []}
    ed_rows, les_rows = [], []
    for lid in sorted(todo):
        m, eds, us = metas[lid]["meta"], metas[lid]["editions"], units[lid]
        lang_s, script = _tag(m)
        lang = LANG.get(m.get("catalog_lang"))
        act_key = core[lid]
        meta2 = {**m, "lost_force": None}
        # --- every edition, article-chunked, unchanged chunks dropped by hash
        for k, ed in enumerate(eds):
            cur = [u for u in us if not u.get("is_container") and u["seq_from"] <= k <= u["seq_to"] and u["text"].strip()]
            if not cur:
                continue
            cur.sort(key=lambda u: _nat_key(u["path"]))
            blocks, last = [], None
            for u in cur:
                rt = root_of(u["path"])
                if rt != last:
                    blocks.append({"kind": "article", "text": u["heading"] or rt, "path": rt, "art": rt})
                    last = rt
                blocks.append({"kind": "text", "text": u["text"], "path": u["path"], "art": rt})
            latest = k == len(eds) - 1
            hdr = export.header(meta2, lang_s, script, ed["valid_from"], None if latest else ed["valid_to"],
                                ("provisional" if ed.get("provisional") else m["status"]) if latest else "lost_force")
            chunks = export.chunk_by_article(blocks, hdr)
            roots_by_chunk = chunk_roots(blocks, chunks)
            for ci, ch in enumerate(chunks):
                body = ch["text"][len(hdr):]
                h = _hash(body)
                if con.execute("SELECT 1 FROM hashes WHERE h=?", (h,)).fetchone():
                    continue
                con.execute("INSERT OR IGNORE INTO hashes VALUES (?)", (h,))
                roots = roots_by_chunk[ci]
                ed_rows.append({"lex_id": lid, "act": act_key, "type": LESSON_TYPE.get(m["act_type"], "other"), "lang": f"{lang_s}-{script}",
                                "vf": ed["valid_from"], "k": k, "n_ed": len(eds), "roots": roots, "text": ch["text"]})
        # --- lessons
        if lang is None:
            con.execute("INSERT OR IGNORE INTO core_done VALUES (?,?)", (b, lid))
            continue
        meta3 = {**m, "lex_id": lid, "act_type": m["act_type"]}
        li = export.lesson_inputs(meta3, us, act_key, set(), CUT)
        by_path: dict[str, list[dict]] = defaultdict(list)
        for u in li:
            by_path[u["path"]].append(u)
        n0 = len(les_rows)
        pool: list[tuple[str, str]] = []
        for path in sorted(by_path, key=_nat_key):
            prev = None
            for u in sorted(by_path[path], key=lambda x: x["valid_from"]):
                p = {"text": u["prev_text"], "valid_from": prev["valid_from"] if prev else u["valid_from"]} if u.get("prev_text") else None
                prev = u
                other = next((s for p_, s in reversed(pool) if p_ != path), None)
                for v in range(views):
                    row = lesson_row(u, p, other, lang, v)
                    if row:
                        les_rows.append(row)
                pool.extend((path, s) for s in sentences(u["text"])[:2])
                pool = pool[-300:]
        if len(les_rows) - n0 > MAX_ACT_ROWS_GEN:   # one huge code must not fill the disk (b009: 302k rows for one act script)
            mine = sorted(les_rows[n0:], key=lesson_prio)
            les_rows[n0:] = mine[:MAX_ACT_ROWS_GEN]
        con.execute("INSERT OR IGNORE INTO core_done VALUES (?,?)", (b, lid))
    sfx = f"{b}.{len(core)}"
    n1 = _write(CAND / "raw_editions" / f"{sfx}.jsonl.gz", ed_rows)
    n2 = _write(CAND / "lessons" / f"{sfx}.jsonl.gz", les_rows)
    con.commit()
    print(f"core {b}: {len(todo)} acts, {n1} edition chunks, {n2} lessons", flush=True)


def cmd_candidates(a) -> None:
    sys.path.insert(0, str(ROOT))
    con = _db()
    p1, p3 = finished_batches("p1"), set(finished_batches("p3"))
    for b in p1:
        have = con.execute("SELECT src FROM raw_done WHERE batch=?", (b,)).fetchone()
        want = "p3" if b in p3 else "p1"
        if have and (have[0] == want or want == "p1"):
            continue
        pass_raw(con, b, want)
    core = select_core(con, a.n_core)
    (CAND / "core.json").write_text(json.dumps(core, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"core set: {len(core)} acts (of them {sum(1 for k, v in core.items() if k != v)} with a store key)", flush=True)
    for b in p1:
        pass_core(con, b, core, a.views)
    print("batches done:", {"p1": p1, "p3": sorted(p3)}, flush=True)


# ---------------------------------------------------------------- assemble

def absid(x) -> str:
    """lex.uz id without the sign: x and -x are the Latin and Cyrillic versions of one act."""
    return str(x or "").lstrip("-")


def load_exclusions() -> tuple[set[tuple[str, str]], dict[str, int], set[str]]:
    """(unsigned act id or bench key, article root) of every exam item, per file; plus the set of exam act ids.
    Both the Latin and the Cyrillic twin of an act are excluded (same unsigned id)."""
    ex: set[tuple[str, str]] = set()
    files, acts = {}, set()
    cm = {}
    f0 = BENCH_DIR / "core_absid.json"
    if f0.exists():
        cm = {k: absid(v) for k, v in json.loads(f0.read_text(encoding="utf-8")).items()}
    for lid, key in core_map().items():
        cm.setdefault(key, absid(lid))
    for f in sorted(BENCH_DIR.glob("mezonbench*.jsonl")):
        n = 0
        for line in f.open(encoding="utf-8"):
            if not line.strip():
                continue
            it = json.loads(line)
            if it.get("act") and it.get("path"):
                for a in {it["act"], cm.get(it["act"], it["act"])}:
                    ex.add((absid(a), root_of(it["path"])))
                    acts.add(absid(a))
                n += 1
        files[f.name] = n
    return ex, files, acts


def row_ids(r: dict) -> set[str]:
    return {x for x in (absid(r.get("lex_id")), absid(r.get("act"))) if x}


def make_keep(ex: set, acts: set):
    """keep(row): False when the row covers an exam (act, article) under any id of the act. A row of an exam act with no
    article roots (refinery P3 documents) is dropped as a whole: its articles cannot be checked."""
    def keep(r) -> bool:
        if r.get("act") == "hier":
            return True
        ids = row_ids(r)
        roots = [r["root"]] if r.get("root") else (r.get("roots") or [])
        if not roots:
            return not (ids & acts)
        return not any((i, rt) in ex for i in ids for rt in roots)
    return keep


def hier_items(con, core: dict[str, str], n: int, rnd: int = 1) -> list[dict]:
    """Act-level hierarchy / conflict items (NLA art. 6: force order; art. 18: equal force -> the later wins)."""
    acts = con.execute("SELECT lex_id,type,title,number,adopted,lang FROM idx WHERE level='national' AND type IN "
                       "('constitution','law','code','chamber','pf','pq','f','vmq','ministry') AND adopted<>'' AND length(title)>8").fetchall()
    acts = [x for x in acts if x[1] in FORCE or x[1] == "chamber_resolution"]
    pool = sorted([x for x in acts if x[0] in core] + [x for x in acts if x[0] not in core][:4000])
    rng = random.Random(SEED + 5 + rnd)
    out, seen = [], set()
    langs = {"lat": [x for x in pool if x[5] == "uz-Latn"], "cyr": [x for x in pool if x[5] == "uz-Cyrl"], "ru": [x for x in pool if x[5] == "ru"]}
    names = {"lat": "Latin", "cyr": "Cyrillic", "ru": "Russian"}  # noqa: F841
    tries = 0
    while len(out) < n and tries < n * 30:
        tries += 1
        lang = rng.choices(["lat", "cyr", "ru"], [0.5, 0.25, 0.25])[0]
        ps = langs[lang]
        if len(ps) < 2:
            continue
        x, y = rng.sample(ps, 2)
        fx, fy = FORCE.get(x[1], 5), FORCE.get(y[1], 5)
        da, db = _date(x[4]), _date(y[4])
        if fx == fy and (da is None or db is None or da == db):
            continue
        if (x[0], y[0]) in seen or (y[0], x[0]) in seen:
            continue
        seen.add((x[0], y[0]))
        if fx != fy:
            win = x if fx > fy else y
            rule = {"lat": "NLA 6-modda: yuridik kuch tartibi bo'yicha yuqori daraja ustun", "cyr": to_cyr("NLA 6-modda: yuridik kuch tartibi bo'yicha yuqori daraja ustun"),
                    "ru": "ст. 6 Закона о НПА: акт большей юридической силы имеет приоритет"}[lang]
        else:
            win = x if da > db else y
            rule = {"lat": "NLA 18-modda: teng kuchda keyin qabul qilingani ustun", "cyr": to_cyr("NLA 18-modda: teng kuchda keyin qabul qilingani ustun"),
                    "ru": "ст. 18 Закона о НПА: при равной силе приоритет у более позднего акта"}[lang]
        r2 = _rng("hier", x[0], y[0])
        first, second = (x, y) if r2.random() < 0.5 else (y, x)

        def nm(t):
            return act_name({"type": t[1], "title": t[2], "number": t[3]}, lang) + (f", {t[4]}" if t[4] else "")
        tpl, li, q = frame(r2, lang, "hier", a1=nm(first), a2=nm(second))
        pos = {"lat": ("Birinchisi", "Ikkinchisi"), "cyr": ("Биринчиси", "Иккинчиси"), "ru": ("Первый", "Второй")}[lang]
        cls = pos[0] if win is first else pos[1]
        ans = f"{cls}: {nm(win)}. {rule}."
        out.append({"act": "hier", "lex_id": x[0], "path": "", "root": "", "vf": "", "lang": lang, "view": 0, "head": "", "items": [
            {"t": "hier", "tpl": tpl, "ans": ans, "cls": cls, "txt": render(lang, li, q, ans)}]})
    return out


def _tokenizer():
    from tokenizers import Tokenizer
    return Tokenizer.from_file(str(TOKENIZER / "tokenizer.json"))


def ratio_by(tok, rows: list[dict], key, per: int = 200) -> dict:
    """chars per token measured with the Qwen tokenizer, per group (sample of `per` rows each)."""
    g: dict = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    out = {}
    rng = random.Random(1)
    for k, rs in g.items():
        smp = rng.sample(rs, min(per, len(rs)))
        texts = [x["_t"] for x in smp]
        n_tok = sum(len(e.ids) for e in tok.encode_batch(texts, add_special_tokens=False))
        out[k] = sum(len(t) for t in texts) / max(1, n_tok)
    return out


def lesson_text(row: dict) -> str:
    return row["head"] + "\n\n" + "\n\n".join(it["txt"] for it in row["items"]) if row["head"] else "\n\n".join(it["txt"] for it in row["items"])


def enforce(rows: list[dict], report: dict, _depth: int = 0) -> list[dict]:
    """Balance binary classes to 45-55 %, cap each template at 3 % of its type and each identical answer at 0.5 % of
    all items. Works on items; a lesson that falls under 3 items is dropped. Deterministic. Run it on the rows that will
    be written (shares are measured on the final set, not on the candidate pool)."""
    rng = random.Random(SEED + 9)
    drops = Counter()
    # 1. binary balance per (type, language)
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        for it in r["items"]:
            if it["cls"]:
                groups[(it["t"], r["lang"])].append(it)
    for key, its in groups.items():
        c = Counter(i["cls"] for i in its)
        if len(c) == 2 and sum(c.values()) >= 20:
            (big, nb), (small, ns) = c.most_common()
            keep = int(ns * BAL_HI / (1 - BAL_HI))
            if nb > keep:
                cand = [i for i in its if i["cls"] == big]
                rng.shuffle(cand)
                for i in cand[keep:]:
                    i["drop"] = True
                    drops["balance"] += 1
    # 2. template cap per type (all languages pooled by type)
    for typ in {i["t"] for r in rows for i in r["items"]}:
        its = [i for r in rows for i in r["items"] if i["t"] == typ and not i.get("drop")]
        cap = max(5, int(MAX_TPL_SHARE * len(its)))
        by = defaultdict(list)
        for i in its:
            by[i["tpl"]].append(i)
        for tpl, lst in by.items():
            if len(lst) > cap:
                rng.shuffle(lst)
                for i in lst[cap:]:
                    i["drop"] = True
                    drops["template_cap"] += 1
    # 3. identical answer cap (binary classes are governed by step 1; the cap applies to every other answer)
    live = [i for r in rows for i in r["items"] if not i.get("drop")]
    cap = max(3, int(MAX_ANS_SHARE * len(live)))
    by_ans = defaultdict(list)
    for i in live:
        if not i["cls"]:
            by_ans[i["ans"]].append(i)
    for ans, lst in by_ans.items():
        if len(lst) > cap:
            rng.shuffle(lst)
            for i in lst[cap:]:
                i["drop"] = True
                drops["identical_answer_cap"] += 1
    out = []
    for r in rows:
        r["items"] = [i for i in r["items"] if not i.get("drop")]
        if len(r["items"]) >= (1 if r["act"] == "hier" else 3):
            out.append(r)
        else:
            drops["lesson_too_small"] += 1
    acc = report.setdefault("enforce_drops", Counter())
    for k, v in drops.items():
        acc[k] += v
    if drops and _depth < 6:   # dropped items shrink the denominators of the shares: run again until stable
        return enforce(out, report, _depth + 1)
    return out


# ---------------------------------------------------------------- assemble: streaming pre-filter with caps

def lesson_prio(r: dict) -> int:
    return zlib.crc32(f"{r['act']}|{r['path']}|{r['vf']}|{r['view']}|{r['lang']}".encode()) ^ SEED


def row_key(kind: str, r: dict) -> str:
    if kind == "lessons":
        return f"{r['act']}|{r['path']}|{r['vf']}|{r['view']}|{r['lang']}"
    return hashlib.sha1(f"{r.get('lex_id')}|{r.get('vf')}|{r.get('text', '')[:400]}".encode()).hexdigest()[:20]


def prefilter(files, keep, used: set, prio, cap_root: int | None, cap_act_chars: int | None, rep: dict, name: str) -> list[dict]:
    """Stream rows; drop exam rows (leak) and rows already written in an earlier round, keep at most `cap_root` rows per
    (act, article root) and at most `cap_act_chars` characters per act (lowest priority number first). Heaps hold raw JSON
    lines only, so memory stays small. Returns decoded rows with '_p' (priority)."""
    import heapq
    excl = used_skip = seen = uid = 0
    heaps: dict[tuple, list] = defaultdict(list)
    for f in files:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                seen += 1
                if not keep(r):
                    excl += 1
                    continue
                if row_key(name, r) in used:
                    used_skip += 1
                    continue
                uid += 1
                a = absid(r.get("lex_id") or r.get("act"))
                hk = (a, r.get("root") or "") if cap_root else (a, uid)
                h = heaps[hk]
                heapq.heappush(h, (-prio(r), uid, len(r.get("text", "")) or len(line), line))
                if cap_root and len(h) > cap_root:
                    heapq.heappop(h)
    by_act: dict[str, list] = defaultdict(list)
    for hk, h in heaps.items():
        by_act[hk[0]].extend(h)
    out, act_trim = [], 0
    for lst in by_act.values():
        lst.sort(key=lambda t: -t[0])   # smallest priority number first
        tot = 0
        for negp, _, n, line in lst:
            if cap_act_chars and tot + n > cap_act_chars:
                act_trim += 1
                continue
            tot += n
            r = json.loads(line)
            r["_p"] = -negp
            out.append(r)
    rep.setdefault("prefilter", {})[name] = {"rows_seen": seen, "excluded_exam": excl, "skipped_used": used_skip, "rows_after_caps": len(out),
                                              "trimmed_by_act_cap": act_trim, "acts": len(by_act)}
    return out


def text_of_replay(r: dict) -> str:
    return r["text"] if "text" in r else "\n".join(m["content"] for m in r["messages"])


def replay_key(r: dict) -> str:
    return hashlib.sha1(text_of_replay(r)[:300].encode()).hexdigest()[:20]


def used_set(con, kind: str) -> set:
    return {k for (k,) in con.execute("SELECT key FROM used WHERE kind=?", (kind,))}


def top_share(rows: list[dict], key, size) -> dict:
    t: Counter = Counter()
    for r in rows:
        t[key(r)] += size(r)
    tot = sum(t.values()) or 1
    return {k: round(v / tot, 4) for k, v in t.most_common(4)}


def cmd_assemble(a) -> None:
    sys.path.insert(0, str(ROOT))
    con = _db()
    con.executescript("CREATE TABLE IF NOT EXISTS used(kind TEXT, key TEXT, PRIMARY KEY(kind,key));"
                      "CREATE TABLE IF NOT EXISTS rounds(n INTEGER PRIMARY KEY, ts TEXT, budget INTEGER, tokens INTEGER);")
    rnd = (con.execute("SELECT MAX(n) FROM rounds").fetchone()[0] or 0) + 1
    core = json.loads((CAND / "core.json").read_text(encoding="utf-8")) if (CAND / "core.json").exists() else {}
    ex, ex_files, exam_acts = load_exclusions()
    keep = make_keep(ex, exam_acts)
    rep: dict = {"round": rnd, "budget_tokens": a.budget, "exclusion_files": ex_files, "exclusion_pairs": len(ex), "exam_acts": len(exam_acts),
                 "mezonbench_v2_present": "mezonbench_v2.jsonl" in ex_files,
                 "batches": {"p1_finished": finished_batches("p1"), "p3_finished": finished_batches("p3"),
                             "raw_src": dict(con.execute("SELECT batch,src FROM raw_done").fetchall())}}
    rep["cand_files"] = {k: [f.name for f in sorted((CAND / k).glob("*.jsonl.gz"))] for k in ("lessons", "raw_editions", "raw_latest")}
    tok = _tokenizer()
    lesson_cap_chars = int(a.budget * SHARE["lessons"] * ACT_SHARE["lessons"] * 2.5 * OVERSHOOT)
    ed_cap_chars = int(a.budget * SHARE["raw_editions"] * ACT_SHARE["raw_editions"] * 2.5)
    pools = {
        "lessons": prefilter(sorted((CAND / "lessons").glob("*.jsonl.gz")), keep, used_set(con, "lessons"), lesson_prio, ROOT_CAP, lesson_cap_chars,
                             rep, "lessons"),
        "raw_editions": prefilter(sorted((CAND / "raw_editions").glob("*.jsonl.gz")), keep, used_set(con, "raw_editions"),
                                  lambda r: zlib.crc32(r["text"][:300].encode()), None, ed_cap_chars, rep, "raw_editions"),
        "raw_latest": prefilter(sorted((CAND / "raw_latest").glob("*.jsonl.gz")), keep, used_set(con, "raw_latest"),
                                lambda r: zlib.crc32(r["text"][:200].encode()), None, None, rep, "raw_latest"),
    }
    for kind in pools:
        print(kind, rep["prefilter"][kind], flush=True)
    rep["candidates"] = {k: len(v) for k, v in pools.items()}
    used_h = used_set(con, "hier")
    hier = [h for h in hier_items(con, core, max(500, int(a.budget * SHARE["hierarchy"] / 120)), rnd)
            if f"{h['lex_id']}|{h['items'][0]['ans'][:60]}" not in used_h]
    for r in pools["lessons"] + hier:
        r["_t"] = lesson_text(r)
    for r in pools["raw_latest"] + pools["raw_editions"]:
        r["_t"] = r["text"]
    ratios = {"raw_latest": ratio_by(tok, pools["raw_latest"], lambda r: (r["type"], r["lang"])),
              "raw_editions": ratio_by(tok, pools["raw_editions"], lambda r: r["lang"]),
              "lessons": ratio_by(tok, pools["lessons"] + hier, lambda r: r["lang"])}
    rep["chars_per_token_measured"] = {k: {str(kk): round(v, 2) for kk, v in d.items()} for k, d in ratios.items()}

    def est(kind, r):
        d = ratios[kind]
        k = (r["type"], r["lang"]) if kind == "raw_latest" else r["lang"]
        return len(r["_t"]) / d.get(k, min(d.values()) if d else 2.5)

    prio = {t: i for i, t in enumerate(["constitution", "code", "law", "chamber", "pf", "pq", "f", "vmq", "ministry", "other"])}
    keyf = {"raw_latest": lambda r: (prio.get(r["type"], 9), r["_p"]), "raw_editions": lambda r: r["_p"], "lessons": lambda r: r["_p"],
            "hierarchy": lambda r: 0}
    sel: dict[str, list] = {}
    rep["pool_est_tokens"], rep["selected_est_tokens"] = {}, {}
    for kind, pool in (("raw_latest", pools["raw_latest"]), ("raw_editions", pools["raw_editions"]), ("lessons", pools["lessons"]), ("hierarchy", hier)):
        ek = "lessons" if kind == "hierarchy" else kind
        cap = a.budget * SHARE[kind]
        over = OVERSHOOT if kind in ("lessons", "hierarchy") else 1.0
        tot, chosen = 0.0, []
        ordered = sorted(pool, key=keyf[kind])
        if kind == "lessons":   # Uzbek first: per-script token caps, then the unused remainder is filled from any script
            lcap, ltot, taken = {k: cap * over * v for k, v in LESSON_LANG_SHARE.items()}, Counter(), set()
            for i, r in enumerate(ordered):
                t = est(ek, r)
                if ltot[r["lang"]] + t <= lcap.get(r["lang"], 0):
                    chosen.append(r)
                    ltot[r["lang"]] += t
                    taken.add(i)
            tot = sum(ltot.values())
            for i, r in enumerate(ordered):
                t = est(ek, r)
                if i not in taken and tot + t <= cap * over:
                    chosen.append(r)
                    tot += t
            ordered = []
        for r in ordered:
            t = est(ek, r)
            if tot + t > cap * over:
                continue
            chosen.append(r)
            tot += t
        if kind in ("lessons", "hierarchy"):   # shares are measured on the final set: enforce, trim to the cap, enforce again
            chosen = enforce(chosen, rep)
            for r in chosen:
                r["_t"] = lesson_text(r)
            while chosen:
                tot = sum(est(ek, r) for r in chosen)
                if tot <= cap:
                    break
                chosen = chosen[: max(1, int(len(chosen) * cap / tot * 0.995))]
            chosen = enforce(chosen, rep)
            for r in chosen:
                r["_t"] = lesson_text(r)
            tot = sum(est(ek, r) for r in chosen)
        sel[kind] = chosen
        rep["selected_est_tokens"][kind] = round(tot)
        rep["pool_est_tokens"][kind] = round(sum(est(ek, r) for r in pool))
    rep["enforce_drops"] = dict(rep.get("enforce_drops", {}))
    # replay: mix_pilot (web + instr) first, then replay_extra.jsonl.gz if the pilot pool is too small
    replay, pool = [], []
    used_rep = used_set(con, "replay")
    srcs = []
    if MIX_PILOT.exists():
        srcs.append(("mix_pilot", (json.loads(line) for line in MIX_PILOT.open(encoding="utf-8"))))
    if REPLAY_EXTRA.exists():
        srcs.append(("replay_extra", _lines(REPLAY_EXTRA)))
    for name, it in srcs:
        for r in it:
            if r.get("kind") in {"web", "instr"} and replay_key(r) not in used_rep:
                r["_src"] = name
                pool.append(r)
    random.Random(SEED + 3 + rnd).shuffle(pool)
    pool.sort(key=lambda r: r["_src"] != "mix_pilot")

    def rtok(r):
        return len(text_of_replay(r)) / (2.6 if r["kind"] == "web" else 4.0)

    cap, tot = a.budget * SHARE["replay"], 0.0
    for r in pool:
        t = rtok(r)
        if tot + t > cap:
            continue
        replay.append(r)
        tot += t
    rep["replay_pool_rows"] = len(pool)
    rep["replay_pool_est_tokens"] = round(sum(rtok(r) for r in pool))
    rep["selected_est_tokens"]["replay"] = round(tot)
    # exact tokens + write
    final = []
    for kind, rows in sel.items():
        for r in rows:
            final.append({"kind": "law", "src": kind, "act": r["act"], "lang": r["lang"], "text": r["_t"]})
    for r in replay:
        final.append({**{k: v for k, v in r.items() if k != "_src"}, "src": "replay", "replay_from": r["_src"]})
    random.Random(SEED + 11 + rnd).shuffle(final)
    texts = [text_of_replay(x) for x in final]
    tokens, n_by, tok_kind = Counter(), Counter(), Counter()
    for i in range(0, len(final), 512):
        enc = tok.encode_batch(texts[i:i + 512], add_special_tokens=False)
        for x, e in zip(final[i:i + 512], enc, strict=True):
            n = len(e.ids) + 1
            tokens[x["src"]] += n
            n_by[x["src"]] += 1
            tok_kind[f"{x['src']}:{x['replay_from']}:{x['kind']}" if x["src"] == "replay" else f"{x['src']}:{x['lang']}"] += n
    OUT.mkdir(parents=True, exist_ok=True)
    per = 4000
    files = []
    for i in range(0, len(final), per):
        p = OUT / f"lawschool_v2-r{rnd:02d}-{i // per:04d}.jsonl.gz"
        _write(p, final[i:i + per])
        files.append(p.name)
    total = sum(tokens.values())
    # mark used (add-only) only after the shards are on disk
    con.executemany("INSERT OR IGNORE INTO used VALUES (?,?)",
                    [("lessons", row_key("lessons", r)) for r in sel["lessons"]]
                    + [("raw_editions", row_key("raw_editions", r)) for r in sel["raw_editions"]]
                    + [("raw_latest", row_key("raw_latest", r)) for r in sel["raw_latest"]]
                    + [("hier", f"{r['lex_id']}|{r['items'][0]['ans'][:60]}") for r in sel["hierarchy"]]
                    + [("replay", replay_key(r)) for r in replay])
    con.execute("INSERT INTO rounds VALUES (?,?,?,?)", (rnd, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), a.budget, total))
    con.commit()
    rep["final"] = {"rows": dict(n_by), "tokens_exact": dict(tokens), "tokens_total": total, "shards": len(files),
                    "share": {k: round(v / total, 3) for k, v in tokens.items()} if total else {}}
    rep["tokens_by_source_lang"] = dict(sorted(tok_kind.items()))
    items = [(it, r["lang"]) for r in sel["lessons"] + sel["hierarchy"] for it in r["items"]]
    rep["items_total"] = len(items)
    rep["items_per_type"] = dict(Counter(i["t"] for i, _ in items))
    ti: Counter = Counter()   # exact tokens per lesson item type on a sample (items encoded alone)
    sample = items[::max(1, len(items) // 40000)]
    for i in range(0, len(sample), 1024):
        enc = tok.encode_batch([x[0]["txt"] for x in sample[i:i + 1024]], add_special_tokens=False)
        for (x, _), e in zip(sample[i:i + 1024], enc, strict=True):
            ti[x["t"]] += len(e.ids)
    tsum = sum(ti.values()) or 1
    rep["lesson_item_token_share_sampled"] = {k: round(v / tsum, 3) for k, v in sorted(ti.items())}
    rep["answer_balance"] = {f"{t}|{lg}": dict(Counter(i["cls"] for i, l2 in items if i["t"] == t and l2 == lg and i["cls"]))
                             for t in ("inforce", "tf", "hier") for lg in ("lat", "cyr", "ru")
                             if any(i["t"] == t and l2 == lg and i["cls"] for i, l2 in items)}
    rep["answer_balance_share_of_majority"] = {k: round(max(v.values()) / sum(v.values()), 3) for k, v in rep["answer_balance"].items() if len(v) >= 2}
    mt = {}
    for t in rep["items_per_type"]:
        c = Counter(i["tpl"] for i, _ in items if i["t"] == t)
        mt[t] = {"n_templates": len(c), "max_share": round(max(c.values()) / sum(c.values()), 4)}
    rep["template_max_share"] = mt
    ca = Counter(i["ans"] for i, _ in items if not i["cls"])
    rep["identical_answer_max_share"] = round(max(ca.values()) / len(items), 5) if ca else 0
    rep["top_act_char_share"] = {"lessons": top_share(sel["lessons"], lambda r: absid(r["act"]), lambda r: len(r["_t"])),
                                 "raw_editions": top_share(sel["raw_editions"], lambda r: absid(r["lex_id"]), lambda r: len(r["_t"]))}
    rep["leak_check_final"] = {"rows_with_excluded_article": sum(1 for k in ("lessons", "raw_editions", "raw_latest") for r in sel[k] if not keep(r))}
    rep["gpu_hours_estimate_this_round"] = {"tokens": total, "gpu_hours_at_620_tok_s": round(total / TOK_PER_SEC / 3600, 1), "label": "ESTIMATE"}
    rep["files"] = files
    mf = OUT / "manifest.json"
    cum = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {"rounds": []}
    cum["rounds"] = [r for r in cum["rounds"] if r.get("round") != rnd] + [rep]
    cum["tokens_total_all_rounds"] = sum(r["final"]["tokens_total"] for r in cum["rounds"])
    cum["shards_all_rounds"] = [f for r in cum["rounds"] for f in r["files"]]
    cum["gpu_hours_estimate"] = estimate() | {"cumulative_shards": {"tokens": cum["tokens_total_all_rounds"],
                                                                   "gpu_hours_at_620_tok_s": round(cum["tokens_total_all_rounds"] / TOK_PER_SEC / 3600, 1)}}
    mf.write_text(json.dumps(cum, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("round", "candidates", "prefilter", "pool_est_tokens", "selected_est_tokens", "final", "enforce_drops",
                                         "answer_balance_share_of_majority", "template_max_share", "identical_answer_max_share",
                                         "top_act_char_share", "leak_check_final")}, ensure_ascii=False, indent=1))


def cmd_replay_extra(a) -> None:
    """Needs pyarrow (the repo .venv): extra FineWeb-2 uzn_Latn + Tulu 3 rows for replay, none already in mix_pilot."""
    import glob

    import pyarrow.parquet as pq
    root = ROOT / "data" / "raw" / "replay"
    seen = {replay_key(json.loads(line)) for line in MIX_PILOT.open(encoding="utf-8")}
    rng = random.Random(SEED + 77)
    rows, wch, ich = [], 0, 0
    for f in sorted(glob.glob(str(root / "fineweb-2" / "data" / "uzn_Latn" / "train" / "*.parquet"))):
        for batch in pq.ParquetFile(f).iter_batches(batch_size=4000, columns=["text"]):
            for t in batch.column("text").to_pylist():
                if wch < a.web_chars and 300 <= len(t) <= 12000 and rng.random() < 0.3 and replay_key({"text": t}) not in seen:
                    rows.append({"kind": "web", "text": t})
                    wch += len(t)
    for f in sorted(glob.glob(str(root / "tulu-3-sft-mixture" / "data" / "*.parquet"))):
        for batch in pq.ParquetFile(f).iter_batches(batch_size=2000, columns=["messages", "source"]):
            for r in batch.to_pylist():
                if ich >= a.instr_chars or any(d in r["source"] for d in ("no_robots", "hard_coded")) or rng.random() > 0.3:
                    continue
                msgs = [{"role": m["role"], "content": m["content"] or ""} for m in r["messages"]]
                n = sum(len(m["content"]) for m in msgs)
                if 100 <= n <= 16000 and msgs[-1]["role"] == "assistant" and replay_key({"messages": msgs}) not in seen:
                    rows.append({"kind": "instr", "messages": msgs})
                    ich += n
    random.Random(SEED + 78).shuffle(rows)
    n = _write(REPLAY_EXTRA, rows)
    print(f"replay_extra: {n} rows, web {wch:,} chars, instr {ich:,} chars -> {REPLAY_EXTRA}")


def estimate() -> dict:
    return {f"{t // 1_000_000}M tokens": {"gpu_hours_at_620_tok_s": round(t / TOK_PER_SEC / 3600, 1), "gpu_days": round(t / TOK_PER_SEC / 86400, 2)}
            for t in (50_000_000, 100_000_000, 200_000_000)} | {"note": "ESTIMATE: tokens / 620 tok/s per GPU, one pass, no eval or restart time"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("candidates")
    c.add_argument("--n-core", type=int, default=N_CORE)
    c.add_argument("--views", type=int, default=2, help="distinct seeded lessons per article edition")
    c.set_defaults(fn=cmd_candidates)
    s = sp.add_parser("assemble")
    s.add_argument("--budget", type=int, default=50_000_000)
    s.set_defaults(fn=cmd_assemble)
    rx = sp.add_parser("replay-extra")
    rx.add_argument("--web-chars", type=int, default=60_000_000)
    rx.add_argument("--instr-chars", type=int, default=120_000_000)
    rx.set_defaults(fn=cmd_replay_extra)
    e = sp.add_parser("estimate")
    e.set_defaults(fn=lambda a: print(json.dumps(estimate(), indent=1)))
    args = ap.parse_args()
    args.fn(args)
