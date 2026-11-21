"""Pilot A ("internship") data: tool-use SFT traces built by running the real tools, no model involved.

    .venv/Scripts/python.exe -X utf8 -m research.internship_data [--tulu data/train/_tulu_pick.jsonl]
        -> data/train/internship_sft.jsonl  (train)   data/train/internship_val.jsonl  (dev + OOD phrasing + exam-free val)

Design: docs/research/internship_rl_pilot.md section 1. Every example is {"kind", "family", "tools": bool, "messages"}:
assistant turns carry "reasoning_content" (short think), optional "tool_calls", and "content"; tool results are
{"role": "tool"} rows holding the JSON that mezon.tools.call really returned. Render with
research.internship_encode.encode_multi (the model's own chat template, loss on assistant spans only).

Exam hygiene: every (act, article) in mezonbench_v1_1 + mezonbench_where_v1 is excluded at ARTICLE level (a superset of
the exact-path rule), and a trace is dropped if any tool response touches one. Hierarchy pairs of the exam are excluded.
Memory: sqlite is streamed, only units of at most 1,000 characters are kept (so a tool response stays under ~1,500 chars).
"""

import argparse
import json
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from mezon import tools as T
from mezon.config import DECISIONS_DB, LAW_DB
from mezon.decisions.store import DecisionStore
from mezon.lawstore.store import LawStore
from research.mezonbench import RANK, SYSTEM, TODAY, act_name, diff_window, grade, human_path, norm, rand_date

ROOT = Path(__file__).resolve().parents[1]
BENCH = [ROOT / "data" / "bench" / "mezonbench_v1_1.jsonl", ROOT / "data" / "bench" / "mezonbench_where_v1.jsonl"]
OUT_TRAIN = ROOT / "data" / "train" / "internship_sft.jsonl"
OUT_VAL = ROOT / "data" / "train" / "internship_val.jsonl"
AUDIT_SYSTEM = ("Siz Mezon: hokim va Kengash qarorlarini qabul qilingan sanadagi qonun tahriri bilan tekshiradigan yordamchisiz. "
                "Faqat aynan iqtibos va modda bilan javob bering; asos topilmasa \"noaniq, ekspert kerak\" deng. "
                "Belgilangan qaror noqonuniy degani emas: yakuniy qarorni ekspert qabul qiladi.")
# golden cases and the acts that cancel them or are cited as cancelled: removed from every slice by registration number
GOLDEN = {"231-4-59-Q/24", "VII-3-1-5-77-K/25", "VI-76-4-10-146-K/24", "207-4-59-Q/24", "161-4-59-Q/23",
          "261-4-59-Q/24", "VII-4-12-5-77-K/25", "VI-76-21-10-146-K/24"}
MAX_UNIT_CHARS = 1000
MAX_RESP = 1500
AUDIT_CAP = 2600  # characters of get_decision output shown in a training trace
TARGET = {"lookup": 130, "flip": 130, "in_force": 130, "hierarchy": 50, "discovery": 80, "abstain": 70, "audit": 250}
VAL_SHARE = 0.08


def art_root(path: str) -> str:
    m = re.match(r"(art:\d+(?:-\d+)?|annex:\d+|[^/]+)", path)
    return m.group(1) if m else path


def load_exam() -> tuple[set, set]:
    """(act, article root) pairs and hierarchy act pairs of the frozen exam."""
    arts, pairs = set(), set()
    for p in BENCH:
        for line in p.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            it = json.loads(line)
            if "path" in it:
                arts.add((it["act"], art_root(it["path"])))
            if it.get("family") == "hierarchy":
                pairs.add(frozenset((it["a"], it["b"])))
    return arts, pairs


def load_exam_exact() -> set:
    """Exact (act, path) pairs of the frozen exam (the audit slice uses this, the rest uses article roots)."""
    out = set()
    for p in BENCH:
        for line in p.read_text(encoding="utf-8").split(chr(10)):
            if line.strip():
                it = json.loads(line)
                if "path" in it:
                    out.add((it["act"], it["path"]))
    return out


# ---------------------------------------------------------------------------------------------- think phrasing
OPEN = ["Savol sana va modda raqamiga bog'liq.", "Bu savolda tahrir sanasi hal qiluvchi.",
        "Javob berishdan oldin matnni bazadan olishim kerak.", "Moddaning o'sha kundagi tahririni ko'rib chiqaman.",
        "Xotiraga tayanmay, vositadan foydalanaman.", "Avval qonun bazasidan tekshiraman.",
        "Savol aniq sanaga qaratilgan.", "Qonun matni vaqt o'tishi bilan o'zgargan bo'lishi mumkin."]
CLOSE = ["Birinchi qadam shu.", "Keyin natijaga qarab qaror qilaman.", "Taxmin qilmayman.",
         "Natijani ko'rgach davom etaman.", "Shundan boshlayman.", "Aniq manba kerak."]
CLOSE_R = ["Shunga qarab javob beraman.", "Keyingi qadamni shu belgilaydi.", "Xulosa shu ma'lumotga tayanadi.",
           "Boshqa taxminga o'rin yo'q.", "Bu yetarli asos.", "Shuni hisobga olaman."]
OPEN_R = ["Natijani o'qiyman.", "Vosita javob qaytardi.", "Qaytgan ma'lumotga qarayman.", "Endi natija ma'lum.",
          "Bazadan javob keldi.", "Natijani tekshiraman.", "Ko'ramiz, vosita nima dedi.", "Javobni tahlil qilaman."]
PLAN = {
    "lookup": ["{s} {p} matnini {d} holatida so'rayman.", "Kerak: {s}, {p}, sana {d}. Matnni vosita bilan olaman.",
               "{d} dagi {p} ({s}) so'zma-so'z matni kerak."],
    "flip": ["Ikki tahrirdan qaysi biri {d} da amalda ekanini bazadagi matn bilan solishtiraman.",
             "{s}, {p}: {d} dagi haqiqiy matnni olib, A va B bilan taqqoslayman.",
             "Variantlarni xotirada emas, {d} dagi tahrir bo'yicha tanlayman."],
    "in_force": ["{p} ({s}) {d} da mavjud edimi, shuni tahrir bo'yicha tekshiraman.",
                 "Modda {d} kuni bor-yo'qligini aniqlash uchun o'sha sanadagi tahrirni so'rayman.",
                 "{d} dagi tahrirda {p} bormi, ko'raman."],
    "discovery": ["Hujjat nomi berilmagan, shuning uchun avval mavzu bo'yicha qidiraman.",
                  "{d} dagi kuchdagi normalar orasidan mavzuni qidiraman, keyin matnni o'qiyman.",
                  "Qidiruv orqali nomzod modda topaman, so'ng matnini tekshiraman."],
    "hierarchy": ["Yuridik kuch tartibi Normativ-huquqiy hujjatlar to'g'risidagi qonunning 6-moddasida belgilangan.",
                  "Ikki hujjatning turini solishtiraman: qaysi biri yuqori kuchga ega."],
    "audit": ["Qaror matnini registratsiya raqami bo'yicha olaman, so'ng asoslarni tekshiraman.",
              "Avval qarorning o'zini o'qiyman; xulosa matnga tayanishi kerak."],
    "abstain": ["{s}, {p} uchun {d} dagi matnni so'rayman.", "{d} sanasidagi tahrirni bazadan olaman.",
                "Avval bazada bu hujjat bor-yo'qligini ko'raman."],
    "recover": ["{s}, {p} matnini {d} holatida so'rayman.", "Moddani to'g'ridan-to'g'ri so'rab ko'raman."],
}
READ = {
    "found": ["Tahrir {e}, {vf} dan kuchda; matn mavjud.", "{p} matni {e} tahririda topildi ({vf} dan).",
              "Matn qaytdi: tahrir {e}, kuchga kirgan sana {vf}."],
    "missing_path": ["{d} dagi tahrirda {p} yo'q.", "Bu sanadagi tahrirda bunday modda topilmadi.",
                     "Vosita xato qaytardi: {p} bu tahrirda yo'q."],
    "no_act": ["Vosita hujjatni bazadan topmadi.", "Hujjat bazada yo'q, demak matn ham yo'q.",
               "Bu hujjat qonun bazasida mavjud emas."],
    "no_edition": ["{d} sanasida hujjat hali mavjud emas edi.", "Hujjatning birinchi tahriri bu sanadan keyin.",
                   "Vosita: {d} da hujjat yo'q edi."],
    "editions": ["Tahrirlar ro'yxati: {n} ta, birinchisi {first}.", "Saqlangan tahrirlar: {n} ta, so'nggisi {last}.",
                 "Ro'yxatda {n} ta tahrir bor."],
    "hits": ["Qidiruv {n} ta natija berdi; birinchisi mavzuga mos.", "Eng yaxshi natija {p} ({s}).",
             "Nomzod topildi: {s}, {p}."],
    "verified": ["Iqtibos tahrirda so'zma-so'z tasdiqlandi.", "verify_quote ok qaytardi."],
    "decision": ["Qaror matni olindi: {n} ta band.", "Qaror o'qildi, bandlar soni {n}."],
}


MID_P = ["Taxmin emas, bazadagi matn dalil bo'ladi.", "Faqat vosita qaytargan ma'lumotga tayanaman.",
         "Javob manbaga bog'langan bo'lishi kerak.", "Sana noto'g'ri bo'lsa, javob ham noto'g'ri chiqadi.",
         "Bu yerda xotira emas, tekshiruv hal qiladi.", "Dalilsiz javob berishdan ko'ra tekshirgan afzal."]
MID_R = ["Xulosani faqat shu natijaga asoslayman.", "Bu ma'lumot savolga bevosita taalluqli.",
         "Natijadan tashqariga chiqib o'ylab topmayman.", "Savol shartlarini natija bilan solishtiraman.",
         "Javob bazadagi yozuvdan kelib chiqadi.", "Qaytgan matn va sanalarni e'tiborga olaman."]


class Think:
    """Composes short thinks (15-60 words) from slot pools; counts each (opener, body, closer) for the 3 % gate."""

    def __init__(self, rng: random.Random):
        self.rng, self.used = rng, {"plan": Counter(), "read": Counter()}

    def _make(self, kind: str, opens, bodies, closes, vals: dict) -> str:
        mids = MID_P if kind == "plan" else MID_R
        for _ in range(50):
            o, b, c, m = (self.rng.randrange(len(opens)), self.rng.randrange(len(bodies)),
                          self.rng.randrange(len(closes)), self.rng.randrange(len(mids)))
            text = f"{opens[o]} {bodies[b].format(**vals)} {mids[m]} {closes[c]}"
            if 15 <= len(text.split()) <= 60:
                self.used[kind][(o, bodies[b][:30], m, c)] += 1
                return text
        raise ValueError(f"think out of 15-60 words: {text}")

    def plan(self, family: str, **vals) -> str:
        v = {"s": "", "p": "", "d": "", **vals}
        return self._make("plan", OPEN, PLAN[family], CLOSE, v)

    def read(self, outcome: str, **vals) -> str:
        v = {"s": "", "p": "", "d": "", "e": "", "vf": "", "n": "", "first": "", "last": "", **vals}
        return self._make("read", OPEN_R, READ[outcome], CLOSE_R, v)


def short(title: str, n: int = 55) -> str:
    return title if len(title) <= n else title[:n].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------------------------- trace plumbing
class Trace:
    LIMIT = {"search_law": 3700, "get_decision": 10**6}

    def __init__(self, system: str, user: str, exam: set, exact: bool = False):
        self.m = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        self.exam, self.exact, self.touched, self.calls = exam, exact, False, []

    def call(self, think: str, name: str, args: dict, law, decisions=None) -> dict:
        res = T.call(name, dict(args), law, decisions)
        for h in [res, *res.get("hits", [])]:
            if "act_key" in h and (h["act_key"], h.get("path", "") if self.exact else art_root(h.get("path", ""))) in self.exam:
                self.touched = True
        body = json.dumps(res, ensure_ascii=False)
        if len(body) > self.LIMIT.get(name, MAX_RESP):
            self.touched = True  # too long to show whole: drop the trace instead of cutting JSON
        self.m.append({"role": "assistant", "reasoning_content": think, "content": "",
                       "tool_calls": [{"type": "function", "function": {"name": name, "arguments": dict(args)}}]})
        self.m.append({"role": "tool", "content": body})
        self.calls.append(name)
        return res

    def answer(self, think: str, text: str) -> None:
        self.m.append({"role": "assistant", "reasoning_content": think, "content": text})


def est_cost(messages: list[dict]) -> float:
    """Rough token cost of a rendered trace (calibrated on the L40S tokenizer, 21 Nov: all rows over 3,072 tokens had
    an estimate above 4,080 and no row under 3,072 was above 4,000). Real counts come from research/internship_check.py."""
    c = sum(len(m.get("content") or "") + len(m.get("reasoning_content") or "")
            + sum(len(json.dumps(t["function"], ensure_ascii=False)) for t in m.get("tool_calls", [])) for m in messages)
    return 801 + 60 * len(messages) + c / 2.0


EST_LIMIT = 4000


def quote_of(text: str, rng: random.Random, lo: int = 60, hi: int = 220) -> str:
    """Verbatim span from the start of the text, cut at a word boundary, 60..220 characters (or the whole text)."""
    t = text.strip()
    if len(t) <= hi:
        return t
    cut = t.rfind(" ", lo, rng.randint(lo + 20, hi))
    return t[: cut if cut >= lo else hi]


def pseudo_item(family: str, answer: str, **kw) -> dict:
    return {"family": family, "answer": answer, **kw}


def show_decision(dec: dict, quotes: list[str]) -> str:
    """get_decision output cut to AUDIT_CAP characters, valid JSON. Clauses holding a flagged quote are kept first, then
    the others in order; dropped clauses set "kesilgan": true. None when a flagged quote cannot be shown."""
    out = {"reg": dec.get("reg_number", ""), "date": dec.get("adopted") or "", "body": dec.get("body") or "",
           "title": dec.get("title") or "", "preamble": dec.get("preamble") or "", "clauses": [], "url": dec.get("url") or ""}
    clauses = list(dec.get("clauses") or [])
    key = [norm(q)[:40] for q in quotes if q]
    pre_hit = any(k and k in norm(dec.get("preamble") or "") for k in key)
    out["preamble"] = out["preamble"][: 900 if not pre_hit else 1600]
    chosen = []
    need = [i for i, c in enumerate(clauses) if any(k and k in norm(str(c)) for k in key)]
    for i in need + [i for i in range(len(clauses)) if i not in need]:
        trial = sorted(chosen + [i])
        out["clauses"] = [clauses[j] for j in trial]
        if len(json.dumps(out, ensure_ascii=False)) > AUDIT_CAP:
            if i in need:
                return None
            continue
        chosen = trial
    out["clauses"] = [clauses[j] for j in chosen]
    if len(chosen) < len(clauses) or len(out["preamble"]) < len(dec.get("preamble") or ""):
        out["kesilgan"] = True
    if any(k and k not in norm(out["preamble"] + " ".join(map(str, out["clauses"]))) for k in key):
        return None
    return json.dumps(out, ensure_ascii=False)


class Builder:
    def __init__(self, seed: int, exam: set, exam_pairs: set, tulu_rows: list):
        self.rng = random.Random(seed)
        self.exam, self.exam_pairs, self.tulu = exam, exam_pairs, tulu_rows
        self.exam_exact = load_exam_exact()
        self.law = LawStore()
        self.think = Think(self.rng)
        self.used_paths: set = set()
        self.rows: list[dict] = []
        con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        self.acts = {r["act_key"]: dict(r) for r in con.execute("SELECT * FROM acts")}
        self.by_path: dict = defaultdict(list)
        for r in con.execute("SELECT act_key, path, heading, text, valid_from, valid_to FROM units "
                             "WHERE length(text) BETWEEN 80 AND ? AND path NOT LIKE '%preamble%'", (MAX_UNIT_CHARS,)):
            if (r["act_key"], art_root(r["path"])) in exam:
                continue
            self.by_path[(r["act_key"], r["path"])].append((r["valid_from"], r["valid_to"], r["text"], r["heading"]))
        con.close()
        self.keys = sorted(self.by_path)
        self.rng.shuffle(self.keys)
        self.gap_acts = {k for k in self.acts if self._has_gap(k)}

    def _has_gap(self, key: str) -> bool:
        eds = self.law.editions(key)
        return bool(eds) and len(eds) > 1 and self.law.edition_gap(key, eds[0]["valid_from"]) is not None

    # -------------------------------------------------------------------------------- helpers
    def emit(self, family: str, tr: Trace, final: str, answer_gold, grade_item: dict | None, tags: dict, want: str = "right") -> bool:
        if tr.touched or est_cost(tr.m) > EST_LIMIT:
            return False
        if grade_item is not None:  # the answer must grade right under the exam's own grader
            if grade(grade_item, final) != want:
                return False
        self.rows.append({"kind": "legal", "family": family, "tools": True, "messages": tr.m, "calls": len(tr.calls),
                          "final": final, "tags": tags})
        return True

    def pick_date(self, versions, key, path):
        vf, vt, text, head = versions
        on = rand_date(self.rng, vf, vt)
        if not on or self.law.edition_gap(key, on) is not None:
            return None
        got = self.law.get_unit(key, path, on)
        if not got or norm(got["text"]) != norm(text):
            return None
        return on

    def title(self, key: str) -> str:
        return short(self.acts[key]["title"])

    def arg_article(self, path: str) -> str:
        return path.split("/")[0].split(":")[1] if "/" not in path and path.startswith("art:") and self.rng.random() < 0.5 else path

    def act_arg(self, key: str) -> str:
        return act_name(self.acts[key])

    # -------------------------------------------------------------------------------- families
    def gen_lookup(self, n: int) -> None:
        got, verify_n = 0, 0
        for key, path in self.keys:
            if got >= n:
                break
            if (key, path) in self.used_paths:
                continue
            v = self.by_path[(key, path)][self.rng.randrange(len(self.by_path[(key, path)]))]
            on = self.pick_date(v, key, path)
            if not on:
                continue
            a = self.acts[key]
            user = (f"{act_name(a)} {human_path(path)} {on} holatida qanday edi? Matn boshidan kamida 60 belgini "
                    f"aynan (so'zma-so'z) keltiring.")
            tr = Trace(SYSTEM, user, self.exam)
            args = {"act": self.act_arg(key), "article": self.arg_article(path), "date": on}
            res = tr.call(self.think.plan("lookup", s=self.title(key), p=human_path(path), d=on), "law_as_of", args, self.law)
            if "text" not in res:
                continue
            q = quote_of(res["text"], self.rng)
            if got % 3 != 0:
                vres = tr.call(self.think.read("found", p=human_path(path), e=res["edition"], vf=res["valid_from"]),
                               "verify_quote", {**args, "quote": q}, self.law)
                if not vres.get("ok"):
                    continue
                tr.answer(self.think.read("verified"), q)
            else:
                tr.answer(self.think.read("found", p=human_path(path), e=res["edition"], vf=res["valid_from"]), q)
            item = pseudo_item("lookup", res["text"])
            if self.emit("lookup", tr, q, res["text"], item, {"act": key, "path": path, "date": on}):
                self.used_paths.add((key, path))
                got += 1

    def gen_flip(self, n: int) -> None:
        pairs = []
        for (key, path), vs in self.by_path.items():
            vs = sorted(vs, key=lambda v: v[0])
            for r1, r2 in zip(vs, vs[1:]):
                a, b = norm(r1[2]), norm(r2[2])
                short_, long_ = sorted((a, b), key=len)
                if r1[1] == r2[0] and a != b and short_.rstrip(";.,: ") not in long_ and (key, path) not in self.used_paths:
                    pairs.append((key, path, r1, r2))
        self.rng.shuffle(pairs)
        got = 0
        for key, path, r1, r2 in pairs:
            if got >= n:
                break
            old_is_gold = self.rng.random() < 0.5
            gold = r1 if old_is_gold else r2
            on = self.pick_date(gold, key, path)
            if not on:
                continue
            t_old, t_new = diff_window(r1[2], r2[2])
            built = []
            with_ed = got % 10 < 6
            for first_is_old in (True, False):  # twins: same article and date, A/B swapped
                a_txt, b_txt = (t_old, t_new) if first_is_old else (t_new, t_old)
                ans = "A" if (old_is_gold == first_is_old) else "B"
                user = (f"{act_name(self.acts[key])} {human_path(path)} ikki tahrirda:\nA) {a_txt}\nB) {b_txt}\n"
                        f"{on} kuni qaysi tahrir amalda edi? Faqat A yoki B deb javob bering.")
                tr = Trace(SYSTEM, user, self.exam)
                res = tr.call(self.think.plan("flip", s=self.title(key), p=human_path(path), d=on), "law_as_of",
                              {"act": self.act_arg(key), "article": self.arg_article(path), "date": on}, self.law)
                if "text" not in res or norm(res["text"]) != norm(gold[2]):
                    break
                if with_ed:
                    r2 = tr.call(self.think.read("found", p=human_path(path), e=res["edition"], vf=res["valid_from"]),
                                 "list_editions", {"act": self.act_arg(key)}, self.law)
                    if "editions" not in r2:
                        break
                    tr.answer(self.think.read("editions", n=len(r2["editions"]), first=r2["editions"][0], last=r2["editions"][-1]), ans)
                else:
                    tr.answer(self.think.read("found", p=human_path(path), e=res["edition"], vf=res["valid_from"]), ans)
                built.append((tr, ans))
            if len(built) != 2 or any(t.touched for t, _ in built):
                continue
            for tr, ans in built:
                self.emit("flip", tr, ans, ans, pseudo_item("flip", ans), {"act": key, "path": path, "date": on})
            self.used_paths.add((key, path))
            got += 2

    def gen_in_force(self, n: int) -> None:
        yes, no = [], []
        for (key, path), vs in self.by_path.items():
            if (key, path) in self.used_paths:
                continue
            vs = sorted(vs, key=lambda v: v[0])
            eds = self.law.editions(key)
            if not eds:
                continue
            yes.append((key, path, vs[0], "in"))
            if vs[0][0] > eds[0]["valid_from"]:
                no.append((key, path, vs[0], "before"))
            if vs[-1][1] and vs[-1][1] < TODAY:
                no.append((key, path, vs[-1], "after"))
        self.rng.shuffle(yes)
        self.rng.shuffle(no)
        half = n // 2
        recover_left = 25
        for pool, want in ((yes, "ha"), (no, "yo'q")):
            got = 0
            for key, path, v, where in pool:
                if got >= half:
                    break
                if (key, path) in self.used_paths:
                    continue
                eds = self.law.editions(key)
                if where == "in":
                    on = rand_date(self.rng, v[0], v[1])
                elif where == "before":
                    on = rand_date(self.rng, eds[0]["valid_from"], v[0])
                else:
                    on = rand_date(self.rng, v[1], None)
                if not on or self.law.edition_gap(key, on) is not None:
                    continue
                if (self.law.get_unit(key, path, on) is not None) != (want == "ha"):
                    continue
                a = self.acts[key]
                user = (f"{act_name(a)} {human_path(path)} {on} kuni amalda bo'lganmi (shu raqam bilan mavjud edimi)? "
                        f"Faqat \"ha\" yoki \"yo'q\" deb javob bering.")
                tr = Trace(SYSTEM, user, self.exam)
                target = {"act": self.act_arg(key), "article": self.arg_article(path), "date": on}
                recover = recover_left > 0 and got % 2 == 0
                if recover:
                    slip = self.rng.choice(["act", "article"])
                    bad = dict(target)
                    if slip == "act":
                        bad["act"] = a["title"].split()[0] + " " + str(self.rng.randint(11, 99))
                    else:
                        bad["article"] = "modda " + path.split("/")[0].split(":")[-1]
                    res0 = tr.call(self.think.plan("recover", s=self.title(key), p=human_path(path), d=on), "law_as_of", bad, self.law)
                    if "error" not in res0:
                        continue
                    r1 = tr.call(self.think.read("no_act" if slip == "act" else "missing_path", p=human_path(path), d=on),
                                 "list_editions", {"act": self.act_arg(key)}, self.law)
                    if "editions" not in r1:
                        continue
                    res = tr.call(self.think.read("editions", n=len(r1["editions"]), first=r1["editions"][0], last=r1["editions"][-1]),
                                  "law_as_of", target, self.law)
                else:
                    res = tr.call(self.think.plan("in_force", s=self.title(key), p=human_path(path), d=on), "law_as_of", target, self.law)
                if want == "ha":
                    if "text" not in res:
                        continue
                    tr.answer(self.think.read("found", p=human_path(path), e=res["edition"], vf=res["valid_from"]) + " Javob: ha.", "ha")
                else:
                    if "error" not in res:
                        continue
                    if not recover:
                        r2 = tr.call(self.think.read("missing_path", p=human_path(path), d=on), "list_editions",
                                     {"act": self.act_arg(key)}, self.law)
                        if "editions" not in r2:
                            continue
                        tr.answer(self.think.read("editions", n=len(r2["editions"]), first=r2["editions"][0],
                                                  last=r2["editions"][-1]) + " Javob: yo'q.", "yo'q")
                    else:
                        tr.answer(self.think.read("missing_path", p=human_path(path), d=on) + " Javob: yo'q.", "yo'q")
                if self.emit("in_force", tr, want, want, pseudo_item("in_force", want), {"act": key, "path": path, "date": on, "recover": recover}):
                    self.used_paths.add((key, path))
                    got += 1
                    recover_left -= 1 if recover else 0

    def gen_hierarchy(self, n: int) -> None:
        keys = sorted(self.acts)
        seen, tries, got = set(), 0, 0
        nla_q = {"query": "normativ-huquqiy hujjatlarning turlari", "date": TODAY, "act": "O'RQ-682"}
        nla_ok = any(h["path"] == "art:6" for h in T.search_law(self.law, **nla_q).get("hits", []))
        classes = Counter()
        while got < n and tries < 20000:
            tries += 1
            x, y = self.rng.sample(keys, 2)
            if RANK[self.acts[x]["type"]] == RANK[self.acts[y]["type"]] or frozenset((x, y)) in self.exam_pairs | seen:
                continue
            win = "A" if RANK[self.acts[x]["type"]] > RANK[self.acts[y]["type"]] else "B"
            if classes[win] >= n // 2:
                continue
            seen.add(frozenset((x, y)))
            user = (f"A) {act_name(self.acts[x])}\nB) {act_name(self.acts[y])}\nUlarning normalari bir-biriga zid bo'lsa, "
                    f"qaysi biri ustun turadi? Faqat A yoki B deb javob bering.")
            tr = Trace(SYSTEM, user, self.exam)
            hi = self.acts[x if win == "A" else y]["type"]
            lo = self.acts[y if win == "A" else x]["type"]
            note = f"Yuridik kuch bo'yicha {hi} turi {lo} turidan yuqori. Javob: {win}."
            if got % 2 == 0 or not nla_ok:
                tr.answer(self.think.plan("hierarchy") + " " + note, win)
            else:
                res = tr.call(self.think.plan("hierarchy"), "search_law", nla_q, self.law)
                tr.answer(self.think.read("hits", n=len(res["hits"]), p="6-modda", s="O'RQ-682") + " " + note, win)
            if self.emit("hierarchy", tr, win, win, pseudo_item("hierarchy", win), {"a": x, "b": y}):
                got += 1
                classes[win] += 1

    def gen_discovery(self, n: int) -> None:
        """No act named: a sentence fragment of a norm and a date -> search_law, then law_as_of on the hit."""
        got = 0
        for key, path in self.keys:
            if got >= n:
                break
            if (key, path) in self.used_paths or not path.startswith("art:"):
                continue
            vs = self.by_path[(key, path)]
            v = vs[self.rng.randrange(len(vs))]
            on = self.pick_date(v, key, path)
            if not on or len(v[2]) < 140:
                continue
            frag = quote_of(v[2], self.rng, 70, 110)
            user = (f"{on} holatida kuchda bo'lgan qaysi hujjatning qaysi moddasida shunday norma bor: «{frag}»? "
                    f"Bitta gapda javob bering va aynan iqtibos keltiring.")
            tr = Trace(SYSTEM, user, self.exam)
            res = tr.call(self.think.plan("discovery", d=on), "search_law", {"query": frag, "date": on}, self.law)
            hits = res.get("hits", [])
            if not hits or hits[0]["act_key"] != key or art_root(hits[0]["path"]) != art_root(path):
                continue
            hp = hits[0]["path"]
            q = quote_of(hits[0]["text"], self.rng, 60, 200)
            r2 = tr.call(self.think.read("hits", n=len(hits), p=human_path(hp), s=self.title(key)), "verify_quote",
                         {"act": key, "article": hp, "date": on, "quote": q}, self.law)
            if not r2.get("ok"):
                continue
            final = f"{act_name(self.acts[key])} {human_path(hp)}: «{q}»"
            tr.answer(self.think.read("verified"), final)
            if self.emit("discovery", tr, final, final, None, {"act": key, "path": hp, "date": on}):
                self.used_paths.add((key, path))
                got += 1

    def gen_abstain(self, n: int) -> None:
        reasons = ["no_act", "no_article", "before_act", "gap"] if self.gap_acts else ["no_act", "no_article", "before_act"]
        per = {r: n // len(reasons) for r in reasons}
        for r in reasons[: n - sum(per.values())]:
            per[r] += 1
        absent = [t for t in ("Mehnat kodeksi", "Jinoyat kodeksi", "Fuqarolik kodeksi", "Oila kodeksi", "Yer osti boyliklari to'g'risida",
                              "Jinoyat-protsessual kodeksi", "Bojxona kodeksi", "Ekologiya kodeksi", "Shaharsozlik kodeksi")
                  if self.law.find_act(t) is None]
        tmpl = "«{t}» (Kodeks) {p} {d} holatida qanday edi? Matn boshidan kamida 60 belgini aynan (so'zma-so'z) keltiriladi."
        for reason, cnt in per.items():
            got, guard = 0, 0
            while got < cnt and guard < 5000:
                guard += 1
                key, path = self.keys[self.rng.randrange(len(self.keys))]
                if (key, path) in self.used_paths:
                    continue
                v = self.by_path[(key, path)][0]
                a = self.acts[key]
                eds = self.law.editions(key)
                if not eds:
                    continue
                if reason == "no_act":
                    t = absent[self.rng.randrange(len(absent))]
                    on = rand_date(self.rng, "2015-01-01", TODAY)
                    p = f"{self.rng.randint(2, 120)}-modda"
                    user = f"«Oʻzbekiston Respublikasining {t}» (Kodeks) {p} {on} holatida qanday edi? Matn boshidan kamida 60 belgini aynan (so'zma-so'z) keltiring."
                    tr = Trace(SYSTEM, user, self.exam)
                    res = tr.call(self.think.plan("abstain", s=t, p=p, d=on), "law_as_of",
                                  {"act": f"Oʻzbekiston Respublikasining {t}", "article": p.split("-")[0], "date": on}, self.law)
                    if "error" not in res:
                        continue
                    final = f"noaniq: «{t}» qonun bazasida yo'q, shu sababli {on} dagi matnni tasdiqlay olmayman."
                    tr.answer(self.think.read("no_act") + " Taxmin qilib iqtibos keltirmayman.", final)
                    tags = {"reason": reason}
                elif reason == "no_article":
                    on = self.pick_date(v, key, path)
                    if not on:
                        continue
                    ghost = f"art:{self.rng.randint(900, 990)}"
                    user = (f"{act_name(a)} {human_path(ghost)} {on} holatida qanday edi? Matn boshidan kamida 60 belgini "
                            f"aynan (so'zma-so'z) keltiring.")
                    tr = Trace(SYSTEM, user, self.exam)
                    res = tr.call(self.think.plan("abstain", s=self.title(key), p=human_path(ghost), d=on), "law_as_of",
                                  {"act": self.act_arg(key), "article": ghost, "date": on}, self.law)
                    if "not found" not in res.get("error", ""):
                        continue
                    final = f"noaniq: {human_path(ghost)} {on} dagi tahrirda topilmadi, iqtibos keltira olmayman."
                    tr.answer(self.think.read("missing_path", p=human_path(ghost), d=on) + " Mavjud bo'lmagan matnni to'qimayman.", final)
                    tags = {"reason": reason, "act": key}
                elif reason == "before_act":
                    first = eds[0]["valid_from"]
                    on = rand_date(self.rng, "2000-01-01", first)
                    if not on or on >= first:
                        continue
                    user = (f"{act_name(a)} {human_path(path)} {on} holatida qanday edi? Matn boshidan kamida 60 belgini "
                            f"aynan (so'zma-so'z) keltiring.")
                    tr = Trace(SYSTEM, user, self.exam)
                    res = tr.call(self.think.plan("abstain", s=self.title(key), p=human_path(path), d=on), "law_as_of",
                                  {"act": self.act_arg(key), "article": self.arg_article(path), "date": on}, self.law)
                    if "did not exist" not in res.get("error", ""):
                        continue
                    final = f"noaniq: bu hujjatning bazadagi birinchi tahriri {first} da; {on} da u mavjud emas edi."
                    tr.answer(self.think.read("no_edition", d=on) + " Asos topilmadi.", final)
                    tags = {"reason": reason, "act": key}
                else:  # gap: the store skipped editions around the date
                    if key not in self.gap_acts:
                        continue
                    v0 = self.law.editions(key)[0]["valid_from"]
                    gp = self.law.edition_gap(key, v0)
                    on = rand_date(self.rng, gp[0], gp[1])
                    if not on or self.law.edition_gap(key, on) is None:
                        continue
                    user = (f"{act_name(a)} {human_path(path)} {on} holatida qanday edi? Matn boshidan kamida 60 belgini "
                            f"aynan (so'zma-so'z) keltiring.")
                    tr = Trace(SYSTEM, user, self.exam)
                    tr.call(self.think.plan("abstain", s=self.title(key), p=human_path(path), d=on), "law_as_of",
                            {"act": self.act_arg(key), "article": self.arg_article(path), "date": on}, self.law)
                    r2 = tr.call(self.think.read("found", p=human_path(path), e="?", vf="?"), "list_editions", {"act": self.act_arg(key)}, self.law)
                    if "editions" not in r2:
                        continue
                    final = (f"noaniq: saqlangan tahrirlar orasida uzilish bor ({gp[0]} va {gp[1]}); "
                             f"{on} dagi aniq matnni tasdiqlay olmayman.")
                    tr.answer(self.think.read("editions", n=len(r2["editions"]), first=r2["editions"][0], last=r2["editions"][-1])
                              + " Oraliqdagi tahrir saqlanmagan.", final)
                    tags = {"reason": reason, "act": key}
                if self.emit("abstain", tr, final, "noaniq", pseudo_item("lookup", "x"), tags | {"reason": reason}, want="abstain"):
                    got += 1

    # -------------------------------------------------------------------------------- audit
    def gen_audit(self, n: int, dev_regs: set[str]) -> tuple[list[dict], list[dict]]:
        """Returns (train rows, dev rows). Verdict mix gated: no verdict above 35 % of the train slice."""
        from mezon.plain import explain
        from mezon.rules.run import audit
        from research.train_data import answer as sft_answer

        store = DecisionStore()
        sft = [json.loads(x) for x in (ROOT / "data" / "train" / "sft.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
        v0 = ROOT / "data" / "eval" / "mezon_bench_v0.jsonl"
        exam_regs = set()
        if v0.exists():
            from research.train_pilot import exam_regs as er
            exam_regs = er()
        cands = []
        for r in sft:
            m = re.match(r"Qaror (\S+), qabul qilingan: (\S+)\.", r["messages"][1]["content"])
            if m and m.group(1) not in GOLDEN | exam_regs and not any(g in r["messages"][1]["content"] for g in GOLDEN | exam_regs):
                cands.append((m.group(1), json.loads(r["messages"][2]["content"])["xulosa"]))
        self.rng.shuffle(cands)
        # clusters: near-duplicate decisions go to the same side (word 6-shingle Jaccard >= 0.9 on the operative text)
        def shingles(txt):
            w = norm(txt).split()
            return {hash(" ".join(w[i:i + 6])) for i in range(max(1, len(w) - 5))}

        shown = show_decision

        prepared = []
        seen_sh: list[tuple[set, bool]] = []
        for reg, verdict in cands:
            ids = store.by_reg(reg)
            d = store.get(ids[0]) if ids else None
            if not d or not d.get("text") or len(d["text"]) < 200:
                continue
            sh = shingles(d["text"])
            dup = next((is_dev for s, is_dev in seen_sh if len(s & sh) / max(1, len(s | sh)) >= 0.9), None)
            is_dev = reg in dev_regs if dup is None else dup
            seen_sh.append((sh, is_dev))
            prepared.append((reg, verdict, d, is_dev))
        # a cluster that touches dev goes entirely to dev
        by_verdict = defaultdict(list)
        dev_rows = []
        for reg, verdict, d, is_dev in prepared:
            (dev_rows if is_dev else by_verdict[verdict]).append((reg, d))
        built: dict[str, list] = defaultdict(list)
        cap = int(0.35 * n)
        for verdict in ("negative", "positive_with_fixable_defects", "positive"):
            for reg, d in by_verdict[verdict]:
                if len(built[verdict]) >= (cap if verdict != "negative" else n):
                    break
                row = self._audit_trace(store, reg, d, shown, explain, audit, sft_answer)
                if row and row["verdict"] == verdict:
                    built[verdict].append(row)
        # gate: no verdict above 35 % of the slice -> total limited by the scarcest class
        neg, fix, clean = (built[v] for v in ("negative", "positive_with_fixable_defects", "positive"))
        total = min(n, int(len(neg) / 0.30) if neg else 0)
        k_neg = min(len(neg), int(0.35 * total))
        k_fix, k_clean = min(len(fix), int(0.35 * total)), min(len(clean), int(0.35 * total))
        rows = neg[:k_neg] + fix[:k_fix] + clean[:k_clean]
        print(f"audit candidates built: negative {len(neg)}, fixable {len(fix)}, clean {len(clean)}; "
              f"kept {k_neg}/{k_fix}/{k_clean}", flush=True)
        dev_audit = []
        for reg, d in dev_rows[:150]:
            row = self._audit_trace(store, reg, d, shown, explain, audit, sft_answer)
            if row:
                row["kind"] = "audit_dev"
                dev_audit.append(row)
        return rows, dev_audit

    def _audit_trace(self, store, reg, d, shown, explain, audit, sft_answer):
        rep = audit(d["id"], law=self.law, decisions=store).to_dict()
        for fl in rep["flags"]:
            fl.update(explain(fl, rep))
        tr = Trace(AUDIT_SYSTEM, f"Qaror {reg} ni tekshiring: qaror matnini oling va har bir asosni qaror sanasidagi tahrir bo'yicha tekshiring.",
                   self.exam_exact, exact=True)
        quotes = [e["quote"] for fl in rep["flags"] for e in fl.get("evidence") or [] if e.get("quote")]
        body = shown(d, quotes)
        if body is None:
            return None
        shown_text = json.loads(body)
        tr.m.append({"role": "assistant", "reasoning_content": self.think.plan("audit"), "content": "",
                     "tool_calls": [{"type": "function", "function": {"name": "get_decision", "arguments": {"reg": reg}}}]})
        tr.m.append({"role": "tool", "content": body})
        tr.calls.append("get_decision")
        nflag = 0
        for fl in rep["flags"][:2]:
            c = (fl.get("citations") or [None])[0]
            if not c or not c.get("quote"):
                continue
            q = c["quote"][:200]
            res = tr.call(self.think.read("decision", n=len(shown_text.get("clauses") or [])) if nflag == 0 else
                          self.think.read("verified"), "verify_quote",
                          {"act": c["act_id"], "article": c["article"], "date": c["on_date"], "quote": q}, self.law)
            if not res.get("ok"):
                return None
            nflag += 1
        if len(rep["flags"]) and not nflag:
            return None
        ans = json.loads(sft_answer(rep))
        ans = {"qaror": reg, "sana": d.get("adopted") or "", **ans}
        final = json.dumps(ans, ensure_ascii=False)
        tr.answer(f"Tekshiruv yakunlandi: {len(rep['flags'])} ta ehtimoliy kamchilik, xulosa {rep['verdict']}. "
                  f"Yakuniy qarorni ekspert qabul qiladi.", final)
        if tr.touched or est_cost(tr.m) > EST_LIMIT:
            return None
        return {"kind": "legal", "family": "audit", "tools": True, "messages": tr.m, "calls": len(tr.calls),
                "final": final, "verdict": rep["verdict"], "tags": {"reg": reg}}

    # -------------------------------------------------------------------------------- OOD phrasing (val only)
    def gen_ood(self, n: int = 60) -> list[dict]:
        out, guard = [], 0
        words = {"modda": ["статья", "модда", "modda"], "kuni": ["на дату", "санасида", "kuni"]}
        while len(out) < n and guard < 4000:
            guard += 1
            key, path = self.keys[self.rng.randrange(len(self.keys))]
            if (key, path) in self.used_paths or not path.startswith("art:"):
                continue
            v = self.by_path[(key, path)][0]
            on = self.pick_date(v, key, path)
            if not on:
                continue
            a, num = self.acts[key], path.split(":")[1].split("/")[0]
            i = len(out) % 4
            if i == 0:
                user = f"На {on} действовала ли статья {num} акта «{a['title']}»? Ответьте только «ha» или «yo'q»."
            elif i == 1:
                user = f"{on} санасида «{a['title']}» ҳужжатининг {num}-моддаси мавжуд эдими? Фақат «ha» ёки «yo'q» деб жавоб беринг."
            elif i == 2:
                user = f"Savol: {num}-modda, «{a['title']}», sana {on}. U shu kuni amalda bo'lganmi? Faqat \"ha\" yoki \"yo'q\"."
            else:
                user = f"Hujjat: {a['title']}. Qism/band: {path}. Sana: {on}. Shu kuni bu band bormidi? Javob: ha yoki yo'q."
            gold = "ha" if self.law.get_unit(key, path, on) is not None else "yo'q"
            out.append({"kind": "ood", "family": "in_force", "tools": True,
                        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                        "gold": gold, "tags": {"act": key, "path": path, "date": on}})
        return out

    # -------------------------------------------------------------------------------- replay
    def replay(self) -> list[dict]:
        rows = []
        for r in self.tulu:
            rows.append({"kind": "replay", "family": r["slot"], "tools": False, "messages": r["messages"], "tags": {}})
        return rows


# ---------------------------------------------------------------------------------------------- gates
def check_gates(rows: list[dict], think: Think | None = None) -> list[str]:
    """Hard gates of section 1.4; returns the list of failures (empty = pass). Works on any rows list."""
    fails = []
    total = len(rows)
    legal = [r for r in rows if r["kind"] == "legal"]
    c = Counter((r["family"], r["final"]) for r in legal if r["family"] in ("flip", "in_force", "hierarchy"))
    for (fam, ans), k in c.items():
        if k / total > 0.15:
            fails.append(f"answer class {fam}/{ans} = {k / total:.1%} of all rows (> 15 %)")
    for fam in ("flip", "in_force", "hierarchy"):
        fc = Counter(r["final"] for r in legal if r["family"] == fam)
        for ans, k in fc.items():
            share = k / max(1, sum(fc.values()))
            if not 0.45 <= share <= 0.55:
                fails.append(f"{fam} class {ans} share {share:.1%} outside 45-55 %")
    users = [r["messages"][1]["content"] for r in legal]
    if len(set(users)) != len(users):
        fails.append("duplicate prompts")
    lk = [r for r in legal if r["family"] == "lookup"]
    if lk and max(Counter(r["final"] for r in lk).values()) / len(lk) > 0.02:
        fails.append("identical lookup answer above 2 %")
    seen = Counter((r["tags"]["act"], r["tags"]["path"], r["tags"]["date"]) for r in lk)
    if seen and max(seen.values()) > 1:
        fails.append("two lookup rows share (act, path, date)")
    au = [r for r in legal if r["family"] == "audit"]
    if au:
        vc = Counter(r["verdict"] for r in au)
        if max(vc.values()) / len(au) > 0.35 + 1e-9:
            fails.append(f"audit verdict above 35 %: {dict(vc)}")
        if max(Counter(r["final"] for r in au).values()) > max(1, 0.02 * len(au)):
            fails.append("identical audit answer above 2 %")
    nl = len(legal)
    if nl:
        zero, one, two = (sum(1 for r in legal if (r["calls"] == 0, r["calls"] == 1, r["calls"] >= 2)[i]) / nl for i in range(3))
        if zero > 0.15:
            fails.append(f"0-call share {zero:.1%} > 15 %")
        if one > 0.45:
            fails.append(f"1-call share {one:.1%} > 45 %")
        if two < 0.40:
            fails.append(f"2+-call share {two:.1%} < 40 %")
    ab = Counter(r["tags"].get("reason") for r in legal if r["family"] == "abstain")
    if ab and max(ab.values()) / sum(ab.values()) > 0.40:
        fails.append(f"abstain reason above 40 %: {dict(ab)}")
    if think:
        for kind, cnt in think.used.items():
            n = sum(cnt.values())
            if n and max(cnt.values()) / n > 0.03:
                fails.append(f"a {kind} think template above 3 %")
    return fails


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2111)
    ap.add_argument("--tulu", default=str(ROOT / "data" / "train" / "_tulu_pick.jsonl"),
                    help="jsonl of {slot, messages}: 'replay_tulu' and 'replay_uz_qa' (extra Tulu) rows, picked on the box")
    ap.add_argument("--allow-fail", action="store_true")
    a = ap.parse_args()
    exam, pairs = load_exam()
    tulu = []
    if Path(a.tulu).exists():
        tulu = [json.loads(x) for x in Path(a.tulu).read_text(encoding="utf-8").split("\n") if x.strip()]
    b = Builder(a.seed, exam, pairs, tulu)
    print(f"exam articles excluded: {len(exam)}; pool articles {len(b.keys)}; acts with edition gaps {len(b.gap_acts)}", flush=True)
    for fam, fn in (("lookup", b.gen_lookup), ("flip", b.gen_flip), ("in_force", b.gen_in_force), ("hierarchy", b.gen_hierarchy),
                    ("discovery", b.gen_discovery), ("abstain", b.gen_abstain)):
        fn(TARGET[fam])
        print(fam, sum(1 for r in b.rows if r["family"] == fam), flush=True)
    import csv

    dev_regs = {r["original_number"] for r in csv.DictReader((ROOT / "data" / "interim" / "positive_originals.csv").open(encoding="utf-8"))
                if r["resolved"] == "True"}  # the 11 real positives with original text: dev smoke set
    audit_rows, audit_dev = b.gen_audit(TARGET["audit"], dev_regs)
    b.rows.extend(audit_rows)
    print("audit", len(audit_rows), "dev audit", len(audit_dev), flush=True)
    rep = b.replay()
    # split: ~8 % of each legal family to val; binary families stratified by answer; flip as whole twin pairs; audit
    # was split by cluster above and keeps all its train rows
    train, val = [], []
    byfam = defaultdict(list)
    for r in b.rows:
        byfam[r["family"]].append(r)
    for fam, rs in byfam.items():
        b.rng.shuffle(rs)
        k = 0 if fam == "audit" else max(2, round(VAL_SHARE * len(rs)))
        if fam == "flip":
            pairs_ = defaultdict(list)
            for r in rs:
                pairs_[(r["tags"]["act"], r["tags"]["path"], r["tags"]["date"])].append(r)
            plist = list(pairs_.values())
            for i, pr in enumerate(plist):
                (val if i < k // 2 else train).extend(pr)
        elif fam in ("in_force", "hierarchy"):
            for cls in sorted({r["final"] for r in rs}):
                crs = [r for r in rs if r["final"] == cls]
                val += crs[: k // 2]
                train += crs[k // 2:]
        else:
            val += rs[:k]
            train += rs[k:]
    for i, r in enumerate(rep):
        (val if i % 12 == 0 else train).append(r)
    ood = b.gen_ood()
    val += ood + audit_dev
    allrows = list(train)
    fails = check_gates(train, b.think)
    print("GATES:", "pass" if not fails else fails)
    if fails and not a.allow_fail:
        raise SystemExit("gate failure: nothing written (use --allow-fail to inspect)")
    b.rng.shuffle(allrows)
    for path, rows in ((OUT_TRAIN, allrows), (OUT_VAL, val)):
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8", newline="\n")
    c = Counter((r["kind"], r["family"]) for r in allrows)
    print(f"wrote {OUT_TRAIN} ({len(allrows)} rows) {dict(c)}")
    print(f"wrote {OUT_VAL} ({len(val)} rows) {dict(Counter((r['kind'], r['family']) for r in val))}")


if __name__ == "__main__":
    main()
