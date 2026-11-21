"""Mezon API: live Gate-0 drafts, decision search, full audits, evidence numbers. Read-only over the local stores.

Run:  .venv/Scripts/python.exe -X utf8 -m uvicorn mezon.api.main:app --port 8090
"""

import csv
import datetime as dt
import hashlib
import html
import logging
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from mezon import ask as ask_mod
from mezon.agent import run as run_agent
from mezon.conclusion import _unit as unit_uz
from mezon.conclusion import draft
from mezon.config import STORE
from mezon.decisions.store import DecisionStore
from mezon.plain import GATES, checked, explain
from mezon.region_report import build as build_region_report
from mezon.rules import corruption, linguistic
from mezon.rules.common import SafeLaw
from mezon.rules.procedure import is_budget_allocation
from mezon.rules.run import audit, load_law
from mezon.version import ruleset
from research.regnum import REGIONS

WEB = Path(__file__).resolve().parents[1] / "web"
REGULATION_DB = STORE / "regulation.sqlite"
MIN_DISCUSSION_DAYS = 15
COURT = {"source": "stat.sud.uz, claims to declare a hokimlik decision invalid, 2023 - 2026 H1 (research/scoreboard.md)",
         "heard": 9320, "satisfied": 3182}

app = FastAPI(title="Mezon", docs_url=None, redoc_url=None)
_decisions = DecisionStore()
_law = load_law()


REVIEWS_DB = STORE / "reviews.sqlite"
_reviews_lock = threading.Lock()
_store_lock = threading.RLock()  # the law and decision stores share one SQLite connection across worker threads


class Review(BaseModel):
    decision_id: str = Field(max_length=80)
    check: str = Field(max_length=40, pattern=r"^R_[a-z0-9_]+$")
    verdict: str = Field(pattern=r"^(correct|wrong|unclear)$")
    note: str = Field(default="", max_length=500)
    reviewer: str = Field(default="", max_length=40)


class GroupAnswer(BaseModel):
    question: int = Field(ge=1, le=20)
    reviewer: str = Field(max_length=40)
    answer: str = Field(pattern=r"^(applies|not_applies|depends)$")
    note: str = Field(default="", max_length=500)


def _reviews() -> sqlite3.Connection:
    con = sqlite3.connect(REVIEWS_DB)
    con.execute("CREATE TABLE IF NOT EXISTS reviews(decision_id TEXT, check_code TEXT, verdict TEXT, note TEXT, at TEXT,"
                " PRIMARY KEY(decision_id, check_code))")
    if "reviewer" not in {r[1] for r in con.execute("PRAGMA table_info(reviews)")}:
        con.execute("ALTER TABLE reviews ADD COLUMN reviewer TEXT DEFAULT ''")
    con.execute("CREATE TABLE IF NOT EXISTS group_answers(question INTEGER, reviewer TEXT, answer TEXT, note TEXT,"
                " at TEXT, PRIMARY KEY(question, reviewer))")
    return con


def _ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _d(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d/%m/%Y").date()


@lru_cache(maxsize=1)
def _art24() -> dict:
    unit = _law.get_unit("nla", "art:24/part:3", dt.date.today().isoformat()) if _law else None
    return {"act": "Normativ-huquqiy hujjatlar to'g'risida Qonun (O'RQ-682)", "article": "24-modda, 3-qism",
            "quote": (unit or {}).get("text", ""), "url": (unit or {}).get("url", "")}


def _drafts(today: dt.date) -> list[dict]:
    if not REGULATION_DB.exists():
        return []
    with _ro(REGULATION_DB) as con:
        rows = con.execute("SELECT id, creator, title, start, end, proposals FROM drafts WHERE is_local=1").fetchall()
    out = []
    for r in rows:
        start, end = _d(r["start"]), _d(r["end"])
        out.append({"id": r["id"], "creator": r["creator"], "title": r["title"], "start": start.isoformat(),
                    "end": end.isoformat(), "days": (end - start).days, "open": end >= today,
                    "proposals": r["proposals"], "url": f"https://regulation.gov.uz/oz/d/{r['id']}"})
    return out


@app.get("/api/live-drafts")
def live_drafts() -> dict:
    today = dt.date.today()
    drafts = _drafts(today)
    open_ = [d for d in drafts if d["open"]]
    budget = [d for d in open_ if is_budget_allocation(d.get("title"))]
    rest = [d for d in open_ if not is_budget_allocation(d.get("title"))]
    short = sorted((d for d in rest if d["days"] < MIN_DISCUSSION_DAYS), key=lambda d: d["end"])
    return {"today": today.isoformat(), "open_local": len(open_), "open_normative_candidates": len(rest),
            "budget_allocations": len(budget),
            "budget_short": sum(d["days"] < MIN_DISCUSSION_DAYS for d in budget), "short": short, "law": _art24()}


@app.get("/api/decisions")
def decisions(q: str = "", limit: int = 30) -> list[dict]:
    like = f"%{q.strip()[:80]}%"
    cur = _decisions.con.execute(
        "SELECT id, reg_number, body, title, adopted, label, source FROM decisions "
        "WHERE (reg_number LIKE ? OR title LIKE ? OR body LIKE ?) AND length(coalesce(text,'')) > 0 "
        "ORDER BY adopted DESC LIMIT ?", (like, like, like, min(max(limit, 1), 100)))
    return [dict(r) for r in cur]


@lru_cache(maxsize=4096)
def _audit_cached(decision_id: str) -> dict:
    with _store_lock:
        return _audit_uncached(decision_id)


def _audit_uncached(decision_id: str) -> dict:
    report = audit(decision_id, law=_law, decisions=_decisions).to_dict()
    report["gate_uz"] = GATES.get(report["gate"], report["gate"])
    for flag in report["flags"]:
        flag.update(explain(flag, report))
    d = _decisions.get(decision_id) or {}
    report["checked_uz"] = checked(report, d.get("text") or "", SafeLaw(_law) if _law else None, d.get("adopted") or "")
    report["checklist_860"] = corruption.checklist(report, bool(d.get("text")))
    report["ruleset"] = ruleset()
    report["linguistic_662"] = linguistic.section(d.get("text") or "", _law, d.get("adopted") or "")
    fresh = _freshness().get(d.get("reg_number") or "", {})
    report["lexuz_checked"], report["lexuz_status"] = fresh.get("date", ""), fresh.get("status", "")
    # The exact text this audit read: if the published text changes later, the hash no longer matches.
    report["text_sha"] = hashlib.sha256((d.get("text") or "").encode("utf-8")).hexdigest()[:16] if d.get("text") else ""
    return report


@app.get("/api/conclusion/{decision_id:path}", response_class=PlainTextResponse)
def conclusion(decision_id: str) -> str:
    """A draft expertise conclusion for the reviewer to edit and sign."""
    ids = [decision_id] if _decisions.get(decision_id) else _decisions.by_reg(decision_id)
    if not ids:
        raise HTTPException(404, "decision not found")
    return draft(_audit_cached(ids[0]))


@app.get("/api/conclusion-word/{decision_id:path}")
def conclusion_word(decision_id: str) -> Response:
    """The draft conclusion as a Word document (.doc) the expert edits and signs in their usual workflow."""
    text = conclusion(decision_id)
    reg = re.sub(r"[^\w-]+", "_", decision_id)[:60]
    body = "".join(f"<p>{html.escape(line) or '&nbsp;'}</p>" for line in text.splitlines())
    doc = ("<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'>"
           "<head><meta charset='utf-8'><title>Mezon xulosa loyihasi</title><style>"
           "@page{size:21cm 29.7cm;margin:2cm 1.5cm 2cm 3cm}"
           "body{font-family:'Times New Roman',serif;font-size:14pt;line-height:1.3}p{margin:0 0 4pt}"
           "</style></head><body>" + body + "</body></html>")
    return Response(content=doc.encode("utf-8"), media_type="application/msword",
                    headers={"Content-Disposition": f'attachment; filename="Mezon_xulosa_{reg}.doc"'})


@app.get("/api/audit/{decision_id:path}")
def audit_one(decision_id: str) -> dict:
    ids = [decision_id] if _decisions.get(decision_id) else _decisions.by_reg(decision_id)
    if not ids:
        raise HTTPException(404, "decision not found")
    return _audit_cached(ids[0])


def _warm() -> None:
    """Audit the labelled decisions in the background so the demo never waits."""
    cur = _decisions.con.execute("SELECT id FROM decisions WHERE label IS NOT NULL AND length(coalesce(text,'')) > 0")
    for (decision_id,) in cur.fetchall():
        try:
            _audit_cached(decision_id)
        except Exception as e:  # noqa: BLE001 - one bad decision must not stop the warm-up
            logging.getLogger("mezon").warning("warm-up audit failed for %s: %s", decision_id, e)


@app.on_event("startup")
def _start_warm() -> None:
    threading.Thread(target=_warm, daemon=True).start()


@app.get("/api/law")
def law_then_now(act: str, path: str, on: str) -> dict:
    """One article as it read on `on` and as it reads today: the time machine behind every citation."""
    if not _law:
        raise HTTPException(503, "law store unavailable")
    then = _law.get_unit(act, path, on)
    now = _law.get_unit(act, path, dt.date.today().isoformat())
    if not then and not now:
        raise HTTPException(404, "article not found")
    pick = lambda u: {k: u.get(k) for k in ("text", "edition", "url", "provisional")} if u else None
    return {"act": act, "path": path, "on": on, "then": pick(then), "now": pick(now),
            "changed": bool(then and now and then["text"].strip() != now["text"].strip()),
            "repealed_since": bool(then and not now), "new_since": bool(now and not then)}


FLAGS_CSV = Path(__file__).resolve().parents[2] / "data" / "interim" / "rule_flags.csv"
_SEV = {"high": 3, "medium": 2, "low": 1}


@lru_cache(maxsize=1)
def _freshness() -> dict[str, dict]:
    """reg number -> {date, status} from the newest lex.uz re-check (research/freshness.py)."""
    files = sorted((FLAGS_CSV.parent).glob("freshness_*.csv"))
    if not files:
        return {}
    date = files[-1].stem.removeprefix("freshness_")
    with open(files[-1], encoding="utf-8-sig", newline="") as f:
        return {r["reg_number"]: {"date": date, "status": r["status"], "detail": r["detail"]}
                for r in csv.DictReader(f) if r["status"] != "not reached"}


@lru_cache(maxsize=1)
def _flag_index() -> dict[str, list[dict]]:
    """decision id -> its flags from the last full audit (`python -m mezon.rules.run --all`)."""
    out: dict[str, list[dict]] = {}
    if FLAGS_CSV.exists():
        with open(FLAGS_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["decision_id"], []).append(r)
    return out


REPEATS_CSV = Path(__file__).resolve().parents[2] / "data" / "interim" / "repeat_defects.csv"


@app.get("/api/repeats")
def repeats() -> list[dict]:
    """Officially cancelled decisions whose body later adopted the same matter with the same flagged defect."""
    if not REPEATS_CSV.exists():
        return []
    with open(REPEATS_CSV, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["shared_flags"]]


@app.get("/api/regions")
def regions() -> list[dict]:
    return [{"code": k, "name": v} for k, v in REGIONS.items()]


@app.get("/api/queue")
def queue(region: int | None = None, limit: int = 40) -> dict:
    """The territorial adliya's review queue: adopted decisions with flags, riskiest and newest first."""
    idx = _flag_index()
    rows = []
    for decision_id, flags in idx.items():
        d = _decisions.get(decision_id)
        if not d or d["role"] == "draft" or (region is not None and d["region"] != region):
            continue
        if d.get("lost_force") and d["lost_force"] <= dt.date.today().isoformat():
            continue  # already out of force: nothing left for the expert to fix, so it leaves the queue
        if d.get("label") not in (None, "", "none"):
            continue  # a cancelling act (lex.uz) or E-qaror says it was cancelled, even when no lost-force date is set
        fresh = _freshness().get(d["reg_number"], {})
        if fresh.get("status", "").startswith("lost force"):
            continue  # lex.uz says it lost force since the store was built
        hard = [f for f in flags if f["status"] == "possible_violation"]
        rows.append({
            "id": decision_id, "reg_number": d["reg_number"], "body": d["body"], "title": d["title"],
            "adopted": d["adopted"], "region": REGIONS.get(d["region"], ""), "url": d["url"],
            "verdict": flags[0]["verdict"], "n_flags": len(flags), "n_hard": len(hard),
            "checks": sorted({f["check"] for f in flags}),
            "score": max((_SEV.get(f["severity"], 0) for f in hard), default=0) * 10 + len(hard),
            "lexuz_checked": fresh.get("date", ""),
        })
    rows.sort(key=lambda r: (r["score"], r["adopted"] or ""), reverse=True)
    return {"region": REGIONS.get(region, "Barcha hududlar") if region else "Barcha hududlar",
            "total": len(rows), "items": rows[: min(max(limit, 1), 200)]}


@app.get("/api/agent/{reg:path}")
def agent_trace(reg: str) -> dict:
    """The agent's step-by-step path for one decision (mezon/agent.py): tools called, what each returned."""
    ids = _decisions.by_reg(reg) or ([reg] if _decisions.get(reg) else [])
    if not ids:
        raise HTTPException(404, "decision not found")
    with _store_lock:
        return run_agent(ids[0], _law, _decisions)


VERDICT_UZ = {"positive": "Ijobiy", "positive_with_fixable_defects": "Bartaraf etiladigan kamchiliklar bilan ijobiy",
              "negative": "Salbiy", "not_checked": "Tekshirilmadi"}
ASK_EXAMPLES = ["355-4-68-Q/25 nega belgilandi?", "VII-3-1-5-77-K/25 menga nima degani?", "265-4-60-Q/25 tadbirkorga ta'siri"]


@app.get("/api/ask")
def ask(q: str, who: str = "citizen") -> dict:
    """Mezon AI for everyone: find the decision in the question, run the agent, answer for an expert, a business or a
    citizen. Without the local model it answers only from the rules and the law store, and says so."""
    who = who if who in ("expert", "business", "citizen") else "citizen"
    regs = ask_mod.numbers(q)
    kind = ask_mod.intent(q)
    ids = next((ids for r in regs if (ids := _decisions.by_reg(r))), None)
    if not ids:
        matches = [] if regs else ask_mod.search(q, _decisions)
        if len(matches) == 1:
            ids = _decisions.by_reg(matches[0]["reg_number"])
        else:
            return {"who": who, "intent": kind, "found": None, "matches": matches,
                    "suggestions": [m["reg_number"] for m in matches] or ASK_EXAMPLES,
                    "message": (f"{regs[0]} raqamli qaror bazada topilmadi." if regs else
                                f"Shu so'rov bo'yicha {len(matches)} ta qaror topildi: birini tanlang." if matches else
                                "Qaror raqamini yoki joy va mavzuni yozing, masalan \"Yakkabog' maktab\".")}
    with _store_lock:
        trace = run_agent(ids[0], _law, _decisions)
    r = _audit_cached(ids[0])
    blocks = []
    for f in r["flags"]:
        cite = (f.get("citations") or [{}])[0]
        b = {"title": f.get("title_uz") or f["title"], "status": f["status"],
             "basis": f"{cite.get('act_title', '')}, {unit_uz(cite.get('article', ''))} ({cite.get('on_date', '')} holatiga)" if cite else "",
             "quote": next((e["quote"] for e in f.get("evidence") or [] if e.get("quote")), "")}
        if who != "expert":
            b.update(plain=f.get("plain_uz", ""), channels=f.get("channels", []), appeal=f.get("appeal_uz", ""))
        blocks.append(b)
    return {"who": who, "intent": kind, "lead": ask_mod.lead(kind, r["flags"], who),
            "found": r["reg_number"], "title": r.get("title", ""), "body": r.get("body", ""),
            "verdict": r["verdict"], "verdict_uz": VERDICT_UZ.get(r["verdict"], r["verdict"]), "steps": trace["steps"],
            "llm": trace["llm"], "blocks": blocks, "checked": len(r.get("checked_uz") or []),
            "url": r.get("url", ""), "conclusion": f"/api/conclusion/{r['reg_number']}"}


IMPACT_CSV = FLAGS_CSV.parent / "law_change_impact.csv"


@lru_cache(maxsize=1)
def _impact() -> list[dict]:
    if not IMPACT_CSV.exists():
        return []
    with open(IMPACT_CSV, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["status"] in ("reworded", "removed")]


@app.get("/api/law-changes")
def law_changes(since: str = "2024-01-01", limit: int = 50) -> dict:
    """A law changed after a decision was adopted: decisions still in force whose cited article was later reworded or
    removed (research/law_change_impact.py), newest change first. The expert re-checks them against today's edition."""
    today = dt.date.today().isoformat()
    rows, seen = [], set()
    for r in sorted(_impact(), key=lambda r: r["changed_on"], reverse=True):
        if r["changed_on"] < since or r["changed_on"] > today or (r["reg_number"], r["act_key"]) in seen:
            continue
        ids = _decisions.by_reg(r["reg_number"])
        d = _decisions.get(ids[0]) if ids else None
        if not d or (d.get("lost_force") and d["lost_force"] <= today) or d.get("label") not in (None, "", "none"):
            continue  # already out of force or cancelled: nothing to re-check
        seen.add((r["reg_number"], r["act_key"]))
        rows.append({"reg_number": r["reg_number"], "adopted": r["adopted"], "body": r["body"], "act": r["act"],
                     "changed_on": r["changed_on"], "articles": ", ".join(f"{u.strip()}-modda" for u in r["changed_units"].split(",") if u.strip()),
                     "status": r["status"],
                     "status_uz": "modda chiqarib tashlangan" if r["status"] == "removed" else "modda tahriri o'zgargan",
                     "url": r["url"]})
    return {"since": since, "total": len(rows), "items": rows[: min(max(limit, 1), 200)]}


@app.get("/api/region-report/{region}", response_class=PlainTextResponse)
def region_report(region: int) -> str:
    """One printable page for a regional adliya head (mezon/region_report.py)."""
    if region not in REGIONS:
        raise HTTPException(404, "region not found")
    items = queue(region=region, limit=200)["items"]
    return build_region_report(region, REGIONS[region], items, _flag_index(), _decisions.get)


@app.post("/api/reviews")
def save_review(r: Review) -> dict:
    """The expert's verdict on one flag; the latest verdict per decision and rule wins."""
    with _reviews_lock, _reviews() as con:
        con.execute("INSERT OR REPLACE INTO reviews(decision_id, check_code, verdict, note, at, reviewer) "
                    "VALUES(?,?,?,?,?,?)", (r.decision_id, r.check, r.verdict, r.note,
                                            dt.datetime.now().isoformat(timespec="seconds"), r.reviewer))
    return {"ok": True}


@app.get("/api/reviews")
def review_summary() -> dict:
    """Precision per rule from expert verdicts: correct / (correct + wrong), with N."""
    with _reviews() as con:
        rows = con.execute("SELECT check_code, verdict, count(*) FROM reviews GROUP BY 1, 2").fetchall()
        mine = {f"{d}|{c}": v for d, c, v in con.execute("SELECT decision_id, check_code, verdict FROM reviews")}
    rules: dict[str, dict] = {}
    for check, verdict, n in rows:
        rules.setdefault(check, {"correct": 0, "wrong": 0, "unclear": 0})[verdict] = n
    for v in rules.values():
        judged = v["correct"] + v["wrong"]
        v["precision"] = round(v["correct"] / judged, 3) if judged else None
    total = {k: sum(v[k] for v in rules.values()) for k in ("correct", "wrong", "unclear")}
    judged = total["correct"] + total["wrong"]
    return {"rules": rules, "total": total, "precision": round(total["correct"] / judged, 3) if judged else None,
            "verdicts": mine}


LAWYER_SHEET = Path(__file__).resolve().parents[2] / "research" / "flags_for_lawyer_round1.csv"
GROUP_QUESTIONS = LAWYER_SHEET.parent / "lawyer_questions_round1.md"


@app.get("/api/review-sheet")
def review_sheet() -> dict:
    """The stratified flags for the lawyers (1-30 first reviewer, 31-60 second) plus the group questions."""
    flags = []
    with LAWYER_SHEET.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            with _store_lock:
                ids = ([row["decision"]] if row["decision"].startswith("draft:")
                       else _decisions.by_reg(row["decision"]) if row["decision"] else [])
            flags.append({"n": int(row["n"]), "check": row["rule"], "rule_uz": row["rule_uz"],
                          "reg_number": row["decision"], "decision_id": ids[0] if ids else "", "body": row["body"],
                          "date": row["date"], "url": row["url"], "status": row["status"],
                          "evidence_quote": row["evidence_quote"], "law": row["law"], "law_quote": row["law_quote"],
                          "law_url": row["law_url"]})
    md = GROUP_QUESTIONS.read_text(encoding="utf-8") if GROUP_QUESTIONS.exists() else ""
    groups = [{"question": int(m.group(1)), "text": m.group(2).strip(), "flags": int(m.group(3))}
              for m in re.finditer(r"^## (\d+)\. (.+?)\n\n(\d+) flags", md, re.MULTILINE | re.DOTALL)]
    with _reviews() as con:
        answers = [{"question": q, "reviewer": rv, "answer": a, "note": n}
                   for q, rv, a, n in con.execute("SELECT question, reviewer, answer, note FROM group_answers")]
    return {"flags": flags, "groups": groups, "answers": answers}


@app.post("/api/group-answers")
def save_group_answer(g: GroupAnswer) -> dict:
    with _reviews_lock, _reviews() as con:
        con.execute("INSERT OR REPLACE INTO group_answers VALUES(?,?,?,?,?)",
                    (g.question, g.reviewer, g.answer, g.note, dt.datetime.now().isoformat(timespec="seconds")))
    return {"ok": True}


@app.get("/review")
def review_page() -> FileResponse:
    return FileResponse(WEB / "review.html")


@app.get("/api/stats")
def stats() -> dict:
    drafts = _drafts(dt.date.today())
    kengash = [d for d in drafts if "kengash" in d["creator"].lower() and not is_budget_allocation(d.get("title"))]
    return {
        "court": COURT,
        "drafts_scanned": len(drafts),
        "kengash_drafts": len(kengash),
        "kengash_short": sum(d["days"] < MIN_DISCUSSION_DAYS for d in kengash),
        "decisions_in_store": _decisions.con.execute("SELECT count(*) FROM decisions").fetchone()[0],
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")
