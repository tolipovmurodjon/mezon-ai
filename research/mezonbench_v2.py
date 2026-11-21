"""MezonBench v2: the HARD exam (v1 is saturated: base + tools 102/103, every question names act, article and date).

    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v2 build [--store PATH] [--out PATH]
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v2 score preds.jsonl [--bench PATH]
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v2 oracle [--bench PATH]
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v2 freeze          # writes data/bench/FROZEN_v2_0.json

Five families, gold only from the law store and the decision store (never a model), deterministic templates:
  ask_noaddr  a question a citizen or business would ask, NO act name, NO article number -> act + article
              (graded with mezonbench_where.grade logic)
  chain       a local decision cites act + article -> "was it in force on the decision date, and what did it say?"
              (ha + verbatim span >= 60 chars, or yo'q)
  dead_cite   the cited article had lost force on the decision date (50 %) or is live (50 %) -> ha / yo'q + date
  ru_cyr      v1-style in_force / hierarchy questions in Russian and Uzbek Cyrillic
  noaniq      the honest answer is "noaniq": act not in the store, date after the store's end, edition gap
Disjoint from v1 (every (act, path) of mezonbench_v1 / where_v1 / judge_q_r1 / internship tool calls) except
dead_cite and chain items on LSP art. 25 and Budget Code arts. 144/146: the only dead citations that exist are on
paths v1 already used, so those items carry "overlap_v1": true and the score table reports them apart ("strict").
v2 must never be trained on. Rebuild against a bigger store with --store (the 38-act build is v2.0).
"""

import argparse
import hashlib
import json
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from mezon.config import LAW_DB
from mezon.decisions.store import DecisionStore
from mezon.lawstore.store import LawStore
from mezon.rules.basis import cited_articles
from research import mezonbench as mb
from research import mezonbench_where as mw
from research.textnorm import fold

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench"
OUT = BENCH / "mezonbench_v2.jsonl"
FROZEN = BENCH / "FROZEN_v2_0.json"
OUT_V21 = BENCH / "mezonbench_v2_1.jsonl"  # public part of v2.1
PRIVATE_V21 = BENCH / "private" / "mezonbench_v2_1_private.jsonl"  # held-out 30 % per family: never shared, never trained on
FROZEN_V21 = BENCH / "FROZEN_v2_1.json"
PRIVATE_SHARE = 0.30
SEED = 20261121
TODAY = mb.TODAY
SIZES = {"ask_noaddr": 60, "chain": 60, "dead_cite": 60, "ru_cyr": 60, "cancel_trigger": 28,
         "conflict_pair": 60, "multi_hop": 60, "noaniq": 75}
GOLDEN = {"231-4-59-Q/24", "207-4-59-Q/24", "261-4-59-Q/24", "VII-3-1-5-77-K/25", "VII-4-12-5-77-K/25",
          "VI-76-4-10-146-K/24", "VI-76-21-10-146-K/24"}
USED_FILES = ["data/bench/mezonbench_v1.jsonl", "data/bench/mezonbench_where_v1.jsonl", "data/train/judge_q_r1.jsonl"]
INTERN_FILES = ["data/train/internship_sft.jsonl", "data/train/internship_val.jsonl", "data/train/internship_v1.jsonl"]
SYSTEM = ("Siz O'zbekiston qonunchiligi bo'yicha ekspertsiz. Qonunni ko'rsatilgan sanadagi tahriri bo'yicha javob "
          "bering. Bilmasangiz yoki asos topilmasa, \"noaniq\" deb yozing.")
SYSTEM_RU = ("Вы эксперт по законодательству Узбекистана. Отвечайте по редакции закона на указанную дату. "
             "Если данных нет, напишите \"noaniq\".")
SYSTEM_CYR = ("Сиз Ўзбекистон қонунчилиги бўйича экспертсиз. Қонунни кўрсатилган санадаги таҳрири бўйича жавоб "
              "беринг. Билмасангиз ёки асос топилмаса, \"noaniq\" деб ёзинг.")


def art_of(path: str) -> str:
    m = re.match(r"art:\d+(?:-\d+)?", path)
    return m.group(0) if m else path.split("/")[0]


# ---------------------------------------------------------------- Cyrillic (deterministic transliteration)

_L2C = [("o'", "ў"), ("O'", "Ў"), ("g'", "ғ"), ("G'", "Ғ"), ("sh", "ш"), ("Sh", "Ш"), ("ch", "ч"), ("Ch", "Ч"),
        ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е"), ("Yo", "Ё"), ("Yu", "Ю"), ("Ya", "Я"), ("Ye", "Е"),
        ("ng", "нг")]
_L1 = dict(zip("abdefghijklmnopqrstuvxyzABDEFGHIJKLMNOPQRSTUVXYZ",
               "абдефҳхижклмнопқрстувхйзАБДЕФҲХИЖКЛМНОПҚРСТУВХЙЗ", strict=True))
_L1.update({"c": "к", "C": "К", "w": "в", "W": "В", "e": "е", "E": "Э", "g": "г", "G": "Г", "h": "ҳ", "H": "Ҳ"})


def lat2cyr(text: str) -> str:
    t = re.sub(r"[ʻʼ‘’`´]", "'", text)
    out, i = [], 0
    while i < len(t):
        for src, dst in _L2C:
            if t.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            if t[i] in "eE" and (i == 0 or not (t[i - 1].isalpha() or t[i - 1] == "'")):
                out.append("э" if t[i] == "e" else "Э")
            else:
                out.append(_L1.get(t[i], t[i]))
            i += 1
    return "".join(out)


def evidence(sentence: str, num: str, width: int = 220) -> str | None:
    """The part of a preamble sentence that names article `num`, verbatim, always containing the number.
    "16-2" is also found as "16 2" or "16²" (pdftotext loses the superscript). The match that is followed by
    "modda" wins over a stray equal number elsewhere; None if the article cannot be located (item is dropped)."""
    a, _, b = num.partition("-")
    pat = rf"(?<![\d-]){a}\s?[-\s²]\s?{b}(?!\d)" if b else rf"(?<![\d-])(?<!\d\s){a}(?!-?\d)(?!\s?²)"
    hits = [m for m in re.finditer(pat, sentence) if "modda" in sentence[m.end(): m.end() + 40].lower()]
    if not hits:
        return None
    m = hits[0]
    start = max(0, m.start() - width)
    start = sentence.rfind(" ", 0, start) + 1 if start else 0
    end = min(len(sentence), m.end() + 50)
    if end < len(sentence):
        end = sentence.rfind(" ", 0, end) if sentence.rfind(" ", 0, end) > m.end() else end
    return ("…" if start else "") + sentence[start:end].strip() + ("…" if end < len(sentence) else "")


ANAPHOR = re.compile(r"\b(?:bunday|ushbu|mazkur|ana shu|shunday|o.sha|ular|ularning|uning)\b", re.IGNORECASE)
ADDRESS = re.compile(r"modda|moddasi|bandi|ilovasi|-son|O.?RQ|PQ-|PF-|VMQ|\d{4}\s*-?\s*yil", re.IGNORECASE)
ANAPHOR_OR_ADDRESS = re.compile(ADDRESS.pattern + "|" + ANAPHOR.pattern, re.IGNORECASE)  # v2.1: pronoun stems


def title_leak(title: str, question: str) -> bool:
    """True if the question repeats the act's own title words (it would name the act)."""
    words = {w for w in fold(title).split() if len(w) >= 5 and w not in mw.STOP}
    return len(words) >= 2 and sum(w in fold(question) for w in words) >= min(3, len(words))


def clip(text: str, n: int) -> str:
    """Cut at a word boundary (v2.0 cut norms mid-word)."""
    text = text.strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------- what v1 and the training sets already used

def load_used(law: LawStore) -> tuple[set, set, set]:
    """(exact (act, path) pairs, (act, article) pairs, registration numbers) already seen by v1 or training."""
    exact, arts, regs = set(), set(), set()
    for f in USED_FILES:
        p = ROOT / f
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            j = json.loads(line)
            if j.get("act") and j.get("path"):
                exact.add((j["act"], j["path"]))
                arts.add((j["act"], art_of(j["path"])))
    for f in INTERN_FILES:
        p = ROOT / f
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            j = json.loads(line)
            if (j.get("tags") or {}).get("reg"):
                regs.add(j["tags"]["reg"])
            for m in j.get("messages", []):
                for t in m.get("tool_calls") or []:
                    a = t["function"]["arguments"]
                    a = json.loads(a) if isinstance(a, str) else a
                    if a.get("act") and a.get("article"):
                        key = law.find_act(a["act"])
                        art = a["article"].strip()
                        num = re.match(r"(?:art:)?(\d+(?:-\d+)?)", art)
                        if key and num:
                            arts.add((key, f"art:{num.group(1)}"))
    return exact, arts, regs


def v1_hier_pairs() -> set:
    pairs = set()
    p = BENCH / "mezonbench_v1.jsonl"
    for line in p.open(encoding="utf-8"):
        j = json.loads(line)
        if j["family"] == "hierarchy":
            pairs.add(frozenset((j["a"], j["b"])))
    return pairs


# ---------------------------------------------------------------- generator

class Builder:
    def __init__(self, store: Path):
        self.law = LawStore(store)
        self.con = sqlite3.connect(f"{Path(store).resolve().as_uri()}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row
        self.acts = {r["act_key"]: dict(r) for r in self.con.execute("SELECT * FROM acts")}
        self.exact, self.arts, self.regs = load_used(self.law)
        self.rng = random.Random(SEED)
        self.items: list[dict] = []
        self.decisions = DecisionStore()

    def add(self, family: str, prompt: str, answer: str, system: str = SYSTEM, **meta) -> None:
        n = sum(i["family"] == family for i in self.items) + 1
        self.items.append({"id": f"{family}-{n:03d}", "family": family, "system": system, "prompt": prompt,
                           "answer": answer, **meta})

    def count(self, family: str) -> int:
        return sum(i["family"] == family for i in self.items)

    def art_exists(self, key: str, path: str) -> bool:
        return self.con.execute("SELECT 1 FROM units WHERE act_key=? AND path=? LIMIT 1", (key, path)).fetchone() is not None

    def article_text(self, key: str, art: str, on: str) -> str | None:
        """All units of one article as they read on `on`, joined; None if the article did not exist."""
        ed = self.law.edition_on(key, on)
        if ed is None:
            return None
        rows = self.con.execute(
            "SELECT text FROM units WHERE act_key=? AND (path=? OR path LIKE ?) AND seq_from<=? AND seq_to>=? "
            "ORDER BY id", (key, art, art + "/%", ed["seq"], ed["seq"])).fetchall()
        return " ".join(r["text"] for r in rows) if rows else None

    def lost_on(self, key: str, art: str, on: str) -> str | None:
        """Date the article lost force, if it had existed and was gone (for good) on `on`."""
        rows = self.con.execute("SELECT valid_to FROM units WHERE act_key=? AND path=?", (key, art)).fetchall()
        if not rows or any(r["valid_to"] is None for r in rows):
            return None
        last = max(r["valid_to"] for r in rows)
        return last if last <= on else None

    # ---- family 1
    def ask_noaddr(self) -> None:
        by_art: dict[tuple[str, str], str] = {}
        for u in self.con.execute("SELECT act_key, path, text FROM units WHERE valid_to IS NULL"):
            k = (u["act_key"], art_of(u["path"]))
            by_art[k] = by_art.get(k, "") + " " + mb.norm(u["text"])
        rows = self.con.execute("SELECT act_key, path, text FROM units WHERE valid_to IS NULL AND path LIKE 'art:%' "
                                "AND length(text) BETWEEN 90 AND 600").fetchall()
        self.rng.shuffle(rows)
        per_act, modal_seen = Counter(), Counter()
        leak = ANAPHOR_OR_ADDRESS
        for r in rows:
            if self.count("ask_noaddr") >= SIZES["ask_noaddr"]:
                break
            key, path = r["act_key"], r["path"]
            a = self.acts[key]
            if (key, path) in self.exact or (key, art_of(path)) in self.arts or not mb.unseen(key, path):
                continue
            if path.count("/") > 1 or per_act[key] >= 6 or re.search(r"[а-яА-Я]{4}", a["title"]):
                continue
            sents = [s.strip() for s in re.split(r"(?<=[.;:])\s+", r["text"]) if 70 <= len(s.strip()) <= 300]
            sents = [s for s in sents if not leak.search(s) and not re.search(r"[а-яА-Я]{4}", s)]
            if not sents:
                continue
            self.rng.shuffle(sents)
            for s in sents:
                kind, stem = self.modal(s.rstrip(".;: "))
                if (len(stem) >= 35 and sum(mb.norm(stem) in v for v in by_art.values()) == 1
                        and not title_leak(a["title"], stem)):
                    break
            else:
                continue
            art = art_of(path).split(":")[1]
            words = stem.split()
            lead_word = stem if len(words) > 1 and words[1][:1].isupper() else stem[0].lower() + stem[1:]
            stem_txt = re.sub(r"[ʻʼ‘’`´]", "'", lead_word)
            lead = ["Savolim bor: ", "Tadbirkor sifatida so'rayman: ", "Fuqaro sifatida bilmoqchiman: ",
                    "Menga tushuntiring: ", "Hokimlikka murojaat qilishdan oldin aniqlamoqchiman: "][modal_seen.total() % 5]
            modal_seen[kind] += 1
            q = {"taqiq": f"{lead}{stem_txt} taqiqlanganmi? Bu qoida qaysi hujjatning qaysi moddasida?",
                 "huquq": f"{lead}{stem_txt} huquqiga egami? Bu qoida qaysi hujjatning qaysi moddasida?",
                 "majburiyat": f"{lead}{stem_txt} majburmi? Bu qoida qaysi hujjatning qaysi moddasida?",
                 "qoida": f"{lead}{stem_txt} — deb yozilgan qoida qaysi hujjatning qaysi moddasida?"}[kind]
            self.add("ask_noaddr", q + "\nJavob shakli: <hujjat nomi yoki raqami>, <N>-modda.", f"{mb.act_name(a)} "
                     f"{mb.human_path(art_of(path))}", system=mw.SYSTEM, act=key, path=path, article=art,
                     act_number=a["number"] or "", act_title=a["title"], date=TODAY, kind=kind, recent=False)
            per_act[key] += 1

    @staticmethod
    def modal(s: str) -> tuple[str, str]:
        f = s
        # v2.1: only "taqiq" yields a grammatical question; "huquq" and "majburiyat" cut stems into nonsense
        for kind, rx in (("taqiq", r"\b(taqiqlanadi|mumkin emas|man etiladi|ruxsat etilmaydi|yoʻl qoʻyilmaydi)"),):
            m = re.search(rx, f, re.IGNORECASE)
            if m and m.start() >= 35:
                return kind, f[:m.start()].rstrip(" ,;:-—")
        return "qoida", f

    # ---- families 2 and 3
    def decision_pool(self) -> tuple[list, list]:
        live, dead = [], []
        con = sqlite3.connect(ROOT / "data" / "store" / "decisions.sqlite")
        for did, reg in con.execute("SELECT id, reg_number FROM decisions WHERE role='adopted' AND text IS NOT NULL "
                                    "AND length(text) > 200 AND adopted IS NOT NULL"):
            if reg in self.regs or reg in GOLDEN:
                continue
            d = self.decisions.get(did)
            seen = set()
            for key, path, sentence in cited_articles(d["text"], exists=self.art_exists):
                on = d["adopted"]
                if key not in self.acts or self.law.edition_gap(key, on) or (key, path) in seen:
                    continue
                ever = self.con.execute("SELECT 1 FROM units WHERE act_key=? AND path=?", (key, path)).fetchone()
                if not ever:
                    continue
                seen.add((key, path))
                num = path.split(":")[1]
                ev = evidence(sentence, num)
                if ev is None:
                    continue
                rec = {"d": d, "key": key, "path": path, "ev": ev, "num": num}
                if self.law.get_unit(key, path, on):
                    live.append(rec)
                elif self.lost_on(key, path, on):
                    rec["lost"] = self.lost_on(key, path, on)
                    dead.append(rec)
        return live, dead

    def decision_prompt(self, rec: dict, tail: str) -> str:
        d, a = rec["d"], self.acts[rec["key"]]
        ev = rec["ev"]
        body = d["body"] if d["body"] and len(d["body"]) <= 90 else "mahalliy organ"  # some bodies hold a title
        return (f"Qaror {d['reg_number']} ({body}, {d['adopted']} da qabul qilingan) "
                f"preambulasida shunday deyilgan:\n«{ev}»\nShu yerda ko'rsatilgan {mb.act_name(a)} "
                f"{rec['num']}-modda {tail}")

    def chain_and_dead(self) -> None:
        live, dead = self.decision_pool()
        self.rng.shuffle(live)
        self.rng.shuffle(dead)
        used_dec: set[str] = set()
        # dead_cite: dead half first (gives its date window), live half drawn from the same window and acts
        n_dead = SIZES["dead_cite"] // 2
        picked = []
        for rec in dead:
            if len(picked) >= n_dead:
                break
            if rec["d"]["reg_number"] in used_dec:
                continue
            used_dec.add(rec["d"]["reg_number"])
            picked.append(rec)
        lo = min((r["d"]["adopted"] for r in picked), default="2024-10-19")
        pool = [r for r in live if r["d"]["adopted"] >= lo and r["key"] in {p["key"] for p in picked}
                and (r["key"], r["path"]) not in self.exact]
        per_art, items = Counter(), []
        for rec in pool:
            if len(items) >= SIZES["dead_cite"] - len(picked):
                break
            if rec["d"]["reg_number"] in used_dec or per_art[(rec["key"], rec["path"])] >= 3:
                continue
            used_dec.add(rec["d"]["reg_number"])
            per_art[(rec["key"], rec["path"])] += 1
            items.append(rec)
        allitems = picked + items
        self.rng.shuffle(allitems)
        for rec in allitems:
            is_dead = "lost" in rec
            self.add("dead_cite", self.decision_prompt(
                rec, "qaror sanasida kuchda bo'lganmi? Faqat \"ha\" yoki \"yo'q\" deb javob bering; \"yo'q\" bo'lsa, "
                     "modda qaysi sanada kuchini yoʻqotganini YYYY-MM-DD shaklida ham yozing."),
                "yo'q" if is_dead else "ha", reg=rec["d"]["reg_number"], act=rec["key"], path=rec["path"],
                verdict="yo'q" if is_dead else "ha", gold_date=rec.get("lost"), date=rec["d"]["adopted"],
                overlap_v1=(rec["key"], rec["path"]) in self.exact, recent=rec["d"]["adopted"] >= mb.RECENT)
        # chain: 30 ha (with the verbatim text on the decision date) and 30 yo'q (dead citations left over)
        half = SIZES["chain"] // 2
        for rec in dead:
            if self.count("chain") >= half or rec["d"]["reg_number"] in used_dec:
                continue
            used_dec.add(rec["d"]["reg_number"])
            self.add_chain(rec, False)
        per_art = Counter()
        amended = [r for r in live if r["d"]["reg_number"] not in used_dec and (r["key"], r["path"]) not in self.exact]
        amended.sort(key=lambda r: not self.amended_since(r))  # amended articles first: today's text is a trap
        want = SIZES["chain"] - self.count("chain")
        batch = []
        for rec in amended:
            if len(batch) >= want:
                break
            text = self.article_text(rec["key"], rec["path"], rec["d"]["adopted"])
            if not text or len(mb.norm(text)) < 60 or per_art[(rec["key"], rec["path"])] >= 3:
                continue
            per_art[(rec["key"], rec["path"])] += 1
            batch.append(rec)
        for rec in batch:
            self.add_chain(rec, True)
        # shuffle chain order so ha / yo'q are interleaved, then renumber
        chain = [i for i in self.items if i["family"] == "chain"]
        rest = [i for i in self.items if i["family"] != "chain"]
        self.rng.shuffle(chain)
        for n, it in enumerate(chain, 1):
            it["id"] = f"chain-{n:03d}"
        self.items = rest + chain

    def amended_since(self, rec: dict) -> bool:
        then = self.article_text(rec["key"], rec["path"], rec["d"]["adopted"])
        now = self.article_text(rec["key"], rec["path"], TODAY)
        return bool(then and now and mb.norm(then) != mb.norm(now))

    def add_chain(self, rec: dict, live: bool) -> None:
        on = rec["d"]["adopted"]
        gold = self.article_text(rec["key"], rec["path"], on) if live else None
        tail = ("qaror sanasida amalda bo'lganmi? Agar ha bo'lsa, o'sha sanadagi matnidan kamida 60 belgini aynan "
                "(so'zma-so'z) keltiring; yo'q bo'lsa \"yo'q\" deb yozing.")
        self.add("chain", self.decision_prompt(rec, tail), gold if live else "yo'q", reg=rec["d"]["reg_number"],
                 act=rec["key"], path=rec["path"], verdict="ha" if live else "yo'q", date=on,
                 amended_since=self.amended_since(rec) if live else None,
                 overlap_v1=(rec["key"], rec["path"]) in self.exact, recent=on >= mb.RECENT)

    # ---- family 4
    def ru_cyr(self) -> None:
        units = self.con.execute("SELECT act_key, path, valid_from, valid_to FROM units WHERE length(text) >= 80 "
                                 "AND path NOT LIKE '%preamble%' ORDER BY id").fetchall()
        by_path = defaultdict(list)
        for u in units:
            by_path[(u["act_key"], u["path"])].append(u)
        yes, no = [], []
        for (key, path), rows in sorted(by_path.items()):
            if (key, path) in self.exact or (key, art_of(path)) in self.arts or re.search(r"[а-я]{4}", self.acts[key]["title"]):
                continue
            rows.sort(key=lambda r: r["valid_from"])
            eds = self.law.editions(key)
            first_ed = eds[0]["valid_from"] if eds else None
            yes.append((rows[0], "in"))
            if first_ed and rows[0]["valid_from"] > first_ed:
                no.append((rows[0], "before"))
            if rows[-1]["valid_to"] and rows[-1]["valid_to"] < TODAY:
                no.append((rows[-1], "after"))
        self.rng.shuffle(yes)
        self.rng.shuffle(no)
        n_hier = 20
        per_lang: Counter = Counter()
        for pool, want in ((yes, "ha"), (no, "yo'q")):
            n = 0
            for r, where in pool:
                if n >= (SIZES["ru_cyr"] - n_hier) // 2:
                    break
                key = r["act_key"]
                on = None
                for _ in range(6):
                    if where == "in":
                        d = mb.rand_date(self.rng, r["valid_from"], r["valid_to"])
                    elif where == "before":
                        d = mb.rand_date(self.rng, self.law.editions(key)[0]["valid_from"], r["valid_from"])
                    else:
                        d = mb.rand_date(self.rng, r["valid_to"], None)
                    if d and not self.law.edition_gap(key, d) and                             (self.law.get_unit(key, r["path"], d) is not None) == (want == "ha"):
                        on = d
                        break
                if not on:
                    continue
                lang = ("ru", "uzcyr")[sum(per_lang.values()) % 2]
                per_lang[lang] += 1
                self.add("ru_cyr", *self.in_force_text(lang, key, r["path"], on, want), lang=lang, task="in_force",
                         act=key, path=r["path"], verdict=want, date=on, recent=on >= mb.RECENT, case=where)
                n += 1
        prev, keys = v1_hier_pairs(), sorted(self.acts)
        tries = 0
        while sum(i.get("task") == "hierarchy" for i in self.items) < n_hier and tries < 5000:
            tries += 1
            x, y = self.rng.sample(keys, 2)
            ax, ay = self.acts[x], self.acts[y]
            if (mb.RANK[ax["type"]] == mb.RANK[ay["type"]] or frozenset((x, y)) in prev
                    or re.search(r"[а-я]{4}", ax["title"] + ay["title"])):
                continue
            prev.add(frozenset((x, y)))
            win = "A" if mb.RANK[ax["type"]] > mb.RANK[ay["type"]] else "B"
            lang = ("ru", "uzcyr")[sum(per_lang.values()) % 2]
            per_lang[lang] += 1
            on = max(ax["adopted"] or "2000-01-01", ay["adopted"] or "2000-01-01")
            self.add("ru_cyr", *self.hier_text(lang, ax, ay, win), lang=lang, task="hierarchy", a=x, b=y,
                     verdict=win, date=on, recent=False)
        ru = [i for i in self.items if i["family"] == "ru_cyr"]
        rest = [i for i in self.items if i["family"] != "ru_cyr"]
        self.rng.shuffle(ru)
        for n, it in enumerate(ru, 1):
            it["id"] = f"ru_cyr-{n:03d}"
        self.items = rest + ru

    def in_force_text(self, lang: str, key: str, path: str, on: str, want: str):
        a = self.acts[key]
        if lang == "ru":
            words = {"art": "статья", "part": "часть", "cl": "пункт", "annex": "приложение", "ch": "глава",
                     "sec": "раздел", "sub": "подпункт"}
            hp = " ".join(f"{words.get(p.split(':')[0], p.split(':')[0])} {p.split(':')[1]}" for p in path.split("/"))
            q = (f"{mb.act_name(a)}, {hp}: действовала ли эта норма на {on} (существовала ли она под этим номером)? "
                 f"Ответьте только «да» или «нет».")
            return q, ("да" if want == "ha" else "нет"), SYSTEM_RU
        q = (f"{mb.act_name(a)} {mb.human_path(path)} {on} куни амалда бўлганми (шу рақам билан мавжуд эдими)? "
             f"Фақат \"ҳа\" ёки \"йўқ\" деб жавоб беринг.")
        return lat2cyr(q), ("ҳа" if want == "ha" else "йўқ"), SYSTEM_CYR

    def hier_text(self, lang: str, ax: dict, ay: dict, win: str):
        if lang == "ru":
            q = (f"A) {mb.act_name(ax)}\nB) {mb.act_name(ay)}\nЕсли их нормы противоречат друг другу, какой акт "
                 f"имеет приоритет? Ответьте только A или B.")
            return q, win, SYSTEM_RU
        q = ("A) " + lat2cyr(mb.act_name(ax)) + "\nB) " + lat2cyr(mb.act_name(ay)) + "\nУларнинг нормалари "
             "бир-бирига зид бўлса, қайси бири устун туради? Фақат A ёки B деб жавоб беринг.")
        return q, win, SYSTEM_CYR

    # ---- family 5
    def noaniq(self) -> None:
        n = SIZES["noaniq"] // 3
        names = ["Mehnat kodeksi", "Fuqarolik kodeksi", "Jinoyat kodeksi", "Jinoyat-protsessual kodeksi",
                 "Oila kodeksi", "Bojxona kodeksi", "Ekologiya kodeksi", "Uy-joy kodeksi",
                 "Ma'muriy javobgarlik toʻgʻrisidagi kodeks", "Fuqarolik protsessual kodeksi",
                 "Iqtisodiy protsessual kodeksi", "Davlat xizmati toʻgʻrisidagi qonun",
                 "Korrupsiyaga qarshi kurashish toʻgʻrisidagi qonun", "Shaxsga doir maʼlumotlar toʻgʻrisidagi qonun",
                 "Elektron tijorat toʻgʻrisidagi qonun"]
        missing = [x for x in names if self.law.find_act(x) is None]
        out_items = []
        for i in range(n):
            if not missing:
                break
            nm = missing[i % len(missing)]
            on = mb.rand_date(self.rng, "2022-01-01", "2026-10-31")
            art = self.rng.randint(1, 15)
            out_items.append(((f"«{nm}» {art}-modda {on} holatida qanday edi? Matn boshidan kamida 60 belgini aynan "
                              f"(so'zma-so'z) keltiring."), on, "act_not_in_store", {"act_name": nm}))
        fut = []
        cand = self.con.execute("SELECT act_key, path FROM units WHERE valid_to IS NULL AND path LIKE 'art:%' "
                                "AND path NOT LIKE '%/%' AND length(text) >= 80").fetchall()
        cand = [r for r in cand if (r["act_key"], r["path"]) not in self.exact
                and (r["act_key"], art_of(r["path"])) not in self.arts]
        self.rng.shuffle(cand)
        for r in cand:
            if len(fut) >= n:
                break
            on = self.future_date()
            a = self.acts[r["act_key"]]
            if re.search(r"[а-я]{4}", a["title"]):
                continue
            fut.append(((f"{mb.act_name(a)} {mb.human_path(r['path'])} {on} kuni amalda bo'lganmi (shu raqam bilan "
                        f"mavjud edimi)? Faqat \"ha\" yoki \"yo'q\" deb javob bering."), on, "date_after_store_end",
                        {"act": r["act_key"], "path": r["path"]}))
        gap = []
        for key in sorted(self.acts):
            eds = self.law.editions(key)
            if not eds or eds[0]["seq"] != 0:
                continue
            for ed in eds[:1]:
                nxt = next((e for e in eds[1:]), None)
                if nxt and (mb.date.fromisoformat(nxt["valid_from"]) - mb.date.fromisoformat(ed["valid_from"])).days > 400:
                    on = mb.rand_date(self.rng, ed["valid_from"], nxt["valid_from"])
                    units = self.con.execute("SELECT path FROM units WHERE act_key=? AND seq_from<=0 AND seq_to>=0 "
                                             "AND path LIKE 'art:%' AND path NOT LIKE '%/%' AND length(text) >= 80 "
                                             "LIMIT 40", (key,)).fetchall()
                    units = [u for u in units if (key, u["path"]) not in self.exact]
                    if on and units and self.law.edition_gap(key, on):
                        for _ in range(3):
                            u = self.rng.choice(units)
                            gap.append(((f"{mb.act_name(self.acts[key])} {mb.human_path(u['path'])} {on} holatida "
                                        f"qanday edi? Matn boshidan kamida 60 belgini aynan (so'zma-so'z) keltiring."),
                                        on, "edition_gap", {"act": key, "path": u["path"]}))
        self.rng.shuffle(gap)
        gap = gap[:n]
        # top up the gap kind from the future kind if the store has too few gaps
        extra = []
        while len(out_items) + len(fut) + len(gap) + len(extra) < SIZES["noaniq"] and cand:
            r = self.rng.choice(cand)
            a = self.acts[r["act_key"]]
            on = self.future_date()
            extra.append(((f"{mb.act_name(a)} {mb.human_path(r['path'])} {on} holatida qanday edi? Matn boshidan "
                          f"kamida 60 belgini aynan (so'zma-so'z) keltiring."), on, "date_after_store_end",
                          {"act": r["act_key"], "path": r["path"]}))
        allitems = out_items + fut + gap + extra
        self.rng.shuffle(allitems)
        for prompt, on, why, meta in allitems:
            self.add("noaniq", prompt, "noaniq", verdict="noaniq", date=on, why=why, recent=on >= mb.RECENT, **meta)

    def future_date(self) -> str:
        return (mb.date(2026, 12, 1) + mb.timedelta(days=self.rng.randint(0, 395))).isoformat()

    # ---- family 6: what cancelled a real local decision (gold: the cancelling decision's own text + label)
    def cancel_trigger(self) -> None:
        con = sqlite3.connect(ROOT / "data" / "store" / "decisions.sqlite")
        classes = {"adliya representation": "A", "adliya letter": "A", "prosecutor protest": "B", "court ruling": "C",
                   "clean-up of outdated acts (PF-6075)": "D"}
        quota = {"A": 10, "B": 4, "C": 2, "D": 12}
        rows = con.execute("SELECT reg_number, adopted, trigger, cancelled_numbers FROM decisions WHERE "
                           "role='cancelling' AND text IS NOT NULL AND length(text) > 200 AND adopted IS NOT NULL "
                           "AND label IN ('POSITIVE','EXCLUDE')").fetchall()
        rows = sorted(rows, key=lambda r: (not r[3], r[0]))  # rows with a named cancelled act first
        got = Counter()
        picked = []
        for reg, adopted, trig, nums in rows:
            cls = classes.get(trig)
            if (not cls or got[cls] >= quota[cls] or reg in GOLDEN or reg in self.regs or len(reg) < 5
                    or len(self.decisions.by_reg(reg)) != 1):
                continue
            if nums and any(n in GOLDEN for n in re.split(r"[,;\s]+", nums)):
                continue
            got[cls] += 1
            picked.append((reg, adopted, cls, nums or ""))
        self.rng.shuffle(picked)
        for reg, adopted, cls, nums in picked:
            gold_nums = [n for n in re.split(r"[,;\s]+", nums) if n]
            ask = " va bekor qilingan qaror raqamini ham ko'rsating." if gold_nums else "."
            self.add("cancel_trigger",
                     f"Mahalliy qaror {reg} ({adopted}) boshqa qarorni bekor qilgan. Uning matnini o'qing: u qaysi "
                     f"asosda qabul qilingan?\nA) adliya organining taqdimnomasi yoki xati\nB) prokuror noroziligi\n"
                     f"C) sud qarori\nD) o'z ahamiyatini yo'qotgan hujjatlarni umumiy tozalash (PF-6075)\n"
                     f"Harfni yozing{ask}",
                     cls + (f", {gold_nums[0]}" if gold_nums else ""), reg=reg, verdict=cls, gold_numbers=gold_nums,
                     date=adopted, recent=adopted >= mb.RECENT)

    # ---- family 7: which of two real norms prevails (NLA art. 6 different force / art. 18 equal force, later wins)
    def conflict_pair(self) -> None:
        live, _dead = self.decision_pool()
        self.rng.shuffle(live)
        used = {i.get("reg") for i in self.items}
        per_art: Counter = Counter()
        n_local = 0
        for rec in live:
            if n_local >= SIZES["conflict_pair"] // 2:
                break
            a = self.acts[rec["key"]]
            if (rec["d"]["reg_number"] in used or mb.RANK.get(a["type"], 0) <= mb.RANK["local"]
                    or (rec["key"], rec["path"]) in self.exact):
                continue
            text = self.article_text(rec["key"], rec["path"], rec["d"]["adopted"])
            if not text or len(mb.norm(text)) < 60:
                continue
            if per_art[(rec["key"], rec["path"])] >= 6:
                continue
            used.add(rec["d"]["reg_number"])
            n_local += 1
            per_art[(rec["key"], rec["path"])] += 1
            hi = f"{mb.act_name(a)} {rec['num']}-modda: «{clip(text, 260)}»"
            body = rec["d"]["body"] if rec["d"]["body"] and len(rec["d"]["body"]) <= 90 else "Mahalliy organ"
            body = re.sub(r"\s*qarori\s*$", "", body, flags=re.IGNORECASE)
            lo = f"{body} qarori {rec['d']['reg_number']}: «{clip(rec['d']['title'] or '', 260)}»"
            hi_first = self.rng.random() < 0.5
            first, second = (hi, lo) if hi_first else (lo, hi)
            self.add("conflict_pair", self.conflict_prompt(first, second), f"{'A' if hi_first else 'B'}, 6-modda",
                     reg=rec["d"]["reg_number"], act=rec["key"], path=rec["path"],
                     verdict="A" if hi_first else "B", nla_article="6", rule="different_force",
                     date=rec["d"]["adopted"], recent=rec["d"]["adopted"] >= mb.RECENT)
        prev = v1_hier_pairs()
        # the real local decisions run out (few distinct live higher articles): top up with act pairs of different force
        keys = sorted(k for k, a in self.acts.items() if a["adopted"] and not re.search(r"[а-я]{4}", a["title"]))
        diff = [(x, y) for i, x in enumerate(keys) for y in keys[i + 1:]
                if mb.RANK[self.acts[x]["type"]] != mb.RANK[self.acts[y]["type"]] and frozenset((x, y)) not in prev]
        self.rng.shuffle(diff)
        for x, y in diff[: max(0, SIZES["conflict_pair"] // 2 - n_local)]:
            ax, ay = self.acts[x], self.acts[y]
            hi, lo = (x, y) if mb.RANK[ax["type"]] > mb.RANK[ay["type"]] else (y, x)
            hi_first = self.rng.random() < 0.5
            tag = {k: f"{mb.act_name(self.acts[k])} (qabul qilingan: {self.acts[k]['adopted']})" for k in (hi, lo)}
            first, second = (tag[hi], tag[lo]) if hi_first else (tag[lo], tag[hi])
            self.add("conflict_pair", self.conflict_prompt(first, second), f"{'A' if hi_first else 'B'}, 6-modda",
                     a=x, b=y, verdict="A" if hi_first else "B", nla_article="6", rule="different_force_acts",
                     date=max(ax["adopted"], ay["adopted"]), recent=False)
        pool = sorted(k for k, a in self.acts.items() if a["type"] in ("pf", "pq", "vmq") and a["adopted"]
                      and not re.search(r"[а-я]{4}", a["title"]))
        pairs = []
        for i, x in enumerate(pool):
            for y in pool[i + 1:]:
                ax, ay = self.acts[x], self.acts[y]
                gap = abs((mb.date.fromisoformat(ax["adopted"]) - mb.date.fromisoformat(ay["adopted"])).days)
                if mb.RANK[ax["type"]] == mb.RANK[ay["type"]] and frozenset((x, y)) not in prev and gap >= 30:
                    pairs.append((x, y))
        self.rng.shuffle(pairs)
        for x, y in pairs[: SIZES["conflict_pair"] // 2]:
            ax, ay = self.acts[x], self.acts[y]
            later = x if ax["adopted"] > ay["adopted"] else y
            first_is_x = self.rng.random() < 0.5
            f, s = (ax, ay) if first_is_x else (ay, ax)
            win = "A" if (later == x) == first_is_x else "B"
            self.add("conflict_pair",
                     self.conflict_prompt(f"{mb.act_name(f)} (qabul qilingan: {f['adopted']})",
                                          f"{mb.act_name(s)} (qabul qilingan: {s['adopted']})"),
                     f"{win}, 18-modda", a=x, b=y, verdict=win, nla_article="18", rule="equal_force_later",
                     date=max(ax["adopted"], ay["adopted"]), recent=False)
        self.shuffle_family("conflict_pair")

    def shuffle_family(self, fam: str) -> None:
        mine = [i for i in self.items if i["family"] == fam]
        rest = [i for i in self.items if i["family"] != fam]
        self.rng.shuffle(mine)
        for n, it in enumerate(mine, 1):
            it["id"] = f"{fam}-{n:03d}"
        self.items = rest + mine

    @staticmethod
    def conflict_prompt(a: str, b: str) -> str:
        return (f"A) {a}\nB) {b}\nFaraz qiling, bu ikki normaning mazmuni bir masalada bir-biriga zid bo'lsa, qaysi biri ustun "
                f"turadi? Harfni va \"Normativ-huquqiy hujjatlar to'g'risida\"gi Qonunning qaysi moddasi asosida "
                f"ekanini yozing (masalan: A, N-modda).")

    # ---- family 8: decision -> cited article -> its amendment -> which wording applied on the decision date
    def multi_hop(self) -> None:
        live, _dead = self.decision_pool()
        self.rng.shuffle(live)
        used = {i.get("reg") for i in self.items}
        got = Counter()
        per_path: Counter = Counter()
        want = SIZES["multi_hop"] // 2
        sql = ("SELECT path, effective_date, old_text, new_text FROM change_log WHERE act_key=? AND "
               "change_type='changed' AND (path=? OR path LIKE ?) AND length(old_text) > 40 AND length(new_text) > 40")
        for rec in live:
            if sum(got.values()) >= SIZES["multi_hop"]:
                break
            on = rec["d"]["adopted"]
            if rec["d"]["reg_number"] in used:
                continue
            ch = [c for c in self.con.execute(sql, (rec["key"], rec["path"], rec["path"] + "/%"))
                  if 0 < abs((mb.date.fromisoformat(c["effective_date"]) - mb.date.fromisoformat(on)).days) <= 500
                  and mb.norm(c["old_text"]) != mb.norm(c["new_text"])]
            if not ch:
                continue
            c = ch[0]
            applied = "new" if on >= c["effective_date"] else "old"
            if got[applied] >= want or self.law.edition_gap(rec["key"], on) or per_path[(rec["key"], c["path"])] >= 5:
                continue
            gold_txt = c["new_text"] if applied == "new" else c["old_text"]
            now = self.law.get_unit(rec["key"], c["path"], on)
            if not now or mb.norm(now["text"]) != mb.norm(gold_txt):
                continue
            t_old, t_new = mb.diff_window(c["old_text"], c["new_text"])
            first_old = self.rng.random() < 0.5
            first, second = (t_old, t_new) if first_old else (t_new, t_old)
            letter = "A" if (applied == "old") == first_old else "B"
            a = self.acts[rec["key"]]
            used.add(rec["d"]["reg_number"])
            got[applied] += 1
            per_path[(rec["key"], c["path"])] += 1
            label = (f"o'zgargan joyi ({mb.human_path(c['path'].split('/', 1)[1])})" if "/" in c["path"]
                     else "matni o'zgartirilgan")
            self.add("multi_hop",
                     f"Qaror {rec['d']['reg_number']} ({on} da qabul qilingan) {mb.act_name(a)} {rec['num']}-moddasiga "
                     f"asoslanadi. Shu moddaning {label}; ikki tahrir:\n"
                     f"A) {first}\nB) {second}\nQaror qabul qilingan kuni qaysi tahrir amalda edi? Harfni va o'zgarish "
                     f"kuchga kirgan sanani YYYY-MM-DD shaklida yozing.",
                     f"{letter}, {c['effective_date']}", reg=rec["d"]["reg_number"], act=rec["key"], path=c["path"],
                     verdict=letter, gold_date=c["effective_date"], applied=applied, date=on, recent=on >= mb.RECENT,
                     overlap_v1=(rec["key"], c["path"]) in self.exact)
        self.shuffle_family("multi_hop")

    # ---- build
    def build(self) -> list[dict]:
        self.ask_noaddr()
        self.chain_and_dead()
        self.ru_cyr()
        self.cancel_trigger()
        self.conflict_pair()
        self.multi_hop()
        self.noaniq()
        return self.items


def stratum(item: dict) -> str:
    """What the gold looks like, so the private part keeps each family's answer mix."""
    if item["family"] == "ask_noaddr":
        return item.get("act", "-")
    return str(item.get("verdict") or item.get("task") or item.get("why") or "-")


def split_items(items: list[dict], share: float = PRIVATE_SHARE) -> tuple[list[dict], list[dict]]:
    """Seeded private hold-out: per family round(share * n) items, drawn from each gold stratum in proportion
    (largest remainder), ids untouched. Returns (public, private); each item gets "split"."""
    rng = random.Random(SEED + 1)
    private_ids: set[str] = set()
    for fam in SIZES:
        sub = [i for i in items if i["family"] == fam]
        if not sub:
            continue
        want = round(share * len(sub))
        strata = defaultdict(list)
        for it in sorted(sub, key=lambda x: x["id"]):
            strata[stratum(it)].append(it)
        quota = {k: len(v) * share for k, v in strata.items()}
        take = {k: int(q) for k, q in quota.items()}
        for k in sorted(quota, key=lambda k: (-(quota[k] - take[k]), k))[: want - sum(take.values())]:
            take[k] += 1
        for k, v in sorted(strata.items()):
            rng.shuffle(v)
            private_ids |= {x["id"] for x in v[: take[k]]}
    public = [{**i, "split": "public"} for i in items if i["id"] not in private_ids]
    private = [{**i, "split": "private"} for i in items if i["id"] in private_ids]
    return public, private


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def build(store: Path = LAW_DB, out: Path = OUT_V21, private: Path = PRIVATE_V21) -> None:
    """v2.1: build everything, hold out 30 % per family as private, write both parts."""
    items = Builder(store).build()
    public, held = split_items(items)
    write_jsonl(out, public)
    write_jsonl(private, held)
    c = Counter(i["family"] for i in items)
    print(f"{out}: {len(public)} public items {dict(Counter(i['family'] for i in public))}")
    print(f"{private}: {len(held)} private items {dict(Counter(i['family'] for i in held))}")
    ans = {fam: dict(Counter(i.get("verdict") or "-" for i in items if i["family"] == fam)) for fam in c}
    print(f"answers per family (all {len(items)}) {ans}")
    print(f"overlap_v1 items: {sum(bool(i.get('overlap_v1')) for i in items)}; noaniq share "
          f"{c['noaniq'] / len(items):.3f}")


# ---------------------------------------------------------------- grader (changing it = a new version)

_VERDICT = re.compile(r"(?<![a-z0-9])(ha|da|yes|yoq|net|no)(?![a-z0-9])")
_ISO = re.compile(r"(20\d\d|19\d\d)-(\d\d)-(\d\d)")
_DMY = re.compile(r"(\d{1,2})[./](\d{1,2})[./]((?:19|20)\d\d)")


def verdict_of(answer: str) -> str:
    m = _VERDICT.search(fold(answer or ""))
    if not m:
        return ""
    return "ha" if m.group(1) in ("ha", "da", "yes") else "yo'q"


def letter_of(answer: str) -> str:
    t = (answer or "").upper().replace("А", "A").replace("В", "B").replace("С", "C")
    m = re.search(r"\b([A-D])\b", t)
    return m.group(1) if m else ""


def dates_in(answer: str) -> set:
    out = {f"{m[1]}-{m[2]}-{m[3]}" for m in _ISO.finditer(answer or "")}
    out |= {f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" for m in _DMY.finditer(answer or "")}
    return out


def grade(item: dict, answer: str) -> str:
    """'right' | 'wrong' | 'abstain'. noaniq items: right iff the answer abstains."""
    a = (answer or "").strip()
    abstains = "noaniq" in fold(a)
    fam = item["family"]
    if fam == "noaniq":
        return "right" if abstains else "wrong"
    if abstains:
        return "abstain"
    if fam == "ask_noaddr":
        return mw.grade(item, a)
    if fam == "chain":
        if verdict_of(a) != item["verdict"]:
            return "wrong"
        if item["verdict"] == "yo'q":
            return "right"
        # the verdict word may come glued to the quote ("Ha. <text>"): try the answer with it cut off as well
        bare = re.sub(r"^\W*(?:ha|да|ҳа|yes)\b\W*", "", a, flags=re.IGNORECASE)
        probe = {"family": "lookup", "answer": item["answer"]}
        return "right" if "right" in (mb.grade(probe, a), mb.grade(probe, bare)) else "wrong"
    if fam == "dead_cite":
        if verdict_of(a) != item["verdict"]:
            return "wrong"
        if item["verdict"] == "ha":
            return "right"
        return "right" if item["gold_date"] in dates_in(a) else "wrong"
    if fam in ("cancel_trigger", "conflict_pair", "multi_hop"):
        if letter_of(a) != item["verdict"]:
            return "wrong"
        if fam == "cancel_trigger":
            nums = [re.sub(r"[^0-9a-z]", "", fold(n)) for n in item["gold_numbers"]]
            flat = re.sub(r"[^0-9a-z]", "", fold(a))
            return "right" if not nums or any(n in flat for n in nums) else "wrong"
        if fam == "conflict_pair":
            art = rf"(?<![\d-]){item['nla_article']}[\s-]*(modda|модда|статья|статьи)"
            return "right" if re.search(art, a.lower()) else "wrong"
        return "right" if item["gold_date"] in dates_in(a) else "wrong"
    if fam == "ru_cyr":
        if item["task"] == "hierarchy":
            m = re.search(r"\b([AB])\b", a.upper().replace("А", "A").replace("В", "B"))
            return "right" if m and m.group(1) == item["verdict"] else "wrong"
        return "right" if verdict_of(a) == item["verdict"] else "wrong"
    raise ValueError(fam)


def oracle_answer(item: dict) -> str:
    fam = item["family"]
    if fam == "chain" and item["verdict"] == "ha":
        return "Ha. " + item["answer"][:240]
    if fam == "dead_cite" and item["verdict"] == "yo'q":
        return f"yo'q, {item['gold_date']}"
    return item["answer"]


def load(path: Path = OUT) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_split(split: str = "both", public: Path = OUT_V21, private: Path = PRIVATE_V21) -> list[dict]:
    """v2.1 items: split is "public", "private" or "both" (private needs data/bench/private/ to exist)."""
    items = load(public) if split in ("public", "both") else []
    if split in ("private", "both"):
        items += load(private)
    return items


def baselines(items: list[dict]) -> dict:
    """Constant answers graded by the grader itself: best per family, and the noaniq-only line."""
    out = {}
    consts = ["ha", "yo'q", "A", "B", "C", "D", "noaniq"]
    total_best = 0
    for fam in SIZES:
        sub = [i for i in items if i["family"] == fam]
        scores = {c: sum(grade(i, c) == "right" for i in sub) for c in consts}
        best = max(scores, key=lambda c: scores[c])
        out[fam] = {"n": len(sub), "best_const": best, "right": scores[best], "acc": round(scores[best] / len(sub), 3),
                    "noaniq_only": round(scores["noaniq"] / len(sub), 3)}
        total_best += scores[best]
    out["ALL"] = {"n": len(items), "right": total_best, "acc": round(total_best / len(items), 3),
                  "noaniq_only": round(sum(grade(i, "noaniq") == "right" for i in items) / len(items), 3)}
    return out


def score(pred_path: str, bench: Path = OUT, split: str | None = None) -> dict:
    """split None: `bench` as is (v2.0). "public" | "private" | "both": the v2.1 files; the three ALL lines are
    always printed when the private part exists."""
    items = {i["id"]: i for i in (load_split(split) if split else load(bench))}
    preds = {}
    for x in Path(pred_path).read_text(encoding="utf-8").splitlines():
        if x.strip():
            j = json.loads(x)
            preds[j["id"]] = j.get("answer", "")
    table = defaultdict(lambda: Counter())
    shares = defaultdict(Counter)
    for iid, it in items.items():
        if iid not in preds:
            continue
        g = grade(it, preds[iid])
        subs = [it["family"], "ALL", "ALL:no_noaniq" if it["family"] != "noaniq" else None,
                f"{it['family']}:{it['task']}" if it.get("task") else None,
                f"{it['family']}:{it['lang']}" if it.get("lang") else None,
                f"{it['family']}:{it['why']}" if it.get("why") else None,
                f"{it['family']}:strict" if it["family"] in ("chain", "dead_cite") and not it.get("overlap_v1") else None,
                f"{it['family']}:{it['verdict']}" if it["family"] in ("chain", "dead_cite") else None,
                "chain:amended" if it["family"] == "chain" and it.get("amended_since") else None]
        for k in subs:
            if k:
                table[k][g] += 1
        shares[it["family"]]["noaniq" if "noaniq" in fold(preds[iid]) else (verdict_of(preds[iid]) or "other")
                             if it["family"] in ("chain", "dead_cite", "ru_cyr", "noaniq") else letter_of(preds[iid]) or "other"] += 1
    base = baselines([i for i in items.values() if i["id"] in preds])
    for fam, c in sorted(shares.items()):
        n = sum(c.values())
        top_n = c.most_common(1)[0][1]
        flag = "  <-- COLLAPSE?" if top_n / n > 0.65 and fam != "noaniq" else ""
        print(f"{fam:10s} answer shares {dict(c.most_common(4))} | always-best-constant {base[fam]['best_const']!r} "
              f"{base[fam]['acc']:.3f} | noaniq-only {base[fam]['noaniq_only']:.3f}{flag}")
    out = {}
    for key in sorted(table):
        t = table[key]
        n = sum(t.values())
        lo, hi = mb.wilson(t["right"], n)
        out[key] = {"n": n, "right": t["right"], "wrong": t["wrong"], "abstain": t["abstain"],
                    "acc": round(t["right"] / n, 3), "ci95": [round(lo, 3), round(hi, 3)]}
        print(f"{key:24} N={n:4}  right {t['right']:4}  wrong {t['wrong']:4}  abstain {t['abstain']:3}  "
              f"acc {out[key]['acc']:.3f}  95% CI {out[key]['ci95']}")
    print(f"BASELINES overall: best-constant-per-family {base['ALL']['acc']:.3f}, noaniq-only {base['ALL']['noaniq_only']:.3f}")
    if split:
        for part in ("public", "private", "both"):
            sub = [i for i in load_split(part) if i["id"] in preds]
            if sub:
                right = sum(grade(i, preds[i["id"]]) == "right" for i in sub)
                lo, hi = mb.wilson(right, len(sub))
                print(f"SPLIT {part:8s} N={len(sub):4}  right {right:4}  acc {right / len(sub):.3f}  95% CI "
                      f"[{lo:.3f}, {hi:.3f}]")
    return out


def oracle(bench: Path = OUT, split: str | None = None) -> dict:
    items = load_split(split) if split else load(bench)
    gold = Counter(grade(i, oracle_answer(i)) for i in items)
    print(f"oracle (gold answers) {split or bench.name}: {dict(gold)} of {len(items)}")
    base = baselines(items)
    for k, v in base.items():
        print(f"baseline {k:11s} N={v['n']:3d} best constant {v.get('best_const', '-')!r:9} acc {v['acc']:.3f}  "
              f"noaniq-only {v['noaniq_only']:.3f}")
    return {"oracle": dict(gold), "baselines": base}


# ---------------------------------------------------------------- freeze

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def freeze() -> None:
    items = load(OUT)
    man = {"frozen": "2026-11-21 Tashkent", "version": "v2.0 (38-act store)",
           "items": {OUT.name: {"n": len(items), "sha256_16": sha(OUT),
                                "families": dict(Counter(i["family"] for i in items))}},
           "code_sha256_16": {p: sha(ROOT / p) for p in ("research/mezonbench_v2.py", "research/mezonbench.py",
                                                       "research/mezonbench_where.py", "mezon/tools.py",
                                                       "mezon/lawstore/store.py")},
           "law_store_sha256_16": sha(LAW_DB),
           "decision_store_sha256_16": sha(ROOT / "data" / "store" / "decisions.sqlite"),
           "rules": "Never train on v2. Changing an item, the grader, a tool or the store = v2.1 and every model re-runs. "
                    "Rebuild on laws_full.sqlite = a different exam (v3), not v2.0."}
    FROZEN.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{FROZEN}: {man['items']}")


def freeze_v21() -> None:
    """Hashes of both v2.1 files, the grader (function source), the tools and the stores; v2.0 must be untouched."""
    import inspect

    v20 = json.loads(FROZEN.read_text(encoding="utf-8"))
    v20_ok = sha(OUT) == v20["items"][OUT.name]["sha256_16"]
    parts = {}
    for name, path in (("public", OUT_V21), ("private", PRIVATE_V21)):
        items = load(path)
        parts[path.name] = {"split": name, "n": len(items), "sha256_16": sha(path),
                            "families": dict(Counter(i["family"] for i in items))}
    grader_src = "".join(inspect.getsource(f) for f in (verdict_of, letter_of, dates_in, grade, oracle_answer,
                                                          baselines, score, load_split))
    man = {"frozen": "2026-11-21 Tashkent", "version": "v2.1 (38-act store; v2.0 items redrawn after generator fixes)",
           "items": parts,
           "grader_sha256_16": hashlib.sha256(grader_src.encode("utf-8")).hexdigest()[:16],
           "code_sha256_16": {p: sha(ROOT / p) for p in ("research/mezonbench_v2.py", "research/mezonbench.py",
                                                       "research/mezonbench_where.py", "mezon/tools.py",
                                                       "mezon/lawstore/store.py", "mezon/rules/basis.py")},
           "law_store_sha256_16": sha(LAW_DB),
           "decision_store_sha256_16": sha(ROOT / "data" / "store" / "decisions.sqlite"),
           "v2_0_files_untouched": v20_ok,
           "rules": "Never train on v2.1. The private part is never shared or shown to a model; it is scored only by "
                    "the grader. Changing an item, the grader, a tool or the store = v2.2 and every model re-runs. "
                    "Rebuild on laws_full.sqlite = a different exam (v3)."}
    FROZEN_V21.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{FROZEN_V21}: {parts} v2.0 untouched={v20_ok}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "score", "oracle", "freeze", "freeze21"])
    ap.add_argument("preds", nargs="?")
    ap.add_argument("--store", default=str(LAW_DB))
    ap.add_argument("--out", default=str(OUT_V21), help="build: public part")
    ap.add_argument("--private", default=str(PRIVATE_V21), help="build: private part")
    ap.add_argument("--bench", default=None, help="score/oracle on one file (v2.0 = data/bench/mezonbench_v2.jsonl)")
    ap.add_argument("--split", default="both", choices=["public", "private", "both"])
    a = ap.parse_args()
    if a.cmd == "build":
        build(Path(a.store), Path(a.out), Path(a.private))
    elif a.cmd == "score":
        score(a.preds, Path(a.bench) if a.bench else OUT, None if a.bench else a.split)
    elif a.cmd == "oracle":
        if a.bench:
            oracle(Path(a.bench))
        else:
            for part in ("public", "private", "both"):
                oracle(split=part)
    elif a.cmd == "freeze21":
        freeze_v21()
    else:
        freeze()


if __name__ == "__main__":
    main()
