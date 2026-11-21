"""Build tmp_real/sorov.sqlite = every E-qaror row we hold + lex.uz decisions the E-qaror data lacks, with the real Mezon result.
Run with the platform Python:  python tools/build_sorov.py   (needs tmp_real/eqaror.sqlite, tmp_real/audit_all.json)"""
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC, DST = ROOT / "tmp_real" / "eqaror.sqlite", ROOT / "tmp_real" / "sorov.sqlite"
audit = json.loads((ROOT / "tmp_real" / "audit_all.json").read_text(encoding="utf-8"))
organs = json.loads((ROOT / "tmp_real" / "eqaror_subset.json").read_text(encoding="utf-8"))["organs"]
REG = {1: "Andijon viloyati", 2: "Buxoro viloyati", 3: "Jizzax viloyati", 4: "Qashqadaryo viloyati", 5: "Navoiy viloyati",
       6: "Namangan viloyati", 7: "Samarqand viloyati", 8: "Surxondaryo viloyati", 9: "Sirdaryo viloyati", 10: "Toshkent viloyati",
       11: "Farg‘ona viloyati", 12: "Xorazm viloyati", 13: "Qoraqalpog‘iston Respublikasi", 14: "Toshkent shahri"}


def organ(r, d, kengash):
    o = (organs.get(f"{r}-{d}") or "").replace("’", "‘").replace("'", "‘")
    if not o:
        return ""
    if kengash:
        o = o.replace("hokimligi", "Kengashi")
    return o if d == 0 else f"{REG.get(r, '')} {o}".strip()


if DST.exists():
    DST.unlink()
shutil.copy(SRC, DST)
c = sqlite3.connect(DST)
for col in ("src text", "lexid text", "has_text int default 0", "flags int default 0", "st int default 0", "checks text"):
    c.execute(f"alter table rows add column {col}")
c.execute("update rows set src='E-qaror', st=0, has_text=0, flags=0")
have = {r[0] for r in c.execute("select n from rows")}
matched = lexonly = 0
for reg, v in audit.items():
    lexid = (v["url"] or "").rsplit("/", 1)[-1].lstrip("-")
    fl = v["flags"]
    if fl < 0:
        continue
    nh, nu = v.get("n_high", fl), v.get("n_unclear", 0)
    st = 1 if nh > 0 else (3 if nu > 0 else 2)
    fl = nh if st == 1 else nu
    if reg in have:
        c.execute("update rows set has_text=1, flags=?, st=?, lexid=?, checks=?, src='E-qaror + lex.uz' where n=?", (fl, st, lexid, ",".join(v.get("checks") or []), reg))
        matched += 1
    else:
        kg = "-K/" in reg
        typ = "Kengash qarori" if kg else ("Hokim farmoyishi" if v["type"] == "F" else "Hokim qarori")
        c.execute("insert into rows(code,d,o,n,t,ty,h,nm,r,dist,s,rel,x,src,lexid,has_text,flags,st,checks) values(?,?,?,?,?,?,0,0,?,?,?,0,0,'lex.uz',?,1,?,?,?)",
                  (f"lex-{lexid}", (v["adopted"] or "")[:10], organ(v["region"] or 0, v["district"] or 0, kg) or (v["body"] or ""), reg,
                   (v["title"] or "").replace("ʻ", "‘").replace("ʼ", "’"), typ, v["region"] or 0, v["district"] or 0, "lex_only", lexid, fl, st, ",".join(v.get("checks") or [])))
        lexonly += 1
import re as _re
STORE = sqlite3.connect(r"file:D:\10_projects\mezon\data\store\decisions.sqlite?mode=ro", uri=True)
for col in ("lost text", "canc text", "canc_url text", "canc_date text", "canc_why text"):
    c.execute(f"alter table rows add column {col}")
REGX = _re.compile(r"\b(?:\d{1,4}-\d{1,2}-\d{1,3}-[QF]/\d{2}|[IVX]{1,4}-\d{1,3}-\d{1,4}-\d{1,2}-\d{1,3}-K/\d{2})\b")
canc = {}
WHY = [(_re.compile(r"adliya[^.]{0,260}?taqdimnoma[^\s,.]*", _re.I | _re.S), "adliya taqdimnomasi"),
       (_re.compile(r"prokuror[^.]{0,200}?protest[^\s,.]*", _re.I | _re.S), "prokuror protesti"),
       (_re.compile(r"sudning[^.]{0,200}?(?:hal qiluv qarori|ajrimi)", _re.I | _re.S), "sud qarori")]
def _why(text):
    t = " ".join((text or "").split())
    for rx, kind in WHY:
        m = rx.search(t)
        if m:
            return kind + ": " + m.group(0)[:220]
    return None
for reg, cn, url, adopted, text in STORE.execute("select reg_number, cancelled_numbers, url, adopted, text from decisions where role='cancelling' and cancelled_numbers!=''"):
    for x in REGX.findall(cn or ""):
        canc.setdefault(x, (reg, url, adopted, _why(text)))
n_lost = 0
for reg, lf in STORE.execute("select reg_number, lost_force from decisions where role in ('adopted','cancelling') and length(text)>300"):
    cc = canc.get(reg)
    if lf or cc:
        c.execute("update rows set lost=?, canc=?, canc_url=?, canc_date=?, canc_why=? where n=?", (lf or None, cc[0] if cc else None, cc[1] if cc else None, cc[2] if cc else None, cc[3] if cc else None, reg))
        n_lost += 1
print("lost/cancelled rows", n_lost)
c.execute("create index i_st_d on rows(st, d desc)")
c.execute("create index i_src on rows(src)")
c.commit()
print("rows", c.execute("select count(*) from rows").fetchone()[0], "matched", matched, "lex-only", lexonly)
print(c.execute("select st, count(*) from rows group by st").fetchall())
