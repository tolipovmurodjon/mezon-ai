"""MezonBench v2.2 = v2.1 with its answer-key bugs fixed + three new families (gold from the law store, a priori).

    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v22 build      # writes public, private, FROZEN_v2_2.json
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v22 oracle
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v22 score preds.jsonl
    .venv/Scripts/python.exe -X utf8 -m research.mezonbench_v22 regrade     # old v2.1 prediction files on shared v2.2 items

Fixes to v2.1 items (counts in the FROZEN changelog): conflict_pair different-force pairs accept NLA art. 6 or 18;
noaniq future-date items state "Bugun 2026-11-21" (items whose act has a stored edition after today are dropped);
noaniq edition_gap items dropped (the tools return a text for them); cancel_trigger items whose decision text the
get_decision tool cannot return are dropped. New families (never selected by any model's score):
edition_timeline, two_hop, conflict_dated. Never train on v2.2.
"""

import argparse
import hashlib
import inspect
import json
import random
import re
import sqlite3  # noqa: F401
from collections import Counter, defaultdict
from pathlib import Path

from mezon.config import LAW_DB
from mezon.decisions.store import DecisionStore
from mezon.lawstore.store import LawStore
from mezon.tools import call
from research import mezonbench as mb
from research import mezonbench_v2 as v2
from research.textnorm import fold

BENCH = v2.BENCH
PUBLIC = BENCH / "mezonbench_v2_2.jsonl"
PRIVATE = BENCH / "private" / "mezonbench_v2_2_private.jsonl"
FROZEN = BENCH / "FROZEN_v2_2.json"
NEW_FAMS = ("edition_timeline", "two_hop", "conflict_dated")
FAMS = tuple(v2.SIZES) + NEW_FAMS
SEED = v2.SEED + 22
TODAY = v2.TODAY
REF = f"Bugun {TODAY}. "
EXTRA_ACTS = [
    "Suv kodeksi",
    "Soliq maslahatchilari toʻgʻrisidagi qonun",
    "Notariat toʻgʻrisidagi qonun",
    "Advokatura toʻgʻrisidagi qonun",
    "Raqobat toʻgʻrisidagi qonun",
    "Bank faoliyati toʻgʻrisidagi qonun",
    "Yoʻl harakati xavfsizligi toʻgʻrisidagi qonun",
    "Sogʻliqni saqlash toʻgʻrisidagi qonun",
    "Mehnatni muhofaza qilish toʻgʻrisidagi qonun",
    "Oʻrmon kodeksi",
    "Mudofaa toʻgʻrisidagi qonun",
    "Valyutani tartibga solish toʻgʻrisidagi qonun",
    "Sugʻurta faoliyati toʻgʻrisidagi qonun",
    "Gaz taʼminoti toʻgʻrisidagi qonun",
    "Turizm toʻgʻrisidagi qonun",
    "Mehnat migratsiyasi toʻgʻrisidagi qonun",
    "Aholini ish bilan taʼminlash toʻgʻrisidagi qonun",
]
_NUM = {"nol": 0, "hech": 0, "bir": 1, "ikki": 2, "uch": 3, "tort": 4, "besh": 5, "olti": 6}


def number_of(answer: str) -> int | None:
    t = re.sub(r"(?:19|20)\d\d-\d\d-\d\d|\d{1,2}[./]\d{1,2}[./](?:19|20)\d\d", " ", answer or "")
    for m in re.finditer(r"\d+|[a-z']+", fold(t)):
        w = m.group(0)
        v = int(w) if w.isdigit() else _NUM.get(w)
        if v is not None:
            return v
    return None


def grade(item: dict, answer: str) -> str:
    """v2.2 grader: v2.1 grader plus the accepted-article set for different-force pairs and the three new families."""
    a = (answer or "").strip()
    fam = item["family"]
    if fam not in NEW_FAMS and not (fam == "conflict_pair" and item.get("nla_accept")):
        return v2.grade(item, a)
    if "noaniq" in fold(a):
        return "abstain"
    if fam == "conflict_pair":
        if v2.letter_of(a) != item["verdict"]:
            return "wrong"
        pat = "|".join(item["nla_accept"])
        return (
            "right"
            if re.search(rf"(?<![\d-])(?:{pat})[\s-]*(modda|модда|статья|статьи)", a.lower())
            else "wrong"
        )
    if fam == "conflict_dated":
        return "right" if v2.letter_of(a) == item["verdict"] else "wrong"
    if fam == "two_hop":
        ok = v2.verdict_of(a) == item["verdict"] and item["gold_date"] in v2.dates_in(a)
        return "right" if ok else "wrong"
    if item["task"] == "edition_on":
        return "right" if item["gold_date"] in v2.dates_in(a) else "wrong"
    return "right" if number_of(a) == item["gold_n"] else "wrong"


def oracle_answer(item: dict) -> str:
    if item["family"] == "two_hop":
        return f"{item['verdict']}, {item['gold_date']}"
    if item["family"] == "conflict_pair" and item.get("nla_accept"):
        return f"{item['verdict']}, {item['nla_accept'][-1]}-modda"
    if item["family"] in NEW_FAMS:
        return item["answer"]
    return v2.oracle_answer(item)


# ---------------------------------------------------------------- fixes to v2.1


def fix_v21(law: LawStore, ds: DecisionStore, items: list[dict]) -> tuple[list[dict], Counter]:
    log: Counter = Counter()
    out = []
    for it in items:
        it = dict(it)
        if it["family"] == "conflict_pair":
            if it.get("rule", "").startswith("different_force"):
                it["nla_accept"] = ["6", "18"]
                it["answer"] = it["answer"].replace("6-modda", "6-modda yoki 18-modda")
                log["conflict_pair: different-force pairs now accept art. 6 or 18"] += 1
            else:
                it["nla_accept"] = ["18"]
        if it["family"] == "cancel_trigger":
            r = call("get_decision", {"reg": it["reg"]}, law, ds)
            if "error" in r or len(r.get("text") or "") < 200:
                log["cancel_trigger: DROPPED, get_decision cannot return the text"] += 1
                continue
            log["cancel_trigger: kept, text retrievable by get_decision"] += 1
        if it["family"] == "noaniq":
            why = it["why"]
            if why == "edition_gap":
                log["noaniq: edition_gap DROPPED (law_as_of returns a text for the date)"] += 1
                continue
            if why == "date_after_store_end":
                r = call("list_editions", {"act": it["act"]}, law)
                if any(d > TODAY for d in r["editions"]):
                    log["noaniq: future item DROPPED (act has a stored edition after today)"] += 1
                    continue
                it["prompt"] = REF + it["prompt"]
                it["reference_date"] = TODAY
                log["noaniq: future item kept, reference date stated in the question"] += 1
            else:
                if law.find_act(it["act_name"]) is not None:
                    log["noaniq: act_not_in_store DROPPED (act found)"] += 1
                    continue
                log["noaniq: act_not_in_store kept (find_act None)"] += 1
        out.append(it)
    return out, log


def new_noaniq(law: LawStore, rng: random.Random, n: int, start: int) -> list[dict]:
    names = [x for x in EXTRA_ACTS if law.find_act(x) is None]
    items = []
    for i in range(n):
        nm = names[i % len(names)]
        on = mb.rand_date(rng, "2022-01-01", "2026-10-31")
        art = rng.randint(1, 40)
        items.append(
            {
                "id": f"noaniq-{start + i:03d}",
                "family": "noaniq",
                "system": v2.SYSTEM,
                "prompt": f"«{nm}» {art}-modda {on} holatida qanday edi? Matn boshidan kamida 60 belgini aynan "
                f"(so'zma-so'z) keltiring.",
                "answer": "noaniq",
                "verdict": "noaniq",
                "date": on,
                "why": "act_not_in_store",
                "act_name": nm,
                "recent": on >= mb.RECENT,
            }
        )
    return items


def new_future(law: LawStore, rng: random.Random, n: int, start: int, old: list[dict]) -> list[dict]:
    """Future-date items on fresh live articles of acts with no stored edition after today; reference date stated."""
    b = v2.Builder(LAW_DB)
    seen = {(i.get("act"), i.get("path")) for i in old}
    cand = [
        r
        for r in b.con.execute(
            "SELECT act_key, path FROM units WHERE valid_to IS NULL AND path LIKE 'art:%' "
            "AND path NOT LIKE '%/%' AND length(text) >= 80"
        )
        if (r["act_key"], r["path"]) not in seen
        and (r["act_key"], r["path"]) not in b.exact
        and (r["act_key"], v2.art_of(r["path"])) not in b.arts
        and not re.search(r"[а-я]{4}", b.acts[r["act_key"]]["title"])
        and not any(e["valid_from"] > TODAY for e in law.editions(r["act_key"]))
    ]
    rng.shuffle(cand)
    items = []
    for r in cand[:n]:
        on = (mb.date(2026, 12, 1) + mb.timedelta(days=rng.randint(0, 395))).isoformat()
        a = b.acts[r["act_key"]]
        items.append(
            {
                "id": f"noaniq-{start + len(items):03d}",
                "family": "noaniq",
                "system": v2.SYSTEM,
                "prompt": REF
                + f"{mb.act_name(a)} {mb.human_path(r['path'])} {on} kuni amalda bo'lganmi (shu raqam "
                f'bilan mavjud edimi)? Faqat "ha" yoki "yo\'q" deb javob bering.',
                "answer": "noaniq",
                "verdict": "noaniq",
                "date": on,
                "why": "date_after_store_end",
                "act": r["act_key"],
                "path": r["path"],
                "reference_date": TODAY,
                "recent": True,
            }
        )
    return items


# ---------------------------------------------------------------- new families


class New(v2.Builder):
    def __init__(self, store: Path, taken_regs: set):
        super().__init__(store)
        self.taken = taken_regs
        self.rows: list[dict] = []

    def put(self, family: str, prompt: str, answer: str, **meta) -> None:
        n = sum(r["family"] == family for r in self.rows) + 1
        self.rows.append(
            {
                "id": f"{family}-{n:03d}",
                "family": family,
                "system": v2.SYSTEM,
                "prompt": prompt,
                "answer": answer,
                **meta,
            }
        )

    def dense_start(self, key: str) -> str:
        eds = sorted(e["valid_from"] for e in self.law.editions(key))
        return eds[1] if len(eds) > 1 else TODAY  # a skipped stretch, if any, follows the first edition

    def timeline(self, size: int = 60) -> None:
        acts = []
        for key, a in sorted(self.acts.items()):
            if re.search(r"[а-я]{4}", a["title"]):
                continue
            eds = sorted(e["valid_from"] for e in self.law.editions(key) if e["valid_from"] <= TODAY)
            if len(eds) >= 5:
                acts.append((key, eds))
        third = size // 3
        task_n = lambda t: sum(r.get("task") == t for r in self.rows)
        for _ in range(4000):
            if task_n("edition_on") >= third:
                break
            key, eds = self.rng.choice(acts)
            d = mb.rand_date(self.rng, self.dense_start(key), TODAY)
            ed = self.law.edition_on(key, d) if d else None
            if not ed or self.law.edition_gap(key, d) or ed["valid_from"] == d:
                continue
            if sum(r.get("act") == key and r.get("task") == "edition_on" for r in self.rows) >= 3:
                continue
            self.put(
                "edition_timeline",
                f"{mb.act_name(self.acts[key])} {d} kuni qaysi tahrirda amalda edi? "
                f"O'sha tahrir kuchga kirgan sanani YYYY-MM-DD shaklida yozing.",
                ed["valid_from"],
                task="edition_on",
                act=key,
                date=d,
                gold_date=ed["valid_from"],
                verdict=ed["valid_from"],
                recent=d >= mb.RECENT,
            )
        want: Counter = Counter()
        cap = {0: third // 4, 1: third // 4, 2: third // 4, 3: third - 3 * (third // 4)}
        for _ in range(20000):
            if task_n("n_editions") >= third:
                break
            key, eds = self.rng.choice(acts)
            d1 = mb.rand_date(self.rng, self.dense_start(key), TODAY)
            d2 = mb.rand_date(self.rng, d1, TODAY) if d1 else None
            if not d1 or not d2 or d1 >= d2:
                continue
            n = sum(d1 < e <= d2 for e in eds)
            b = min(n, 3)
            if (
                want[b] >= cap[b]
                or sum(r.get("act") == key and r.get("task") == "n_editions" for r in self.rows) >= 3
            ):
                continue
            want[b] += 1
            self.put(
                "edition_timeline",
                f"{mb.act_name(self.acts[key])}: {d1} dan keyin va {d2} gacha (shu sana "
                f"kiritilgan) nechta yangi tahrir kuchga kirgan? Faqat son yozing.",
                str(n),
                task="n_editions",
                act=key,
                date=d2,
                date_from=d1,
                gold_n=n,
                verdict=str(n),
                recent=d2 >= mb.RECENT,
            )
        cl = defaultdict(set)
        for r in self.con.execute("SELECT act_key, path, effective_date FROM change_log"):
            cl[(r["act_key"], v2.art_of(r["path"]))].add(r["effective_date"])
        live_acts = {k for k, _ in acts}
        arts = sorted(k for k in cl if k[0] in live_acts and re.fullmatch(r"art:\d+(?:-\d+)?", k[1]))
        want = Counter()
        capc = {0: third // 3, 1: third // 3, 2: third - 2 * (third // 3)}
        for _ in range(40000):
            if task_n("n_art_changes") >= third:
                break
            key, path = self.rng.choice(arts)
            d1 = mb.rand_date(self.rng, self.dense_start(key), TODAY)
            d2 = mb.rand_date(self.rng, d1, TODAY) if d1 else None
            if not d1 or not d2 or d1 >= d2:
                continue
            n = sum(d1 < e <= d2 for e in cl[(key, path)])
            b = min(n, 2)
            if want[b] >= capc[b] or any(r.get("act") == key and r.get("path") == path for r in self.rows):
                continue
            want[b] += 1
            self.put(
                "edition_timeline",
                f"{mb.act_name(self.acts[key])} {mb.human_path(path)}: {d1} dan keyin va "
                f"{d2} gacha (shu sana kiritilgan) nechta yangi tahrirda shu moddaning matni (yoki uning qismlari) "
                f"o'zgargan, qo'shilgan yoki chiqarilgan? Faqat son yozing.",
                str(n),
                task="n_art_changes",
                act=key,
                path=path,
                date=d2,
                date_from=d1,
                gold_n=n,
                verdict=str(n),
                recent=d2 >= mb.RECENT,
            )
        self.shuffle_rows("edition_timeline")

    def shuffle_rows(self, fam: str) -> None:
        mine = [r for r in self.rows if r["family"] == fam]
        rest = [r for r in self.rows if r["family"] != fam]
        self.rng.shuffle(mine)
        for n, it in enumerate(mine, 1):
            it["id"] = f"{fam}-{n:03d}"
        self.rows = rest + mine

    def two_hop(self, size: int = 60) -> None:
        live, _dead = self.decision_pool()
        self.rng.shuffle(live)
        cnt: Counter = Counter()
        per_art: Counter = Counter()
        for rec in live:
            if sum(cnt.values()) >= size:
                break
            d, on = rec["d"], rec["d"]["adopted"]
            reg = d["reg_number"]
            if reg in self.taken or per_art[(rec["key"], rec["path"])] >= (6 if rec["path"] else 3):
                continue
            then = self.article_text(rec["key"], rec["path"], on)
            now = self.article_text(rec["key"], rec["path"], TODAY)
            if not then or not now or len(mb.norm(then)) < 60:
                continue
            differ = mb.norm(then) != mb.norm(now)
            if cnt[differ] >= size // 2:
                continue
            ed = self.law.edition_on(rec["key"], on)
            cnt[differ] += 1
            per_art[(rec["key"], rec["path"])] += 1
            self.taken.add(reg)
            verdict = "ha" if differ else "yo'q"
            self.put(
                "two_hop",
                self.decision_prompt(
                    rec,
                    f"matni qaror qabul qilingan kundagi tahrirda bugungi ({TODAY}) tahriridan farq qilganmi? Avval "
                    f'"ha" yoki "yo\'q" deb yozing, so\'ng qaror kuni amalda bo\'lgan tahrir kuchga kirgan sanani '
                    f"YYYY-MM-DD shaklida yozing.",
                ),
                f"{verdict}, {ed['valid_from']}",
                reg=reg,
                act=rec["key"],
                path=rec["path"],
                verdict=verdict,
                gold_date=ed["valid_from"],
                date=on,
                recent=on >= mb.RECENT,
                overlap_v1=(rec["key"], rec["path"]) in self.exact,
                reuses_v21_decision=reg in self.used21,
            )
        self.shuffle_rows("two_hop")

    def conflict_dated(self, size: int = 60) -> None:
        rows = self.con.execute(
            "SELECT act_key, path, text, valid_from, valid_to FROM units WHERE path LIKE 'art:%' "
            "AND path NOT LIKE '%/%' AND length(text) BETWEEN 100 AND 700"
        ).fetchall()
        rows = [
            r for r in rows if not re.search(r"[а-я]{4}", self.acts[r["act_key"]]["title"] + r["text"][:200])
        ]
        dense = {k: self.dense_start(k) for k in self.acts}
        quota = size // 4
        got: Counter = Counter()
        per_act: Counter = Counter()

        def state(key, path, d):
            if self.law.edition_on(key, d) is None:
                return "none"
            return "in" if self.law.in_force(key, d)[0] and self.law.get_unit(key, path, d) else "out"

        def tag(r):
            return f"{mb.act_name(self.acts[r['act_key']])} {mb.human_path(r['path'])}: «{v2.clip(r['text'], 230)}»"

        def window(r):
            """dates on which this unit is outside its life (not yet added / already gone), inside the dense store"""
            lo = dense[r["act_key"]]
            if r["valid_from"] > lo:
                return lo, (v2.mb.date.fromisoformat(r["valid_from"]) - v2.mb.timedelta(days=1)).isoformat()
            if r["valid_to"] and r["valid_to"] <= TODAY:
                return r["valid_to"], TODAY
            return None

        usedrows: set = set()
        outrows = [r for r in rows if window(r) and window(r)[0] < window(r)[1]]
        for _ in range(200000):
            if sum(got.values()) >= size or sum(got.values()) >= 9 + 3 * quota:
                break
            kind = self.rng.choice("ABCD")
            if got[kind] >= (9 if kind == "C" else quota):
                continue
            if kind == "C":
                x, y = self.rng.choice(rows), self.rng.choice(rows)
                d = mb.rand_date(self.rng, max(dense[x["act_key"]], dense[y["act_key"]]), TODAY)
            else:
                o = self.rng.choice(outrows)
                w = window(o)
                d = mb.rand_date(self.rng, *w)
                if kind == "D":
                    mates = [
                        r
                        for r in outrows
                        if r["act_key"] != o["act_key"] and window(r)[0] <= (d or "") <= window(r)[1]
                    ]
                    if not d or not mates:
                        continue
                    x, y = o, self.rng.choice(mates)
                else:
                    other = self.rng.choice(rows)
                    # kind A: x in force, y out -> y is the out row; kind B: x out, y in
                    x, y = (other, o) if kind == "A" else (o, other)
            if (
                not d
                or x["act_key"] == y["act_key"]
                or per_act[x["act_key"]] >= 9
                or per_act[y["act_key"]] >= 9
                or (x["act_key"], x["path"]) in usedrows
                or (y["act_key"], y["path"]) in usedrows
            ):
                continue
            if self.law.edition_gap(x["act_key"], d) or self.law.edition_gap(y["act_key"], d):
                continue
            sx, sy = state(x["act_key"], x["path"], d), state(y["act_key"], y["path"], d)
            if "none" in (sx, sy):
                continue
            if any(
                s_ == "out" and not (r["valid_from"] > d or (r["valid_to"] and r["valid_to"] <= d))
                for s_, r in ((sx, x), (sy, y))
            ):
                continue
            verdict = {("in", "in"): "C", ("in", "out"): "A", ("out", "in"): "B", ("out", "out"): "D"}[
                (sx, sy)
            ]
            if verdict != kind:
                continue
            got[kind] += 1
            per_act[x["act_key"]] += 1
            per_act[y["act_key"]] += 1
            usedrows.update({(x["act_key"], x["path"]), (y["act_key"], y["path"])})
            self.put(
                "conflict_dated",
                f"Ikki norma bir masalani turlicha tartibga soladi.\nA) {tag(x)}\nB) {tag(y)}\nNizo {d} sanasida "
                f"yuzaga keldi. O'sha sanada qaysi norma kuchda edi (shu raqam bilan mavjud va kuchini yo'qotmagan)?\n"
                f"A, B, C (ikkalasi ham kuchda edi) yoki D (hech biri kuchda emas edi)? Faqat harfni yozing.",
                verdict,
                a=x["act_key"],
                a_path=x["path"],
                b=y["act_key"],
                b_path=y["path"],
                verdict=verdict,
                date=d,
                recent=d >= mb.RECENT,
            )
        self.shuffle_rows("conflict_dated")


# ---------------------------------------------------------------- split, build, score


def stratum(it: dict) -> str:
    if it["family"] == "edition_timeline":
        return f"{it['task']}:{min(it.get('gold_n', 0), 3)}"
    return v2.stratum(it)


def split_new(items: list[dict], share: float = v2.PRIVATE_SHARE) -> set:
    rng = random.Random(SEED)
    priv: set = set()
    for fam in FAMS:
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
            priv |= {x["id"] for x in v[: take[k]]}
    return priv


def build() -> None:
    law, ds = LawStore(), DecisionStore()
    old = v2.load_split("both")
    pub_ids = {i["id"] for i in v2.load(v2.OUT_V21)}
    fixed, log = fix_v21(law, ds, old)
    dropped_na = (Counter(i["family"] for i in old) - Counter(i["family"] for i in fixed)).get("noaniq", 0)
    na_ids = [int(i["id"].split("-")[1]) for i in old if i["family"] == "noaniq"]
    n_fut = dropped_na // 3
    fresh = new_noaniq(law, random.Random(SEED), dropped_na - n_fut, max(na_ids) + 1)
    fresh += new_future(law, random.Random(SEED + 1), n_fut, max(na_ids) + 1 + len(fresh), old)
    log["noaniq: replacement act_not_in_store items added (unlisted acts, find_act None)"] = len(fresh)
    taken = set(
        v2.GOLDEN
    )  # v2.1 decisions may be re-asked a different question (flagged "reuses_v21_decision")
    used21 = {i.get("reg") for i in old if i.get("reg")}
    b = New(LAW_DB, taken)
    b.used21 = used21
    b.timeline()
    b.two_hop()
    b.conflict_dated()
    added = fresh + b.rows
    priv = split_new(added)
    public, held = [], []
    for it in fixed:
        (public if it["id"] in pub_ids else held).append(
            {**it, "split": "public" if it["id"] in pub_ids else "private"}
        )
    for it in added:
        (held if it["id"] in priv else public).append(
            {**it, "split": "private" if it["id"] in priv else "public"}
        )
    v2.write_jsonl(PUBLIC, public)
    v2.write_jsonl(PRIVATE, held)
    changelog = dict(log)
    changelog["new family items (all splits)"] = dict(Counter(i["family"] for i in b.rows))
    changelog["v2.1 items in / kept"] = f"{len(old)} / {len(fixed)}"
    grader_src = "".join(inspect.getsource(f) for f in (number_of, grade, oracle_answer))
    man = {
        "frozen": "2026-11-21 Tashkent",
        "version": "v2.2 (v2.1 answer-key fixes + edition_timeline, two_hop, conflict_dated)",
        "items": {
            p.name: {
                "split": s,
                "n": len(x),
                "sha256_16": v2.sha(p),
                "families": dict(Counter(i["family"] for i in x)),
            }
            for p, s, x in ((PUBLIC, "public", public), (PRIVATE, "private", held))
        },
        "grader_sha256_16": hashlib.sha256((grader_src + inspect.getsource(v2.grade)).encode()).hexdigest()[
            :16
        ],
        "code_sha256_16": {
            p: v2.sha(v2.ROOT / p)
            for p in (
                "research/mezonbench_v22.py",
                "research/mezonbench_v2.py",
                "mezon/tools.py",
                "mezon/lawstore/store.py",
            )
        },
        "law_store_sha256_16": v2.sha(LAW_DB),
        "decision_store_sha256_16": v2.sha(v2.ROOT / "data" / "store" / "decisions.sqlite"),
        "changelog_v2_1_to_v2_2": changelog,
        "rules": "Never train on v2.2. Private part never shared. New families were drawn a priori from the store; "
        "no item was selected by any model's answer. Changing an item/grader/tool/store = v2.3.",
    }
    FROZEN.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(changelog, indent=1, ensure_ascii=False))
    print(f"public {len(public)} {dict(Counter(i['family'] for i in public))}")
    print(f"private {len(held)} {dict(Counter(i['family'] for i in held))}")


def load_all(split: str = "both") -> list[dict]:
    items = v2.load(PUBLIC) if split in ("public", "both") else []
    return items + (v2.load(PRIVATE) if split in ("private", "both") else [])


def oracle() -> None:
    for part in ("public", "private", "both"):
        items = load_all(part)
        g = Counter(grade(i, oracle_answer(i)) for i in items)
        print(f"oracle {part}: {dict(g)} of {len(items)}")
    items = load_all()
    for fam in NEW_FAMS + ("noaniq", "conflict_pair"):
        sub = [i for i in items if i["family"] == fam]
        consts = {
            c: sum(grade(i, c) == "right" for i in sub)
            for c in ["ha", "yo'q", "A", "B", "C", "D", "0", "1", "2", "noaniq"]
        }
        print(
            f"{fam:17s} N={len(sub)} gold mix {dict(Counter(i['verdict'] for i in sub).most_common(6))} "
            f"best constant {max(consts.items(), key=lambda kv: kv[1])}"
        )


def read_preds(path: Path) -> dict:
    lines = filter(str.strip, path.read_text(encoding="utf-8").splitlines())
    return {j["id"]: j.get("answer", "") for j in map(json.loads, lines)}


def score(pred_path: str, split: str = "public") -> None:
    items = {i["id"]: i for i in load_all(split)}
    preds = read_preds(Path(pred_path))
    t = defaultdict(Counter)
    for iid, p in preds.items():
        if iid in items:
            g = grade(items[iid], p)
            t[items[iid]["family"]][g] += 1
            t["ALL"][g] += 1
    for k, c in sorted(t.items()):
        n = sum(c.values())
        print(
            f"{k:18s} N={n:4} right {c['right']:4} wrong {c['wrong']:4} abstain {c['abstain']:3} acc {c['right'] / n:.3f}"
        )


def regrade() -> None:
    """Old v2.1 prediction files re-scored on the v2.2 items they share (same id and same prompt text); re-worded
    noaniq items are counted apart because the old answer saw the old question."""
    old = {i["id"]: i for i in v2.load_split("public")}
    new = {i["id"]: i for i in load_all("public")}
    files = [
        "data/bench/frontier/opus55_v21_tools.jsonl",
        "data/bench/v21_base_tools_partial.jsonl",
        "data/bench/v21_base_closed.jsonl",
        "data/bench/frontier/opus55_v21_closed.jsonl",
    ]
    print(
        f"{'file':36s} {'N':>4} {'v2.1 acc':>9} {'v2.2 acc':>9}  families that changed (right v2.1->v2.2 / N shared)"
    )
    for f in files:
        preds = read_preds(v2.ROOT / f)
        shared = [i for i in preds if i in new and i in old and new[i]["prompt"] == old[i]["prompt"]]
        reworded = [i for i in preds if i in new and i in old and new[i]["prompt"] != old[i]["prompt"]]
        a1 = sum(v2.grade(old[i], preds[i]) == "right" for i in shared)
        a2 = sum(grade(new[i], preds[i]) == "right" for i in shared)
        fam = []
        for fm in v2.SIZES:
            s = [i for i in shared if new[i]["family"] == fm]
            r1 = sum(v2.grade(old[i], preds[i]) == "right" for i in s)
            r2 = sum(grade(new[i], preds[i]) == "right" for i in s)
            if s and r1 != r2:
                fam.append(f"{fm} {r1}->{r2}/{len(s)}")
        n = max(len(shared), 1)
        print(
            f"{Path(f).name:36s} {len(shared):4} {a1 / n:9.3f} {a2 / n:9.3f}  {'; '.join(fam) or 'no change'}"
            f"  [{len(reworded)} reworded, {len(preds) - len(shared) - len(reworded)} dropped/other: not scored]"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "oracle", "score", "regrade"])
    ap.add_argument("preds", nargs="?")
    ap.add_argument("--split", default="public")
    a = ap.parse_args()
    if a.cmd == "score":
        score(a.preds, a.split)
    else:
        {"build": build, "oracle": oracle, "regrade": regrade}[a.cmd]()


if __name__ == "__main__":
    main()
