"""MezonAudit-bench instances: REAL / SMITH / CLEAN / LIVE splits, a private 30 % per split, a hash manifest.

    .venv/Scripts/python.exe -X utf8 -m research.audit_bench.instances          # build everything, print the counts
    .venv/Scripts/python.exe -X utf8 -m research.audit_bench.instances --eye 10 # print 10 instances per split to read

Splits (the SWE-bench / SWE-smith / LiveCodeBench ideas, see docs/research/benchmark_design.md):
  REAL   decisions really cancelled on an adliya representation / prosecutor protest / court ruling, original text.
         The three golden cases (Qarshi, Xatirchi, Yangiyo'l) and their cancelling or re-adopting acts are EXCLUDED
         (they are the demo, and the demo must not be in the exam).
  SMITH  synthetic, labelled so: a real decision with ONE deterministic injected defect, text otherwise identical.
         Six families; each injection is re-checked by code before the instance is kept.
  CLEAN  decisions in force for 2+ years (adopted on or before 2024-11-21), never cancelled, never lost force, on which
         the whole rule engine is silent. (By construction the engine's own false-alarm rate on CLEAN is 0, so CLEAN
         measures a model's false alarms, not the engine's.)
  LIVE   decisions adopted after 2026-11-22 (after any training cutoff). Empty today; refilled by sync.

Files (data/bench/audit_v1/): <split>.jsonl = the instances a model sees (no label of any kind), gold_<split>.jsonl
= the answers. The private 30 % of every split (and of every SMITH family) goes to data/bench/private/ with its gold;
only its sha256 appears in manifest.json. Hidden-from-model fields: lost_force, label, trigger, cancelling act.
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mezon.decisions.store import DecisionStore
from mezon.rules import basis, business, form
from mezon.rules.common import SafeLaw, date, operative_clauses, squash
from mezon.rules.run import load_law
from research import duplicates, textnorm
from research.textnorm import similarity

OUT = ROOT / "data" / "bench" / "audit_v1"
PRIV = ROOT / "data" / "bench" / "private"
ENGINE_CACHE = (
    OUT / "_engine_cache.json"
)  # {decision id: {"v": verdict, "checks": [...]}} from mezon.rules.run.audit
VERSION = "audit_v1"
SEED = "mezon-audit-v1"
LIVE_FROM = "2026-11-22"
CLEAN_BEFORE = "2024-11-21"  # in force 2+ years on 2026-11-21
LSP_ARTICLE_LOST = (
    "25"  # Law on Local State Power art. 25 lost force on 2024-10-19 (finding-dead-article-citations)
)
LSP_LOST_ON = "2024-10-19"
SMITH_CAP = 34  # per family: 6 families, about 200 in all when the pools allow it
FAMILY_CHECKS = {
    "form_farmoyish": {"R_form"},
    "business_3m": {"R_business_3m", "R_tax_timing"},
    "retroactive": {"R_retroactive"},
    "dead_citation": {"R_basis"},
    "duplicate_clause": {"R_duplicate", "R_double_repeal"},
    "double_repeal": {"R_duplicate", "R_double_repeal"},
}
FAMILIES = [
    "form_farmoyish",
    "business_3m",
    "dead_citation",
    "duplicate_clause",
    "retroactive",
    "double_repeal",
]

# The golden cases and their cancelling / re-adopting acts. They never enter any split.
GOLDEN = {
    "231-4-59-Q/24",
    "VII-3-1-5-77-K/25",
    "VI-76-4-10-146-K/24",
    "261-4-59-Q/24",
    "VII-4-12-5-77-K/25",
    "VI-76-21-10-146-K/24",
    "269-4-59-Q/24",
    "207-4-59-Q/24",
}  # the last two: the Qarshi demo pair
MONTHS_UZ = [
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
]
CYR = re.compile(r"[Ѐ-ӿ]")
REAL_TRIGGERS = {"adliya representation", "adliya letter", "prosecutor protest", "court ruling"}


def h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def is_private(key: str) -> bool:
    """A fixed 30 % of every group, decided by a hash, so it never moves when the pool grows."""
    return int(h(f"{SEED}|private|{key}")[:8], 16) % 10 < 3


def uz_date(d: dt.date, suffix: str = "dagi") -> str:
    return f"{d.year}-yil {d.day}-{MONTHS_UZ[d.month - 1]}{suffix}"


def latin(d: dict) -> bool:
    t = d.get("text") or ""
    return len(CYR.findall(t)) < 0.02 * max(len(t), 1)


# ---------------------------------------------------------------- text surgery


SENTENCE_END = re.compile(
    r"[^\W\d_]{3,}[.;](?=\s|$)"
)  # a word of 3+ letters then a full stop: skips initials like "E. Mamatqulov"
JUNK = re.compile(r"function\s*\(|<script|lxComp")  # lex.uz page code that leaked into a few texts


def insert_clause(text: str, sentence: str) -> str | None:
    """Add one numbered clause right after the last clause of the operative part, before the signature, a page
    footer or the annex (a first version appended after the footer: the eye audit caught it as a visible tell)."""
    clauses = operative_clauses(text)
    m = textnorm._OPERATIVE_RE.search(text)
    if not clauses or not m:
        return None
    last = max(c[0] for c in clauses)
    a = textnorm._ANNEX_RE.search(text, m.end())
    end = a.start() if a else len(text)
    starts = [x for x in textnorm._CLAUSE_RE.finditer(text, m.end(), end) if int(x.group(1)) == last]
    if not starts:
        return None
    from_ = starts[-1].end()
    mm = SENTENCE_END.search(text, from_, end)
    pos = mm.end() if mm else end
    return f"{text[:pos].rstrip()}\n\n        {last + 1}. {sentence}\n\n{text[pos:].lstrip()}"


def diff_span(old: str, new: str) -> str:
    """The inserted or changed middle of `new`, for the gold and the eye audit."""
    i = 0
    while i < min(len(old), len(new)) and old[i] == new[i]:
        i += 1
    j = 0
    while j < min(len(old), len(new)) - i and old[-1 - j] == new[-1 - j]:
        j += 1
    return new[i : len(new) - j].strip()


# ---------------------------------------------------------------- injectors: (decision dict, ctx) -> instance parts


def inj_form(d: dict, ctx: dict):
    if d["type"] != "Q":
        return None
    reg = d["reg_number"]
    new_reg = re.sub(r"-Q/", "-F/", reg)
    if new_reg == reg:
        return None
    text = d["text"].replace(reg, new_reg)
    text = re.sub(r"\bQARORI\b", "FARMOYISHI", text, count=1)
    m = dict(d, text=text, type="F", reg_number=new_reg, is_normative=None)
    ok = any(f.check == "R_form" for f in form.check(m, SafeLaw(None)))
    return (m, "form_farmoyish", new_reg, "") if ok else None


NOT_BURDEN_TITLE = re.compile(
    r"byudjet|budjet|maqbullash|nom berish|nomlash|nomini|prezidentining|vazirlar mahkamasining"
)
NOT_BURDEN_CLAUSE = re.compile(r"byudjet|budjet|moliyalashtir|zaxira")
MAX_CHARS = 45000  # longer texts (a few are 600 000 characters of annex tables) do not fit a model prompt


def _burden_base(d: dict, need_business: bool) -> bool:
    """A genuine burden: money or an obligation set by an operative clause that is not budget financing, a naming
    decision or an act that merely implements a presidential / cabinet decision (the rule engine's detector alone is
    too loose for that: the first eye audit found street renamings and budget acts among its hits)."""
    if d["entry_kind"] != "none" or d["adopted"] is None:
        return False
    found = business.burden_clause(d["text"])
    if not found:
        return False
    title = textnorm.fold(d["title"] or "")
    if NOT_BURDEN_TITLE.search(title) or NOT_BURDEN_CLAUSE.search(textnorm.fold(found[1])):
        return False
    if business.JOB_QUOTA.search(title) or business.TAX_RATE.search(title):
        return False
    return found[2]["money"] and (found[2]["business"] or not need_business)


def inj_business(d: dict, ctx: dict):
    if not _burden_base(d, True):
        return None
    on = date(d["adopted"])
    when = on + dt.timedelta(days=2)
    sentence = f"Mazkur qaror {uz_date(when, 'dan')} e’tiboran kuchga kiradi."
    text = insert_clause(d["text"], sentence)
    if not text:
        return None
    m = dict(d, text=text)
    ok = any(
        f.check == "R_business_3m" and f.status == "possible_violation"
        for f in business.check(m, SafeLaw(None))
    )
    return (m, "business_3m", sentence, "") if ok else None


def inj_retro(d: dict, ctx: dict):
    if not _burden_base(d, False):
        return None
    on = date(d["adopted"])
    back = 15 + int(h(d["reg_number"])[:4], 16) % 45
    sentence = f"Mazkur qaror {uz_date(on - dt.timedelta(days=back), 'dan')} e’tiboran kuchga kiradi."
    text = insert_clause(d["text"], sentence)
    if not text:
        return None
    m = dict(d, text=text)
    ok = any(f.check == "R_retroactive" for f in business.check(m, SafeLaw(None)))
    return (m, "retroactive", sentence, "") if ok else None


def inj_dead_citation(d: dict, ctx: dict):
    if (d["adopted"] or "") < "2024-10-20":
        return None
    text = d["text"]
    pre_end = textnorm._OPERATIVE_RE.search(text)
    if not pre_end:
        return None
    pre = text[: pre_end.start()]
    # the article list right after the Law on Local State Power, e.g. «Qonunining 6, 24-moddalariga»
    for lm in re.finditer(
        r"hokimiyati\s+to[‘’ʻʼ'`]?g[‘’ʻʼ'`]?risida[”\"»]?\s*gi[^.]{0,80}?qonunining\s+(\d+)",
        pre,
        re.IGNORECASE,
    ):
        if lm.group(1) == LSP_ARTICLE_LOST:
            return None
        start, end = lm.start(1), lm.end(1)
        new = pre[:start] + LSP_ARTICLE_LOST + pre[end:]
        m = dict(d, text=new + text[pre_end.start() :])
        hit = [
            f
            for f in basis.check(m, SafeLaw(ctx["law"]))
            if f.check == "R_basis" and f"article {LSP_ARTICLE_LOST} " in f.title
        ]
        return (
            (m, "dead_citation", f"{pre[start - 30 : start]}{LSP_ARTICLE_LOST}{pre[end : end + 20]}", "")
            if hit
            else None
        )
    return None


def _older_in_force(d: dict, ctx: dict) -> list[dict]:
    out = []
    for o in ctx["by_body"].get((d["region"], d["district"], d["type"]), []):
        if o["reg_number"] == d["reg_number"] or not o["adopted"] or o["adopted"] >= d["adopted"]:
            continue
        if o["lost_force"] and o["lost_force"] <= d["adopted"]:
            continue
        out.append(o)
    return sorted(out, key=lambda o: o["reg_number"])


def inj_duplicate(d: dict, ctx: dict):
    own = {squash(c) for _, c in operative_clauses(d["text"])}
    for o in _older_in_force(d, ctx):
        sim = similarity(textnorm.fold(d["title"] or ""), textnorm.fold(o["title"] or ""))
        if not 0.25 <= sim < 0.9 or "prezidentining" in textnorm.fold(
            d["title"] or ""
        ):  # same topic, not the same act
            continue
        for n, clause in operative_clauses(o["text"]):
            c = re.sub(r"\s+", " ", clause).strip()
            if (
                150 <= len(c) <= 700
                and squash(c) not in own
                and not re.search(r"nazorat|e.lon|bekor qil", textnorm.fold(c))
            ):
                text = insert_clause(d["text"], c)
                if not text:
                    return None
                m = dict(d, text=text)
                if any(squash(c) in squash(x) for _, x in operative_clauses(text)):
                    return m, "duplicate_clause", c, o["reg_number"]
                return None
    return None


def inj_double_repeal(d: dict, ctx: dict):
    cands = [
        o
        for o in ctx["by_body"].get((d["region"], d["district"], d["type"]), [])
        if o["reg_number"] != d["reg_number"]
        and o["adopted"]
        and o["adopted"] < d["adopted"]
        and o["lost_force"]
        and o["lost_force"] < d["adopted"]
    ]
    for o in sorted(cands, key=lambda o: o["reg_number"]):
        who = "Kengashning" if d["type"] == "K" else "Hokimning"
        sentence = f"{who} {uz_date(date(o['adopted']))} {o['reg_number']}-sonli qarori kuchini yo’qotgan deb hisoblansin."
        text = insert_clause(d["text"], sentence)
        if not text:
            return None
        m = dict(d, text=text)
        if duplicates.REPEAL_VERB.search(text) and o["reg_number"] in text:
            return m, "double_repeal", sentence, o["reg_number"]
        return None
    return None


INJECTORS = {
    "form_farmoyish": inj_form,
    "business_3m": inj_business,
    "dead_citation": inj_dead_citation,
    "duplicate_clause": inj_duplicate,
    "retroactive": inj_retro,
    "double_repeal": inj_double_repeal,
}


# ---------------------------------------------------------------- build


def instance_view(d: dict, split: str, family: str) -> tuple[dict, str]:
    iid = "a1-" + h(f"{split}|{family}|{d['reg_number']}")[:10]
    return {
        "id": iid,
        "reg_number": d["reg_number"],
        "type": d["type"],
        "date": d["adopted"],
        "title": d["title"] or "",
        "text": d["text"],
    }, iid


def load_pool(ds: DecisionStore) -> tuple[list[dict], dict]:
    rows = [ds.get(i) for i in ds.ids("adopted") if i.startswith("lex:")]
    rows = [
        d
        for d in rows
        if d
        and 800 <= len(d["text"] or "") <= MAX_CHARS
        and not JUNK.search(d["text"])
        and d["reg_number"]
        and d["adopted"]
    ]
    cancelled = set()
    for r in ds.con.execute("SELECT cancelled_numbers FROM decisions WHERE role='cancelling'"):
        cancelled |= {x.strip() for x in re.split(r"[,;\s]+", r[0] or "") if x.strip()}
    cancelled |= GOLDEN
    return rows, {"cancelled": cancelled}


def build() -> dict:
    ds = DecisionStore()
    law = load_law()
    cache = json.loads(ENGINE_CACHE.read_text(encoding="utf-8")) if ENGINE_CACHE.exists() else {}
    rows, aux = load_pool(ds)
    for d in rows:
        d["entry_kind"] = business.entry_into_force(d["text"])["kind"]
    by_body: dict[tuple, list[dict]] = {}
    for d in rows:
        by_body.setdefault((d["region"], d["district"], d["type"]), []).append(d)
    # lost_force matters for double_repeal even on decisions whose text is short: take them from the whole lex.uz set
    for r in ds.con.execute(
        "SELECT id FROM decisions WHERE source='lex.uz' AND role='adopted' AND length(text)>=200"
    ):
        d = ds.get(r[0])
        if (
            d
            and d["reg_number"]
            and d["adopted"]
            and d["id"] not in {x["id"] for x in by_body.get((d["region"], d["district"], d["type"]), [])}
        ):
            by_body.setdefault((d["region"], d["district"], d["type"]), []).append(d)
    ctx = {"law": law, "by_body": by_body}
    engine_silent = lambda d: cache.get(d["id"], {}).get("checks") == []
    stats: dict = {}
    splits: dict[str, list[tuple[dict, dict, str]]] = {"real": [], "smith": [], "clean": [], "live": []}

    # REAL: really cancelled, original text, golden excluded, one per registration number
    seen = set()
    for d in sorted(rows, key=lambda x: x["reg_number"]):
        if (
            d["label"] != "POSITIVE"
            or (d["trigger"] or "") not in REAL_TRIGGERS
            or d["reg_number"] in GOLDEN | seen
        ):
            continue
        seen.add(d["reg_number"])
        view, iid = instance_view(d, "real", "real")
        gold = {
            "id": iid,
            "split": "real",
            "family": "real",
            "synthetic": False,
            "verdict": "not_positive",
            "defect_types": ["any"],
            "provenance": f"cancelled on {d['trigger']}; base {d['reg_number']}",
            "span": "",
        }
        splits["real"].append((view, gold, "real"))
    real_regs = {v["reg_number"] for v, _, _ in splits["real"]}

    # CLEAN: 2+ years in force, never cancelled, never lost force, whole rule engine silent
    clean_regs = set()
    for d in sorted(rows, key=lambda x: x["reg_number"]):
        if (
            d["adopted"] <= CLEAN_BEFORE
            and not d["lost_force"]
            and d["reg_number"] not in aux["cancelled"]
            and d["label"] == "none"
            and d["type"] in ("Q", "K")
            and engine_silent(d)
            and d["reg_number"] not in real_regs
        ):
            view, iid = instance_view(d, "clean", "clean")
            gold = {
                "id": iid,
                "split": "clean",
                "family": "clean",
                "synthetic": False,
                "verdict": "positive",
                "defect_types": [],
                "provenance": f"in force since {d['adopted']}, never cancelled, engine silent",
                "span": "",
            }
            splits["clean"].append((view, gold, "clean"))
            clean_regs.add(d["reg_number"])

    # SMITH: one injected defect per base decision; a base is used once; real/clean/golden/cancelled bases excluded
    used = set(real_regs) | clean_regs | aux["cancelled"]
    pool = sorted(
        (
            d
            for d in rows
            if d["label"] == "none"
            and d["type"] in ("Q", "K")
            and latin(d)
            and d["lost_force"] in ("", None)
            and d["reg_number"] not in used
        ),
        key=lambda d: h(f"{SEED}|{d['reg_number']}"),
    )
    stats["smith_pool"] = len(pool)
    inapplicable = {f: 0 for f in FAMILIES}
    for fam in FAMILIES:
        kept = 0
        for d in pool:
            if kept >= SMITH_CAP:
                break
            if d["reg_number"] in used:
                continue
            checks = set(cache.get(d["id"], {}).get("checks", ["?"]))
            if (
                checks & FAMILY_CHECKS[fam] or "?" in checks
            ):  # the rules must not already see this kind of defect in the base
                continue
            res = INJECTORS[fam](d, ctx)
            if not res:
                inapplicable[fam] += 1
                continue
            m, family, span, related = res
            view, iid = instance_view(m, "smith", family)
            gold = {
                "id": iid,
                "split": "smith",
                "family": family,
                "synthetic": True,
                "verdict": "not_positive",
                "defect_types": [family],
                "provenance": f"SYNTHETIC: base {d['reg_number']} + injected {family}",
                "span": span,
                "base_reg": d["reg_number"],
                "base_engine_flags": sorted(checks),
                "base_text_sha256": h(d["text"])[:16],
            }
            if related:
                gold["related_reg"] = related
            splits["smith"].append((view, gold, family))
            used.add(d["reg_number"])
            kept += 1
    stats["smith_inapplicable_tried"] = inapplicable

    # LIVE: adopted after LIVE_FROM (nothing yet when the store was built)
    for d in rows:
        if d["adopted"] >= LIVE_FROM and d["type"] in ("Q", "K"):
            view, iid = instance_view(d, "live", "live")
            splits["live"].append(
                (
                    view,
                    {
                        "id": iid,
                        "split": "live",
                        "family": "live",
                        "synthetic": False,
                        "verdict": "unknown",
                        "defect_types": [],
                        "provenance": "adopted after cutoff",
                        "span": "",
                    },
                    "live",
                )
            )
    return {"splits": splits, "stats": stats}


def write(built: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": VERSION,
        "built": dt.date.today().isoformat(),
        "splits": {},
        "private_hashes": {},
        "stats": built["stats"],
    }
    for split, items in built["splits"].items():
        pub_i, pub_g, prv_i, prv_g = [], [], [], []
        for view, gold, fam in items:
            priv = is_private(f"{split}|{fam}|{view['id']}")
            (prv_i if priv else pub_i).append(view)
            (prv_g if priv else pub_g).append(gold)
            if priv:
                manifest["private_hashes"][view["id"]] = h(
                    json.dumps(view, sort_keys=True, ensure_ascii=False)
                )[:32]
        for folder, ins, gld in ((OUT, pub_i, pub_g), (PRIV, prv_i, prv_g)):
            (folder / f"{split}.jsonl").write_text(
                "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ins), encoding="utf-8"
            )
            (folder / f"gold_{split}.jsonl").write_text(
                "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in gld), encoding="utf-8"
            )
        fams: dict[str, int] = {}
        for _, g, fam in items:
            fams[fam] = fams.get(fam, 0) + 1
        manifest["splits"][split] = {
            "n": len(items),
            "public": len(pub_i),
            "private": len(prv_i),
            "families": fams,
        }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def load(split: str, private: bool = False) -> list[tuple[dict, dict]]:
    """(instance, gold) pairs of one split from the public (or private) folder."""
    folder = PRIV if private else OUT
    f, g = folder / f"{split}.jsonl", folder / f"gold_{split}.jsonl"
    if not f.exists():
        return []
    ins = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    gold = {
        x["id"]: x for x in (json.loads(y) for y in g.read_text(encoding="utf-8").splitlines() if y.strip())
    }
    return [(i, gold[i["id"]]) for i in ins]


def eye(n: int) -> None:
    """Print n instances per split to read: the injected span in its context, or the opening of the text."""
    rng_seed = 0
    for split in ("real", "smith", "clean"):
        pairs = load(split)
        if split == "smith":  # spread over the families
            by: dict[str, list] = {}
            for p in pairs:
                by.setdefault(p[1]["family"], []).append(p)
            order = [x for grp in zip(*by.values()) for x in grp] if by else []
            pairs = order + [p for p in pairs if p not in order]
        print(
            f"\n===== EYE AUDIT {split.upper()} ({len(pairs)} public instances; showing {min(n, len(pairs))})"
        )
        for ins, gold in pairs[:n]:
            rng_seed += 1
            print(
                f"\n--- {ins['id']} {ins['reg_number']} {ins['date']} [{gold['family']}] text {len(ins['text'])} chars"
            )
            print(f"    title: {ins['title'][:110]}")
            print(f"    gold:  {gold['verdict']} {gold['defect_types']}  {gold['provenance'][:100]}")
            if gold["span"]:
                print(f"    SPAN:  {gold['span'][:260]}")


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()[:16]


EYE_AUDIT = {
    "date": "2026-11-21",
    "read": "REAL 7 of 7 public, SMITH 10 (spread over families) plus the insertion context of 2 per family, CLEAN 10",
    "found_and_fixed": [
        (
            "business_3m / retroactive bases included budget acts and street renamings (the rule engine's burden detector is loose): "
            "now a base needs a money burden outside budget, naming and implementing-act titles"
        ),
        "duplicate_clause copied clauses between unrelated acts: now needs the same topic (title similarity 0.25-0.9)",
        (
            "inserted clauses were appended after the signature and footer (a visible tell); then they split the last clause "
            "at 'viloyat hokimining': now they go after the last clause's own sentence end"
        ),
        (
            "one CLEAN text was 627 000 characters (annex tables): texts over 45 000 characters and texts with leaked lex.uz "
            "page code are excluded from every split except REAL"
        ),
        "form_farmoyish gold span carried a label that is not in the text: now the new registration number only",
    ],
    "known_weaknesses": [
        "business_3m N and retroactive N are tiny (the engine finds few genuine burdens without a stated entry into force)",
        "SMITH is Latin-script only; REAL and CLEAN also hold Cyrillic texts, a possible shortcut",
        "an inserted clause is a stylistic tell for a model that compares with real decisions",
        "double_repeal reuses a few repealed targets; CLEAN is small because few old decisions survive the filters",
    ],
}


def freeze() -> None:
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    out = {
        "frozen": dt.date.today().isoformat() + " Tashkent",
        "version": VERSION,
        "splits": man["splits"],
        "files": {
            f.name: {"bytes": f.stat().st_size, "sha256_16": file_hash(f)}
            for f in sorted(OUT.glob("*.jsonl"))
        },
        "private_manifest_sha256_16": h(json.dumps(man["private_hashes"], sort_keys=True))[:16],
        "private_items": len(man["private_hashes"]),
        "code_sha256_16": {
            n: file_hash(ROOT / n)
            for n in (
                "research/audit_bench/instances.py",
                "research/audit_bench/grade.py",
                "research/audit_bench/harness.py",
                "mezon/tools.py",
                "mezon/lawstore/store.py",
                "mezon/verify.py",
            )
        },
        "law_store_sha256_16": file_hash(ROOT / "data" / "store" / "laws.sqlite"),
        "decision_store_sha256_16": file_hash(ROOT / "data" / "store" / "decisions.sqlite"),
        "eye_audit": EYE_AUDIT,
        "rules": "Never train on audit_v1. Changing an instance, the grader, a tool or either store = v1.1 and every model "
        "re-runs. SMITH is synthetic and always reported as such. Private items are in data/bench/private/ "
        "(never published, never given to a model that is being trained). Flagged means possible violation.",
    }
    (ROOT / "data" / "bench" / "FROZEN_audit_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(
        "frozen:",
        {
            k: v["sha256_16"]
            for k, v in out["files"].items()
            if k in ("real.jsonl", "smith.jsonl", "clean.jsonl")
        },
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eye", type=int, default=0)
    ap.add_argument(
        "--freeze", action="store_true", help="write data/bench/FROZEN_audit_v1.json from the built files"
    )
    a = ap.parse_args()
    if a.freeze:
        freeze()
        return
    if a.eye:
        eye(a.eye)
        return
    manifest = write(build())
    for split, v in manifest["splits"].items():
        print(f"{split:6} N={v['n']:4} public={v['public']:4} private={v['private']:4} {v['families']}")
    print(
        "smith pool:",
        manifest["stats"]["smith_pool"],
        "| injector inapplicable (tried):",
        manifest["stats"]["smith_inapplicable_tried"],
    )


if __name__ == "__main__":
    main()
