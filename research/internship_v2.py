"""Internship v2 data: v1 rows + deterministic traces for the three gaps of the hard exam (MezonBench v2.1, 21 Nov).

    .venv/Scripts/python.exe -X utf8 -m research.internship_v2
        -> data/train/internship_v2.jsonl  (train)   data/train/internship_v2_val.jsonl  (10 % of new rows + filtered v1 val)

Families (every trace is built by running mezon.tools.call; the answer must grade right under mezonbench_v2.grade):
  dead_date           "was the article in force on D?" -> not found -> list_editions -> probe editions (backward doubling, then
                      binary search) -> "yo'q, <date it lost force>"; or "ha" + the edition (live articles, and dead
                      articles asked before they died). 50/50.
  name_recover        the question names the act in a form the store cannot resolve -> error -> retry with the act number
                      (or search_law for codes) -> the dead_date procedure. ha / yo'q 50/50.
  name_recover_quote  same recovery, then a verbatim quote from the edition in force on the date.
  chain_date          "was it in force on D and what did it say?" -> verbatim quote of the edition on D (>= 60 chars, today's
                      wording differs for amended articles) or "yo'q" (+ date) for dead articles. 50/50.
Leak control: every (act, article root) of every MezonBench file (v1, where, v2, v2.1, v3, private) is excluded from the
pool and from the v1 rows; every registration number found in those files and the golden cases drop v1 audit rows.
"""

import glob
import itertools
import json
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from mezon.config import LAW_DB
from mezon.lawstore.store import LawStore
from research import internship_data as I
from research.internship_data import EST_LIMIT, GOLDEN, Trace, art_root, est_cost, quote_of
from research.mezonbench import SYSTEM, TODAY, act_name, human_path, norm, rand_date
from research.mezonbench import grade as grade_v1
from research.mezonbench_v2 import grade as grade_v2
from research.regnum import find_all

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "data" / "bench"
OUT_TRAIN = ROOT / "data" / "train" / "internship_v2.jsonl"
OUT_VAL = ROOT / "data" / "train" / "internship_v2_val.jsonl"
V1_TRAIN, V1_VAL = I.OUT_TRAIN, I.OUT_VAL
TARGET = {"dead_date": 180, "name_recover": 110, "name_recover_quote": 50, "chain_date": 160}
NEW_FAMILIES = tuple(TARGET)
MAX_UNIT = 600
MAX_PROBES = 7
PER_UNIT = 3
LOST_CAP = 10  # 2 % of the 500 new rows: one lost-force date in at most 10 answers


# ---------------------------------------------------------------------------------------------- leak control
def bench_files() -> list[Path]:
    names = [
        "mezonbench_v1.jsonl",
        "mezonbench_where_v1.jsonl",
        "mezonbench_v2.jsonl",
        "mezonbench_v2_1.jsonl",
        "mezonbench_v3.jsonl",
    ]
    files = [BENCH_DIR / n for n in names]
    files += [Path(p) for p in glob.glob(str(BENCH_DIR / "private" / "*"))]
    files += [Path(p) for p in glob.glob(str(BENCH_DIR / "audit_v1" / "*"))]
    files += [
        BENCH_DIR / n
        for n in (
            "FROZEN_audit_v1.json",
            "FROZEN_v1_1.json",
            "FROZEN_v2_0.json",
            "FROZEN_v2_1.json",
            "FROZEN_v3_0.json",
        )
    ]
    return [p for p in files if p.is_file()]


def load_leak_sets() -> tuple[set, set, int]:
    """(act, article root) pairs, registration numbers, number of files scanned."""
    arts: set = set()
    regs: set = set(GOLDEN)
    files = bench_files()
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("{"):
                try:
                    it = json.loads(s)
                except ValueError:
                    continue
                if isinstance(it.get("act"), str) and isinstance(it.get("path"), str):
                    arts.add((it["act"], art_root(it["path"])))
        regs |= {h["original"] if "original" in h else h.get("reg", "") for h in find_all(text)} - {""}
        regs |= set(re.findall(r"\b[IVX]*-?\d+-\d+-\d+(?:-\d+)?-[QKF]/\d\d\b", text))
    return arts, regs, len(files)


# ---------------------------------------------------------------------------------------------- think phrasing
OPEN = I.OPEN + [
    "Sana bo'yicha tekshirish kerak.",
    "Bu yerda aniq tahrir sanasi muhim.",
    "Modda holatini bazadan bilib olaman.",
]
PLAN = {
    "date": [
        "{p} ({s}) {d} kuni amalda bo'lganmi, avval shu sanadagi tahrirni so'rayman.",
        "{d} dagi tahrirda {p} bormi, ko'raman: kuchini yo'qotgan bo'lsa, sanasini ham topishim kerak.",
        "Kerak: {s}, {p}, sana {d}. Moddaning o'sha kundagi holatini vosita bilan olaman.",
    ],
    "quote": [
        "{d} dagi tahrirdan {p} ({s}) matnini olaman; bugungi tahrir boshqacha bo'lishi mumkin.",
        "Qaror sanasi {d}: {p} ({s}) o'sha kundagi so'zma-so'z matni kerak.",
        "Iqtibos aynan {d} dagi tahrirdan bo'lishi shart, shuning uchun sanani ko'rsatib so'rayman.",
    ],
    "bad_name": [
        "Hujjat nomini savoldagidek yozib so'rab ko'raman: {s}, {p}, {d}.",
        "{p} uchun {d} dagi matnni so'rayman; hujjat nomini savolda berilganicha kiritaman.",
    ],
}
READ = {
    "nf": [
        "{d} dagi tahrirda {p} topilmadi; bu hali uning umuman bo'lmaganini bildirmaydi, tahrirlarni ko'raman.",
        "Vosita: {p} bu sanada yo'q. Qachon yo'qolganini bilish uchun tahrirlar ro'yxati kerak.",
        "{p} {d} da topilmadi. Endi tahrir sanalarini ko'rib, yo'qolish chegarasini izlayman.",
    ],
    "eds": [
        "Tahrirlar {n} ta; {d} ga to'g'ri keladigani {cur}. Undan oldingi tahrirlarda moddani qidiraman.",
        "Ro'yxatda {n} ta tahrir, {d} dagi tahrir {cur}. Avvalgi tahrirlarni tekshirib chegarani aniqlayman.",
        "{n} ta tahrir saqlangan; kerakli oraliq {cur} dan oldin. Tahrir sanalari bo'yicha moddani izlayman.",
    ],
    "present": [
        "{e} tahririda {p} bor; demak modda o'sha paytda kuchda edi, chegara {lo} va {hi} orasida.",
        "Bu tahrirda ({e}) modda mavjud. Yo'qolish {lo} dan keyin va {hi} gacha sodir bo'lgan.",
        "{p} {e} tahririda topildi; chegara {lo} (bor) va {hi} (yo'q) o'rtasida.",
    ],
    "absent": [
        "{e} tahririda {p} yo'q; oxirgi mavjud tahrir bundan oldinroq, qidirishni davom ettiraman.",
        "Bu tahrirda ({e}) modda ko'rinmadi. Mavjud bo'lgan tahrirni yana oldinroqdan izlayman.",
        "{p} {e} da topilmadi, demak yo'qolish shu tahrirda yoki undan oldin sodir bo'lgan.",
    ],
    "boundary": [
        "{lo} tahririda {p} bor, {hi} tahririda yo'q: modda {hi} da kuchini yo'qotgan.",
        "Chegara aniq: oxirgi mavjud tahrir {lo}, keyingisi {hi}. Kuchini yo'qotgan sana {hi}.",
        "{p} {lo} gacha amalda, {hi} dan boshlab yo'q; sana {hi}.",
    ],
    "live": [
        "{p} {d} dagi tahrirda ({e}) mavjud, {vf} dan kuchda; demak javob: ha.",
        "Matn qaytdi: tahrir {e}, kuchga kirgan sana {vf}. Modda o'sha kuni amalda edi.",
        "{d} kuni {p} amalda ekani tasdiqlandi: tahrir {e}.",
    ],
    "live_old": [
        "{p} {d} da kuchda edi (tahrir {e}), garchi keyinroq o'zgargan yoki bekor qilingan bo'lsa ham.",
        "Savol {d} sanasiga qaratilgan: o'sha kuni {p} tahrir {e} bilan amalda edi.",
        "{d} dagi tahrirda modda bor; keyingi o'zgarishlar bu sanaga ta'sir qilmaydi.",
    ],
    "quote": [
        "{p} {d} dagi tahrirda ({e}) topildi; iqtibosni aynan shu matndan olaman.",
        "Tahrir {e}, {vf} dan {vt} gacha amalda. Bugungi tahrir boshqa bo'lishi mumkin, iqtibos shu tahrirdan.",
        "Matn olindi ({e}). Iqtibosni so'zma-so'z, shu tahrirdan keltiraman.",
    ],
    "no_act": [
        "Vosita hujjatni bu nom bilan topmadi; nom bazadagi ko'rinishga mos kelmadi.",
        "Xato: hujjat bazada shu nomda yo'q. Nomni boshqacha, aniqroq usulda berib ko'raman.",
        "Hujjat nomi tanilmadi; bu moddaning yo'qligini emas, nom shakli noto'g'riligini ko'rsatadi.",
    ],
    "retry_number": [
        "Hujjatning raqami {num}; shu raqam bilan qayta so'rayman.",
        "Savolda raqam bor: {num}. Hujjatni raqam orqali chaqirib ko'raman.",
    ],
    "retry_search": [
        "Raqami yo'q, shuning uchun hujjatni sarlavhasidagi so'zlar bo'yicha qidiraman.",
        "Nom bo'yicha topilmadi; sarlavha so'zlari bilan qidiruv orqali hujjat kalitini aniqlayman.",
    ],
    "hit": [
        "Qidiruv hujjatni topdi: kalit {k}. Endi shu kalit bilan so'rayman.",
        "Nomzod hujjat {k}; modda so'rovini shu nom bilan takrorlayman.",
    ],
    "verified": I.READ["verified"],
}
MID = I.MID_P


class Think(I.Think):
    """v1's slot composer with the v2 pools (same 3 % template gate bookkeeping)."""

    def say(self, kind: str, key: str, **vals) -> str:
        v = {k: "" for k in ("s", "p", "d", "e", "vf", "vt", "lo", "hi", "n", "cur", "num", "k")} | vals
        pool = PLAN[key] if kind == "plan" else READ[key]
        mids = I.MID_P if kind == "plan" else I.MID_R
        opens = OPEN if kind == "plan" else I.OPEN_R
        closes = I.CLOSE if kind == "plan" else I.CLOSE_R
        for _ in range(60):
            o, b, c, m = (
                self.rng.randrange(len(opens)),
                self.rng.randrange(len(pool)),
                self.rng.randrange(len(closes)),
                self.rng.randrange(len(mids)),
            )
            text = f"{opens[o]} {pool[b].format(**v)} {mids[m]} {closes[c]}"
            if 15 <= len(text.split()) <= 60:
                self.used[kind][(o, key, b, m, c)] += 1
                return text
        raise ValueError(text)


# ---------------------------------------------------------------------------------------------- prompt templates
DATE_LEAD = [
    "",
    "Savol: ",
    "Tekshirib bering: ",
    "Huquqshunos so'rayapti: ",
    "Hokimlik yuristi so'raydi: ",
    "Ariza bo'yicha aniqlik kerak: ",
    "Eslatma: javob tahrir sanasiga bog'liq. ",
]
# (core, tail kind): the tail decides the exact answer format
DATE_CORE = [
    "{a} {p} {d} kuni kuchda edimi?",
    "{d} sanasida {a} {p} amalda bo'lganmi?",
    "Mahalliy organ qarorida {a} {p} ga havola qilingan; qaror {d} da qabul qilingan. Shu norma o'sha kuni amalda edimi?",
    "{d} holatiga {a} {p} mavjud va kuchdami?",
    "Qaror {d} da chiqqan va {a} {p} ga tayanadi. Tayanch norma shu sanada kuchda bo'lganmi?",
    "{a}: {p} {d} da amal qilganmi?",
    "{p} ({a}) {d} sanasida bekor qilinmagan edimi, ya'ni kuchda edimi?",
]
DATE_TAIL = {
    "iso": 'Javobingiz "ha" yoki "yo\'q"; "yo\'q" bo\'lsa, modda kuchini yo\'qotgan sanani YYYY-MM-DD shaklida qo\'shing.',
    "short": "Javob shakli: «ha» yoki «yo'q, YYYY-MM-DD» (modda kuchini yo'qotgan sana).",
    "dmy": "Faqat ha yoki yo'q; yo'q bo'lsa, kuchini yo'qotgan sanani KK.OO.YYYY ko'rinishida yozing.",
    "iso2": "Birinchi so'z \"ha\" yoki \"yo'q\" bo'lsin. Modda bekor bo'lgan bo'lsa, qaysi sanadan (YYYY-MM-DD) bekor bo'lganini ham ayting.",
}
CHAIN_CORE = [
    "{a} {p}: qaror {d} da qabul qilingan. Norma o'sha kuni amalda bo'lganmi? Ha bo'lsa, shu sanadagi matndan kamida 60 belgini aynan keltiring.",
    "Qarorda {a} {p} ga tayaniladi (qabul sanasi {d}). {d} dagi tahrir bo'yicha: norma bormi? Bor bo'lsa, matnidan kamida 60 belgi so'zma-so'z.",
    "{d} sanali mahalliy qaror {a} {p} ni keltirgan. O'sha kundagi tahrirdan kamida 60 belgi aynan yozing; norma o'sha kuni kuchda bo'lmasa, \"yo'q\" deng.",
    "{a} {p}: {d} kuniga holat. Kuchda bo'lsa, matndan kamida 60 belgini aynan keltiring; bo'lmasa, \"yo'q\".",
    "Tadbirkor qaror ({d}) {a} {p} ga asoslanganini aytdi. Shu normaning {d} dagi matnidan kamida 60 belgi aynan; norma o'sha kuni yo'q bo'lsa, \"yo'q\" bilan javob bering.",
]
CHAIN_ASK_DATE = " \"yo'q\" bo'lsa, kuchini yo'qotgan sanani (YYYY-MM-DD) ham yozing."
QUOTE_CORE = [
    "{a} {p} {d} kuni qanday ko'rinishda edi? Matn boshidan kamida 60 belgini aynan keltiring.",
    "{d} sanasidagi tahrir bo'yicha {a} {p} matnini so'zma-so'z (kamida 60 belgi) yozing.",
    "{a} {p}: o'sha {d} kundagi matndan kamida 60 belgi aynan kerak.",
    "Hujjat: {a}. Band: {p}. Sana: {d}. Shu kundagi matndan kamida 60 belgini so'zma-so'z keltiring.",
]
NAME_LEAD = DATE_LEAD


def lost_phrase(fmt: str, lost: str, tail: str) -> str:
    if tail == "short":
        return f"yo'q, {lost}"
    if tail == "dmy":
        y, m, d = lost.split("-")
        return f"yo'q, kuchini yo'qotgan sana: {d}.{m}.{y}"
    return f"yo'q, kuchini yo'qotgan sana: {lost}"


# ---------------------------------------------------------------------------------------------- builder
class V2:
    def __init__(self, seed: int, exam: set):
        self.rng = random.Random(seed)
        self.exam = exam
        self.law = LawStore()
        self.think = Think(self.rng)
        self.rows: list[dict] = []
        self.finals: set = set()
        self.last_lo = ""
        self.lost_n: Counter = Counter()
        self.uses: Counter = Counter()
        self.tpl: Counter = Counter()
        self.stats: Counter = Counter()
        con = sqlite3.connect(f"file:{LAW_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        self.acts = {r["act_key"]: dict(r) for r in con.execute("SELECT * FROM acts")}
        self.versions: dict = defaultdict(list)
        self.alive_ever: set = set()
        for r in con.execute(
            "SELECT act_key, path, text, valid_from, valid_to FROM units WHERE path NOT LIKE '%preamble%' "
            "AND length(text) BETWEEN 80 AND ?",
            (MAX_UNIT,),
        ):
            if (r["act_key"], art_root(r["path"])) in exam:
                continue
            self.versions[(r["act_key"], r["path"])].append((r["valid_from"], r["valid_to"], r["text"]))
        full = {
            (r["act_key"], r["path"]): r["n"]
            for r in con.execute(
                "SELECT act_key, path, sum(valid_to IS NULL) n FROM units GROUP BY act_key, path"
            )
        }
        con.close()
        self.dead, self.live, self.amended = [], [], []
        for k, vs in self.versions.items():
            vs.sort()
            if len(vs) != len({v[0] for v in vs}):
                continue
            if full[k] == 0 and vs[-1][1] and vs[-1][1] <= TODAY:
                self.dead.append(k)
            elif full[k]:
                self.live.append(k)
                if len(vs) > 1 and any(norm(a[2]) != norm(b[2]) for a, b in itertools.pairwise(vs)):
                    self.amended.append(k)
        for pool in (self.dead, self.live, self.amended):
            pool.sort()
            self.rng.shuffle(pool)
        self.bad_names = 0

    # ------------------------------------------------------------------ helpers
    def tag(self, family: str, *ids) -> str:
        t = f"{family}|" + "|".join(map(str, ids))
        self.tpl[t] += 1
        return t

    def arg_art(self, path: str) -> str:
        return (
            path.split("/")[0].split(":")[1]
            if "/" not in path and path.startswith("art:") and self.rng.random() < 0.5
            else path
        )

    def emit(self, family: str, tr: Trace, final: str, item: dict, tags: dict, g=grade_v2) -> bool:
        if tr.touched or est_cost(tr.m) > EST_LIMIT:
            self.stats["drop_cost_or_touch"] += 1
            return False
        if (final.lower().startswith("ha. ") or family == "name_recover_quote") and (family, final) in self.finals:
            self.stats["drop_dup_quote"] += 1
            return False
        if final.startswith("yo'q,") and self.lost_n[tags["lost"]] >= LOST_CAP:  # no lost-force date may dominate
            self.stats["drop_date_cap"] += 1
            return False
        if g(item, final) != "right":
            self.stats["drop_grade"] += 1
            return False
        self.finals.add((family, final))
        if final.startswith("yo'q,"):
            self.lost_n[tags["lost"]] += 1
        self.rows.append(
            {
                "kind": "legal",
                "family": family,
                "tools": True,
                "messages": tr.m,
                "calls": len(tr.calls),
                "final": final,
                "tags": tags,
            }
        )
        return True

    def window(self, key, path, lo=None, hi=None):
        vs = self.versions[(key, path)]
        return rand_date(self.rng, lo or vs[0][0], hi)

    def locate_loss(self, tr: Trace, key: str, act_arg: str, path: str, d: str, lost: str):
        """not-found at d already seen. list_editions, backward doubling to a present edition, then binary search.
        Returns the boundary date or None."""
        _s, p = self.title(key), human_path(path)
        r = tr.call(self.think.say("read", "nf", p=p, d=d), "list_editions", {"act": act_arg}, self.law)
        if "editions" not in r:
            return None
        eds = r["editions"]
        idx = max(i for i, e in enumerate(eds) if e <= d)
        probes, lo, hi, step = 0, None, idx, 1
        art = self.arg_art(path)
        first = True
        while lo is None:
            i = idx - step
            if i < 0 or probes >= MAX_PROBES:
                return None
            think = (
                self.think.say("read", "eds", n=len(eds), d=d, cur=eds[idx])
                if first
                else self.think.say("read", "absent", p=p, e=eds[hi], lo="?", hi=eds[hi])
            )
            first = False
            res = tr.call(think, "law_as_of", {"act": act_arg, "article": art, "date": eds[i]}, self.law)
            probes += 1
            if "text" in res:
                lo = i
            elif "not found" in res.get("error", ""):
                hi = i
                step *= 2
            else:
                return None
        while hi - lo > 1:
            if probes >= MAX_PROBES:
                return None
            mid = (lo + hi) // 2
            res = tr.call(
                self.think.say("read", "present", p=p, e=eds[lo], lo=eds[lo], hi=eds[hi]),
                "law_as_of",
                {"act": act_arg, "article": art, "date": eds[mid]},
                self.law,
            )
            probes += 1
            if "text" in res:
                lo = mid
            elif "not found" in res.get("error", ""):
                hi = mid
            else:
                return None
        self.last_lo = eds[lo]
        return eds[hi] if eds[hi] == lost else None

    def title(self, key: str) -> str:
        return I.short(self.acts[key]["title"])

    # ------------------------------------------------------------------ name forms the store cannot resolve
    def bad_form(self, key: str) -> tuple[str, str, str] | None:
        """(name as the question writes it, retry mode, retry argument) with find_act(name) is None and the retry resolving."""
        a, t = self.acts[key], self.acts[key]["title"]
        num = (a["number"] or "").replace("‘", "'")
        cands = []
        if num and a["type"] != "vmq":
            kind = {
                "law": "Qonun",
                "pq": "Prezident qarori",
                "pf": "Prezident Farmoni",
                "ministry": "vazirlik buyrug'i",
            }.get(a["type"], "hujjat")
            cands += [
                (f"«{t}» {kind}i ({num}-son)", "number", num),
                (f"{kind} {num}-son", "number", num),
                (f"{t}, {kind.lower()} {num} sonli", "number", num),
            ]
        elif num:
            cands += [
                (f"Vazirlar Mahkamasining {num}-sonli qarori", "number", f"VMQ-{num}"),
                (f"VMQ {num}-son", "number", f"VMQ-{num}"),
                (f"VMQ-{num}-sonli qaror", "number", f"VMQ-{num}"),
            ]
        if a["type"] in ("code", "constitution") and "Respublikasining" in t:
            rest = t.replace("Oʻzbekiston Respublikasining ", "")
            cands += [
                (f"Oʻzbekiston Respublikasi {rest}", "search", rest),
                (f"{rest.capitalize()} (Oʻzbekiston Respublikasi)", "search", rest),
            ]
        if a["type"] == "code":
            rest = t.split()[-2:]
            cands += [(" ".join(rest).capitalize() + " 2.0", "search", " ".join(rest))]
        self.rng.shuffle(cands)
        for name, mode, arg in cands:
            if self.law.find_act(name) is None and self.law.find_act(arg if mode == "number" else t) == key:
                return name, mode, arg
        return None

    def recover(
        self, tr: Trace, key: str, bad: str, mode: str, arg: str, d: str, path: str, double: bool, story: dict
    ) -> str | None:
        """First call with the bad name fails (optionally list_editions fails too); retry by number or by search_law.
        Returns the act argument that works; story["think"] is the think for the next (successful) law_as_of call."""
        s, p = self.title(key), human_path(path)
        art = self.arg_art(path)
        res0 = tr.call(
            self.think.say("plan", "bad_name", s=s, p=p, d=d),
            "law_as_of",
            {"act": bad, "article": art, "date": d},
            self.law,
        )
        if "act not in the law store" not in res0.get("error", ""):
            return None
        if double:  # the same bad name fails once more, now in list_editions
            r = tr.call(self.think.say("read", "no_act"), "list_editions", {"act": bad}, self.law)
            if "act not in the law store" not in r.get("error", ""):
                return None
        story["route"] = mode
        if mode == "number":
            story["think"] = self.think.say("read", "retry_number", num=arg)
            return arg
        r = tr.call(
            self.think.say("read", "retry_search") if double else self.think.say("read", "no_act"),
            "search_law",
            {"query": arg, "date": d},
            self.law,
        )
        hits = r.get("hits", [])
        if not hits or hits[0]["act_key"] != key:
            return None
        story["think"] = self.think.say("read", "hit", k=key)
        return key

    # ------------------------------------------------------------------ dead_date and name_recover
    def dead_item(self, want: str, pick: str):
        """(key, path, date, lost, edition_gap ok) for want 'yo'q' (date after loss) or 'ha' (live, or dead but before loss)."""
        for _ in range(4000):
            if want == "yo'q" or (want == "ha" and pick == "dead_early"):
                key, path = self.dead[self.rng.randrange(len(self.dead))]
            else:
                key, path = self.live[self.rng.randrange(len(self.live))]
            if self.uses[(key, path)] >= PER_UNIT:
                continue
            vs = self.versions[(key, path)]
            lost = vs[-1][1] if want == "yo'q" or pick == "dead_early" else None
            if want == "yo'q":
                d = rand_date(self.rng, lost, None)
                if not d or d < lost:
                    continue
            elif pick == "dead_early":
                v = vs[self.rng.randrange(len(vs))]
                d = rand_date(self.rng, v[0], v[1])
                if not d or d >= lost:
                    continue
            else:
                v = vs[self.rng.randrange(len(vs))]
                d = rand_date(self.rng, v[0], v[1])
                if not d:
                    continue
            if self.law.edition_gap(key, d) is not None:
                continue
            got = self.law.get_unit(key, path, d)
            if (got is not None) != (want == "ha"):
                continue
            return key, path, d, lost
        return None

    def gen_dead(self, n: int, recover: bool) -> None:
        fam = "name_recover" if recover else "dead_date"
        done = {"yo'q": 0, "ha": 0}
        wants = ["yo'q", "ha"]
        guard = 0
        while sum(done.values()) < n and guard < 6000:
            guard += 1
            want = wants[sum(done.values()) % 2]
            if done[want] >= n // 2:
                want = "ha" if want == "yo'q" else "yo'q"
            pick = "dead_early" if (want == "ha" and done["ha"] % 2 == 1) else "live"
            it = self.dead_item(want, pick)
            if it is None:
                continue
            key, path, d, lost = it
            a, s, p = self.acts[key], self.title(key), human_path(path)
            tail = self.rng.choices(list(DATE_TAIL), weights=[5, 3, 1, 2])[0]
            li, ci = self.rng.randrange(len(DATE_LEAD)), self.rng.randrange(len(DATE_CORE))
            act_txt, _route = act_name(a), None
            bad = None
            if recover:
                bad = self.bad_form(key)
                if bad is None:
                    self.bad_names += 1
                    continue
                act_txt = bad[0]
            user = DATE_LEAD[li] + DATE_CORE[ci].format(a=act_txt, p=p, d=d) + " " + DATE_TAIL[tail]
            tr = Trace(SYSTEM, user, self.exam)
            act_arg = act_name(a)
            story: dict = {}
            if recover:
                good = self.recover(
                    tr, key, bad[0], bad[1], bad[2], d, path, double=self.rng.random() < 0.4, story=story
                )
                if good is None:
                    continue
                act_arg = good
                first_think = story["think"]
            else:
                first_think = self.think.say("plan", "date", s=s, p=p, d=d)
            res = tr.call(
                first_think, "law_as_of", {"act": act_arg, "article": self.arg_art(path), "date": d}, self.law
            )
            if want == "ha":
                if "text" not in res:
                    continue
                ed = res["edition"]
                final = "ha" if tail == "short" else f"ha, amalda (tahrir: {ed})"
                key_ = "live" if pick == "live" else "live_old"
                tr.answer(
                    self.think.say("read", key_, p=p, d=d, e=ed, vf=res["valid_from"]) + " Javob: ha.", final
                )
                item = {"family": "dead_cite", "verdict": "ha", "gold_date": None}
                sub = pick
            else:
                if "not found" not in res.get("error", ""):
                    continue
                found = self.locate_loss(tr, key, act_arg, path, d, lost)
                if found is None:
                    self.stats["drop_locate"] += 1
                    continue
                final = lost_phrase("iso", lost, tail)
                tr.answer(
                    self.think.say("read", "boundary", p=p, lo=self.last_lo, hi=lost) + f" Javob: yo'q, {lost}.",
                    final,
                )
                item = {"family": "dead_cite", "verdict": "yo'q", "gold_date": lost}
                sub = "dead"
            t = self.tag(fam, li, ci, tail, bad[0][:12] if recover else "")
            ok = self.emit(
                fam,
                tr,
                final,
                item,
                {
                    "act": key,
                    "path": path,
                    "date": d,
                    "lost": lost,
                    "sub": sub,
                    "tail": tail,
                    "recover": bool(recover),
                    "tpl": t,
                    "route": story.get("route"),
                },
            )
            if ok:
                done[want] += 1
                self.uses[(key, path)] += 1

    # ------------------------------------------------------------------ quote families
    def quote_item(self, trap: bool):
        pool = self.amended if trap else self.live
        for _ in range(3000):
            key, path = pool[self.rng.randrange(len(pool))]
            if self.uses[(key, path)] >= PER_UNIT:
                continue
            vs = self.versions[(key, path)]
            v = vs[self.rng.randrange(len(vs) - 1)] if trap else vs[self.rng.randrange(len(vs))]
            d = rand_date(self.rng, v[0], v[1])
            if not d or len(v[2]) < 90 or self.law.edition_gap(key, d) is not None:
                continue
            got = self.law.get_unit(key, path, d)
            if not got or norm(got["text"]) != norm(v[2]):
                continue
            if trap and norm(
                self.law.get_unit(key, path, TODAY)["text"] if self.law.get_unit(key, path, TODAY) else ""
            ) == norm(v[2]):
                continue
            return key, path, d, v
        return None

    def gen_chain(self, n: int) -> None:
        done = {"ha": 0, "yo'q": 0}
        guard = 0
        while sum(done.values()) < n and guard < 6000:
            guard += 1
            want = "ha" if sum(done.values()) % 2 == 0 else "yo'q"
            if done[want] >= n // 2:
                want = "yo'q" if want == "ha" else "ha"
            li, ci = self.rng.randrange(len(DATE_LEAD)), self.rng.randrange(len(CHAIN_CORE))
            if want == "ha":
                it = self.quote_item(trap=True)
                if it is None:
                    continue
                key, path, d, _v = it
                a, s, p = self.acts[key], self.title(key), human_path(path)
                user = DATE_LEAD[li] + CHAIN_CORE[ci].format(a=act_name(a), p=p, d=d)
                tr = Trace(SYSTEM, user, self.exam)
                args = {"act": act_name(a), "article": self.arg_art(path), "date": d}
                res = tr.call(self.think.say("plan", "quote", s=s, p=p, d=d), "law_as_of", args, self.law)
                if "text" not in res:
                    continue
                q = quote_of(res["text"], self.rng, 60, 200)
                vr = tr.call(
                    self.think.say(
                        "read",
                        "quote",
                        p=p,
                        d=d,
                        e=res["edition"],
                        vf=res["valid_from"],
                        vt=res["valid_to"] or TODAY,
                    ),
                    "verify_quote",
                    {**args, "quote": q},
                    self.law,
                )
                if not vr.get("ok"):
                    continue
                final = "Ha. " + q
                tr.answer(self.think.say("read", "verified"), final)
                item = {"family": "chain", "verdict": "ha", "answer": res["text"]}
                tags = {"act": key, "path": path, "date": d, "trap": True, "sub": "quote"}
                tags["tpl"] = self.tag("chain_date", li, ci, "ha")
                if self.emit("chain_date", tr, final, item, tags):
                    done["ha"] += 1
                    self.uses[(key, path)] += 1
            else:
                it = self.dead_item("yo'q", "dead")
                if it is None:
                    continue
                key, path, d, lost = it
                a, s, p = self.acts[key], self.title(key), human_path(path)
                ask_date = self.rng.random() < 0.7
                user = (
                    DATE_LEAD[li]
                    + CHAIN_CORE[ci].format(a=act_name(a), p=p, d=d)
                    + (CHAIN_ASK_DATE if ask_date else "")
                )
                tr = Trace(SYSTEM, user, self.exam)
                res = tr.call(
                    self.think.say("plan", "quote", s=s, p=p, d=d),
                    "law_as_of",
                    {"act": act_name(a), "article": self.arg_art(path), "date": d},
                    self.law,
                )
                if "not found" not in res.get("error", ""):
                    continue
                if ask_date:
                    found = self.locate_loss(tr, key, act_name(a), path, d, lost)
                    if found is None:
                        self.stats["drop_locate"] += 1
                        continue
                    final = f"yo'q, kuchini yo'qotgan sana: {lost}"
                    tr.answer(
                        self.think.say("read", "boundary", p=p, lo=self.last_lo, hi=lost)
                        + f" Javob: yo'q, {lost}.",
                        final,
                    )
                else:
                    r2 = tr.call(
                        self.think.say("read", "nf", p=p, d=d),
                        "list_editions",
                        {"act": act_name(a)},
                        self.law,
                    )
                    if "editions" not in r2:
                        continue
                    final = "yo'q"
                    tr.answer(
                        self.think.say("read", "eds", n=len(r2["editions"]), d=d, cur="?") + " Javob: yo'q.",
                        final,
                    )
                item = {"family": "chain", "verdict": "yo'q", "answer": ""}
                tags = {
                    "act": key,
                    "path": path,
                    "date": d,
                    "lost": lost,
                    "sub": "dead",
                    "ask_date": ask_date,
                    "tpl": self.tag("chain_date", li, ci, "yo'q", ask_date),
                }
                if self.emit("chain_date", tr, final, item, tags):
                    done["yo'q"] += 1
                    self.uses[(key, path)] += 1

    def gen_recover_quote(self, n: int) -> None:
        done, guard = 0, 0
        while done < n and guard < 6000:
            guard += 1
            it = self.quote_item(trap=done % 2 == 0)
            if it is None:
                continue
            key, path, d, _v = it
            bad = self.bad_form(key)
            if bad is None:
                continue
            _a, _s, p = self.acts[key], self.title(key), human_path(path)
            li, ci = self.rng.randrange(len(DATE_LEAD)), self.rng.randrange(len(QUOTE_CORE))
            user = DATE_LEAD[li] + QUOTE_CORE[ci].format(a=bad[0], p=p, d=d)
            tr = Trace(SYSTEM, user, self.exam)
            story: dict = {}
            good = self.recover(tr, key, bad[0], bad[1], bad[2], d, path, double=False, story=story)
            if good is None:
                continue
            args = {"act": good, "article": self.arg_art(path), "date": d}
            res = tr.call(story["think"], "law_as_of", args, self.law)
            if "text" not in res:
                continue
            q = quote_of(res["text"], self.rng, 60, 200)
            tr.answer(
                self.think.say(
                    "read",
                    "quote",
                    p=p,
                    d=d,
                    e=res["edition"],
                    vf=res["valid_from"],
                    vt=res["valid_to"] or TODAY,
                ),
                q,
            )
            item = {"family": "lookup", "answer": res["text"]}
            tags = {
                "act": key,
                "path": path,
                "date": d,
                "route": story["route"],
                "tpl": self.tag("name_recover_quote", li, ci, bad[0][:12]),
            }
            if self.emit("name_recover_quote", tr, q, item, tags, g=grade_v1):
                done += 1
                self.uses[(key, path)] += 1


# ---------------------------------------------------------------------------------------------- v1 filtering and gates
def v1_leaks(row: dict, arts: set, regs: set) -> bool:
    blob = json.dumps(row["messages"], ensure_ascii=False)
    if any(g in blob for g in regs):
        return True
    for m in row["messages"]:
        if m["role"] != "tool":
            continue
        try:
            body = json.loads(m["content"])
        except ValueError:
            continue
        for h in [body, *body.get("hits", [])]:
            if isinstance(h, dict) and (h.get("act_key"), art_root(h.get("path", ""))) in arts:
                return True
    return False


def v2_gates(rows: list[dict], think: Think) -> list[str]:
    fails = []
    n = len(rows)
    for fam in NEW_FAMILIES:
        fr = [r for r in rows if r["family"] == fam]
        if fam in ("dead_date", "name_recover", "chain_date"):
            c = Counter("ha" if r["final"].lower().startswith("ha") else "yo'q" for r in fr)
            if fr and not all(0.45 <= c[k] / len(fr) <= 0.55 for k in ("ha", "yo'q")):
                fails.append(f"{fam} class balance {dict(c)}")
        else:
            c2 = Counter(r["final"] for r in fr)
            if fr and max(c2.values()) / len(fr) > 0.02:
                fails.append(f"{fam} identical answer above 2 %")
    t = Counter(r["tags"]["tpl"] for r in rows)
    if t and max(t.values()) / n > 0.03:
        fails.append(f"a prompt template above 3 %: {t.most_common(1)}")
    for kind, cnt in think.used.items():
        tot = sum(cnt.values())
        if tot and max(cnt.values()) / tot > 0.03:
            fails.append(f"a {kind} think template above 3 %")
    if len({r["messages"][1]["content"] for r in rows}) != n:
        fails.append("duplicate prompts")
    return fails


def main() -> None:
    arts, regs, nfiles = load_leak_sets()
    print(
        f"leak sets from {nfiles} files: {len(arts)} (act, article) pairs, {len(regs)} registration numbers",
        flush=True,
    )
    b = V2(2112, arts)
    print(f"pool: dead units {len(b.dead)}, live {len(b.live)}, amended live {len(b.amended)}", flush=True)
    b.gen_dead(TARGET["dead_date"], recover=False)
    b.gen_dead(TARGET["name_recover"], recover=True)
    b.gen_recover_quote(TARGET["name_recover_quote"])
    b.gen_chain(TARGET["chain_date"])
    new = b.rows
    c = Counter(r["family"] for r in new)
    print("new rows", len(new), dict(c), "drops", dict(b.stats), "no bad-name form", b.bad_names, flush=True)
    fails = v2_gates(new, b.think)
    print("NEW GATES:", "pass" if not fails else fails)
    if fails:
        raise SystemExit("gate failure: nothing written")
    # split new rows: 10 % to val, stratified by family and answer class
    train_new, val_new = [], []
    byfam = defaultdict(list)
    for r in new:
        byfam[r["family"]].append(r)
    for fam, rs in byfam.items():
        by_cls = defaultdict(list)
        for r in rs:
            by_cls["ha" if r["final"].lower().startswith("ha") else "other"].append(r)
        for cls_rows in by_cls.values():
            b.rng.shuffle(cls_rows)
            k = max(1, round(0.10 * len(cls_rows)))
            val_new += cls_rows[:k]
            train_new += cls_rows[k:]
    v1_train = [json.loads(x) for x in V1_TRAIN.read_text(encoding="utf-8").split("\n") if x.strip()]
    v1_val = [json.loads(x) for x in V1_VAL.read_text(encoding="utf-8").split("\n") if x.strip()]
    keep_t = [r for r in v1_train if not v1_leaks(r, arts, regs)]
    keep_v = [r for r in v1_val if not v1_leaks(r, arts, regs)]
    print(
        f"v1 train {len(v1_train)} -> {len(keep_t)} kept ({len(v1_train) - len(keep_t)} leak-dropped); "
        f"v1 val {len(v1_val)} -> {len(keep_v)}",
        flush=True,
    )
    # the audit slice shrinks under the new leak control: balance its verdicts as far as the survivors allow
    au = [r for r in keep_t if r["family"] == "audit"]
    vc = Counter(r["verdict"] for r in au)
    cap_pos = max(vc.get("negative", 0), 1) + 1
    drop_ids, seen_pos = set(), 0
    for r in au:
        if r["verdict"] == "positive":
            seen_pos += 1
            if seen_pos > cap_pos:
                drop_ids.add(id(r))
    print(f"audit rows after leak control {dict(vc)}; positive capped at {cap_pos} ({len(drop_ids)} dropped)")
    keep_t = [r for r in keep_t if id(r) not in drop_ids]
    fam_drop = Counter(r["family"] for r in v1_train if v1_leaks(r, arts, regs))
    print("v1 train leak-dropped by family", dict(fam_drop))
    # the same leak control on the new families (a search hit can surface a bench article; audit rows are exempt)
    def _new_leaks(r):
        return r["family"] not in ("audit", "audit_dev") and v1_leaks(r, arts, regs)
    n0 = len(train_new) + len(val_new)
    train_new = [r for r in train_new if not _new_leaks(r)]
    val_new = [r for r in val_new if not _new_leaks(r)]
    print(f"new-family leak-dropped: {n0 - len(train_new) - len(val_new)}")
    train = keep_t + train_new
    f1 = I.check_gates(train, None)
    waived = [f for f in f1 if f.startswith("audit verdict above 35 %")]  # cannot hold with the few audit rows left
    f1 = [f for f in f1 if f not in waived]
    print("V1 GATES ON COMBINED:", "pass" if not f1 else f1, "| waived (audit mix, tiny slice):", waived)
    if f1:
        raise SystemExit("v1 gate failure on the combined file: nothing written")
    b.rng.shuffle(train)
    val = keep_v + val_new
    for path, rows in ((OUT_TRAIN, train), (OUT_VAL, val)):
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"wrote {OUT_TRAIN} ({len(train)} rows; new {len(train_new)})")
    print(f"wrote {OUT_VAL} ({len(val)} rows; new {len(val_new)})")
    for fam in NEW_FAMILIES:
        fr = [r for r in new if r["family"] == fam]
        print(
            fam,
            len(fr),
            "calls",
            dict(sorted(Counter(r["calls"] for r in fr).items())),
            "answers",
            dict(Counter(r["final"][:3] for r in fr).most_common(3)),
        )
    dd = Counter(r["final"] for r in new if r["final"].startswith("yo'q,"))
    print(
        "dead-date answers: distinct",
        len(dd),
        "max identical",
        max(dd.values()) if dd else 0,
        "of",
        sum(dd.values()),
    )
    print(
        "max prompt template share", f"{max(Counter(r['tags']['tpl'] for r in new).values()) / len(new):.2%}"
    )


if __name__ == "__main__":
    main()
