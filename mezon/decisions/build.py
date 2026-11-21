"""Build the decision store (SQLite) from the measured research outputs in data/interim."""

import csv
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from mezon.config import DATA, DECISIONS_DB, STORE
from research import regnum, textnorm

INTERIM = DATA / "interim"
CACHES = [DATA / "cache"] + ([Path(os.environ["MEZON_CACHE"])] if os.environ.get("MEZON_CACHE") else [])

SCHEMA = """
CREATE TABLE decisions (
  id TEXT PRIMARY KEY, src_id TEXT, source TEXT, role TEXT,
  reg_number TEXT, type TEXT, region INTEGER, district INTEGER, year INTEGER,
  body TEXT, title TEXT, adopted TEXT, entry_into_force TEXT, published TEXT, lost_force TEXT,
  is_normative INTEGER, url TEXT, text TEXT, clauses TEXT, stages TEXT,
  label TEXT, trigger TEXT, cancelled_numbers TEXT,
  disc_start TEXT, disc_end TEXT, proposals INTEGER
);
CREATE INDEX ix_reg ON decisions(reg_number);
CREATE INDEX ix_body ON decisions(region, district, type);
"""


def iso(s: str | None) -> str:
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else ""


def read_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def lex_text(doc_id: str, hint: str | None = None) -> str:
    aid = str(doc_id).lstrip("-")
    paths = [Path(hint)] if hint else []
    for root in CACHES:
        paths.append(root / "lexuz" / "text" / f"{aid}.txt")
        paths += sorted((root / "lexuz" / "zip" / aid).glob("*.txt"))
    for p in paths:
        if p.exists() and p.stat().st_size:
            return read_text(p)
    return ""


def draft_text(draft_id: str, pdf_ids: str) -> str:
    out = []
    for pdf in pdf_ids.split()[:2]:
        for root in CACHES:
            p = root / "regulation" / f"d{draft_id}_{pdf}.txt"
            if p.exists() and p.stat().st_size:
                out.append(read_text(p))
                break
    return "\n".join(out)


def rows(name: str) -> list[dict]:
    p = INTERIM / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _reg_fields(reg: str) -> dict:
    p = regnum.parse(reg or "") or {}
    return {
        "type": p.get("type"),
        "region": p.get("region"),
        "district": p.get("district"),
        "year": p.get("year"),
    }


def _stages(raw: str) -> dict:
    try:
        return {name: int(done) for name, done in json.loads(raw)}
    except (ValueError, TypeError):
        return {}


def _record(**kw) -> dict:
    rec = dict.fromkeys(
        [
            "id",
            "src_id",
            "source",
            "role",
            "reg_number",
            "body",
            "title",
            "adopted",
            "entry_into_force",
            "published",
            "lost_force",
            "is_normative",
            "url",
            "text",
            "stages",
            "label",
            "trigger",
            "cancelled_numbers",
            "disc_start",
            "disc_end",
            "proposals",
        ]
    )
    rec.update(kw)
    rec.update(_reg_fields(rec["reg_number"]))
    rec["stages"] = rec["stages"] or {}
    return rec


def collect() -> list[dict]:
    labels = {r["lex_uz_id"].lstrip("-"): r for r in rows("cancellation_labels.csv")}
    cancelled_by: dict[str, str] = {}
    for r in labels.values():
        for n in (r.get("cancelled_numbers") or "").split():
            if r["label"] in ("POSITIVE", "EXCLUDE"):
                cancelled_by.setdefault(n, r["label"])
    recs: dict[str, dict] = {}

    def lex(d: dict, role: str, label: str | None, trigger: str = "", cancelled: str = "") -> None:
        key = f"lex:{d['id'].lstrip('-')}"
        if key in recs:
            if label and recs[key]["label"] in (None, "none"):
                recs[key]["label"] = label
            return
        text = lex_text(d["id"], d.get("text_path"))
        recs[key] = _record(
            id=key,
            src_id=d["id"],
            source="lex.uz",
            role=role,
            reg_number=d.get("number") or "",
            body=d.get("body_name") or (d.get("header") or "").split(",")[0],
            title=d.get("title") or "",
            adopted=iso(d.get("date")),
            entry_into_force=iso(d.get("entry_into_force")),
            lost_force=iso(d.get("lost_force")),
            url=d.get("url") or "",
            text=text,
            label=label or "none",
            trigger=trigger,
            cancelled_numbers=cancelled,
        )

    for d in json.loads((INTERIM / "cancel_docs.json").read_text(encoding="utf-8")):
        lab = labels.get(d["id"].lstrip("-"), {})
        lex(d, "cancelling", lab.get("label"), lab.get("trigger", ""), lab.get("cancelled_numbers", ""))
    for d in json.loads((INTERIM / "district_docs.json").read_text(encoding="utf-8")):
        lex(d, "adopted", cancelled_by.get(d.get("number") or ""))
    for r in rows("positive_originals.csv"):
        if r.get("resolved") == "True" and r.get("original_id"):
            d = {
                "id": r["original_id"],
                "number": r["original_number"],
                "date": r["original_date"],
                "title": r["original_title"],
                "url": r["original_url"],
            }
            lex(d, "adopted", "POSITIVE", r.get("trigger", ""))

    crawled = STORE / "lexuz_local.sqlite"
    if crawled.exists():
        con = sqlite3.connect(f"file:{crawled}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        for d in con.execute("SELECT * FROM decisions WHERE length(coalesce(text,'')) > 0"):
            key = f"lex:{d['lex_id'].lstrip('-')}"
            lost = d["lost_force"] or lost_from_note(d["sharhi"])
            if key in recs:
                old = recs[key]
                old["lost_force"] = old["lost_force"] or lost or ""
                if not old["text"]:
                    old["text"] = d["text"]
                    old["entry_into_force"] = old["entry_into_force"] or d["entry_into_force"] or ""
                    old["title"] = old["title"] or d["title"] or ""
                continue
            recs[key] = _record(
                id=key, src_id=d["lex_id"], source="lex.uz", role="adopted", reg_number=d["number"] or "",
                body=(d["header"] or "").split(",")[0], title=d["title"] or "", adopted=d["adopted"] or "",
                entry_into_force=d["entry_into_force"] or "", lost_force=lost or "", url=d["url"] or "",
                text=d["text"], label=cancelled_by.get(d["number"] or "", "none"),
            )
        con.close()

    by_reg = {r["reg_number"]: r for r in recs.values() if r["reg_number"]}

    def attach(reg: str, stages: dict, normative, **extra) -> bool:
        target = by_reg.get(reg)
        if not target:
            return False
        target["stages"] = target["stages"] | stages
        if normative not in ("", None) and target["is_normative"] is None:
            target["is_normative"] = int(normative)
        for k, v in extra.items():
            if v and target.get(k) in (None, "", "none"):  # "none" is the builder's "no label yet"
                target[k] = v
        return True

    for r in rows("eqaror_stages.csv") + rows("case_designcode_eqaror.csv"):
        stages = _stages(r.get("all_stages_json", ""))
        normative = r.get("is_normative")
        if normative in (None, "") and "Normativ" in (r.get("content_label") or ""):
            normative = "1"
        label = "POSITIVE" if r.get("set") == "bad" else None
        if attach(r["reg_number"], stages, normative, label=label):
            continue
        key = f"eq:{r['url'].rstrip('/').rsplit('/', 1)[-1]}"
        recs[key] = by_reg[r["reg_number"]] = _record(
            id=key,
            src_id=r["url"],
            source="e-qaror",
            role="adopted",
            reg_number=r["reg_number"],
            body=r.get("body", ""),
            title=r.get("title", ""),
            adopted=iso(r.get("date")),
            is_normative=int(normative) if normative not in ("", None) else None,
            url=r["url"],
            text="",
            stages=stages,
            label=label or "none",
            trigger=r.get("asos_kind", ""),
        )
    for r in rows("eqaror_stages_observed.csv"):
        stages = {
            "Jamoatchilik muhokamasi": int(r["discussion_done"]),
            "Huquqiy ekspertiza": int(r["expertise_done"]),
        }
        if attach(r["reg_number"], stages, r["is_normative"]):
            continue
        key = f"eq:obs:{r['reg_number']}"
        recs[key] = by_reg[r["reg_number"]] = _record(
            id=key,
            src_id=r["url"],
            source="e-qaror (observed)",
            role="adopted",
            reg_number=r["reg_number"],
            body=r["body"],
            title="",
            adopted=iso(r["date"]),
            is_normative=int(r["is_normative"]) if r["is_normative"] else None,
            url=r["url"],
            text="",
            stages=stages,
            label=cancelled_by.get(r["reg_number"], "none"),
        )
    for r in rows("regulation_window.csv"):
        key = f"draft:{r['id']}"
        recs[key] = _record(
            id=key,
            src_id=r["id"],
            source="regulation.gov.uz",
            role="draft",
            reg_number="",
            body=r["creator"],
            title=r["title"],
            url=r["url"],
            text=draft_text(r["id"], r.get("pdf_ids", "")),
            label="none",
            disc_start=iso(r["start"]),
            disc_end=iso(r["end"]),
            proposals=int(r["proposals"] or 0),
        )
    return list(recs.values())


_LOST_NOTE = re.compile(r"kuchini yoqot|bekor qilin|haqiqiy emas deb topil")


def lost_from_note(note: str | None) -> str:
    """The lost-force date in a LexUZ note ("... 2022 yil 31 dekabrdan o'z kuchini yo'qotadi", or the date of the
    cancelling decision it names), as ISO; "" when the note does not say the act lost force or names no date.
    lex.uz often fills the note but not the lost-force field (21 of 59 crawled decisions, 19.11.2026)."""
    from research.regulation_window import _dates
    from research.textnorm import fold

    f = fold(note or "")
    if not _LOST_NOTE.search(f):
        return ""
    explicit = re.search(r"(20\d\d yil(?:ning)? \d{1,2} \w+?)dan\b[^.]{0,60}kuchini yoqot", f)
    if explicit and (ds := _dates(explicit.group(1))):
        return ds[0][1].isoformat()
    ds = _dates(f)
    return ds[0][1].isoformat() if ds else ""


def build(db: Path = DECISIONS_DB) -> int:
    recs = collect()
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    cols = [
        "id",
        "src_id",
        "source",
        "role",
        "reg_number",
        "type",
        "region",
        "district",
        "year",
        "body",
        "title",
        "adopted",
        "entry_into_force",
        "published",
        "lost_force",
        "is_normative",
        "url",
        "text",
        "clauses",
        "stages",
        "label",
        "trigger",
        "cancelled_numbers",
        "disc_start",
        "disc_end",
        "proposals",
    ]
    for r in recs:
        r["clauses"] = json.dumps(
            textnorm.split_decision(r["text"])["clauses"] if r["text"] else [], ensure_ascii=False
        )
        r["stages"] = json.dumps(r["stages"], ensure_ascii=False)
        con.execute(
            f"INSERT INTO decisions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [r.get(c) for c in cols],
        )
    con.commit()
    con.close()
    return len(recs)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DECISIONS_DB
    print(f"{build(out)} decisions -> {out}")
