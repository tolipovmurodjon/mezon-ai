"""Real E-qaror data: the full set of API rows we hold (SQLite, built read-only from the L40S download)."""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tmp_real" / "eqaror_subset.json"   # per-slice totals + organ names by region-district
DB = ROOT / "tmp_real" / "sorov.sqlite"            # every row we hold + lex.uz decisions + the real Mezon result
LEX_DB = Path(os.environ.get("MEZON_REPO", r"D:\10_projects\mezon")) / "data" / "store" / "decisions.sqlite"
AUDIT_CACHE = ROOT / "tmp_real" / "eqaror_audit_cache.json"
REGION_NAMES = {
    1: "Andijon viloyati", 2: "Buxoro viloyati", 3: "Jizzax viloyati", 4: "Qashqadaryo viloyati", 5: "Navoiy viloyati",
    6: "Namangan viloyati", 7: "Samarqand viloyati", 8: "Surxondaryo viloyati", 9: "Sirdaryo viloyati",
    10: "Toshkent viloyati", 11: "Farg‘ona viloyati", 12: "Xorazm viloyati", 13: "Qoraqalpog‘iston Respublikasi",
    14: "Toshkent shahri",
}
SLICE_LABELS = {"hokim_qaror": "Hokim qarori / farmoyishi", "kengash": "Kengash qarori", "kengash_rais": "Kengash raisi farmoyishi",
                "normative": "Normativ hujjatlar", "declared_invalid": "Haqiqiy emas deb topilgan", "lex_only": "lex.uz qarori (E-qaror ma’lumotida yo‘q)"}
TYPES = ["Hokim qarori", "Hokim farmoyishi", "Kengash qarori", "Kengash raisi farmoyishi"]
_c = {}


def load():
    if "d" not in _c:
        _c["d"] = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"slices": {}, "rows": [], "organs": {}}
    return _c["d"]


def organ_for(region, district, kengash=False):
    """Full organ name from region + district number, or '' if unknown."""
    org = (load()["organs"].get(f"{region}-{district}") or "").replace("’", "‘").replace("'", "‘")
    if not org:
        return ""
    if kengash:
        org = org.replace("hokimligi", "Kengashi")
    return org if district == 0 else f"{REGION_NAMES.get(region, '')} {org}".strip()


def con():
    if "con" not in _c:
        _c["con"] = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
        _c["con"].row_factory = sqlite3.Row
    return _c["con"]


def districts(region):
    out = []
    for k, v in load()["organs"].items():
        r, d = k.split("-")
        if int(r) == region and int(d) > 0:
            out.append((d, v))
    return sorted(out, key=lambda x: x[1])


def _where(q="", region="", dist="", tur="", norm="", dan="", gacha="", st="", skip=()):
    where, args = [], []
    if st in ("0", "1", "2", "3") and "st" not in skip:
        where.append("st=?"); args.append(int(st))
    if region.isdigit() and "r" in skip:
        region = ""
    if region.isdigit():
        where.append("r=?"); args.append(int(region))
    if dist.isdigit():
        where.append("dist=?"); args.append(int(dist))
    if tur in TYPES:
        where.append("ty=?"); args.append(tur)
    if norm in ("0", "1"):
        where.append("nm=?"); args.append(int(norm))
    if dan:
        where.append("d>=?"); args.append(dan)
    if gacha:
        where.append("d<=?"); args.append(gacha)
    if q:
        where.append("(n LIKE ? OR o LIKE ? OR t LIKE ?)"); args += [f"%{q}%"] * 3
    return (" WHERE " + " AND ".join(where)) if where else "", args


_COUNTS = {}


def counts(q="", region="", dist="", tur="", norm="", dan="", gacha="", st=""):
    """Cached per filter set until sorov.sqlite is rebuilt (searches scan 446K rows)."""
    key = (DB.stat().st_mtime if DB.exists() else 0, q, region, dist, tur, norm, dan, gacha, st)
    if key not in _COUNTS:
        if len(_COUNTS) > 500:
            _COUNTS.clear()
        _COUNTS[key] = _counts(q, region, dist, tur, norm, dan, gacha, st)
    return _COUNTS[key]


def _counts(q="", region="", dist="", tur="", norm="", dan="", gacha="", st=""):
    """Real counts for the tabs (per status) and for the region filter, under the other active filters."""
    c = con()
    w, a = _where(q, region, dist, tur, norm, dan, gacha, st, skip=("st",))
    tabs = {r[0]: r[1] for r in c.execute(f"SELECT st, count(*) FROM rows{w} GROUP BY st", a)}
    w2, a2 = _where(q, "", dist, tur, norm, dan, gacha, st)
    regs = {r[0]: r[1] for r in c.execute(f"SELECT r, count(*) FROM rows{w2} GROUP BY r", a2)}
    return tabs, regs


def query(q="", region="", dist="", tur="", norm="", dan="", gacha="", sort="new", page=1, per=25, st=""):
    w, args = _where(q, region, dist, tur, norm, dan, gacha, st)
    c = con()
    tk = (DB.stat().st_mtime if DB.exists() else 0, "total", w, tuple(args))
    if tk not in _COUNTS:
        _COUNTS[tk] = c.execute("SELECT count(*) FROM rows" + w, args).fetchone()[0]
    total = _COUNTS[tk]
    order = "d DESC" if sort != "old" else "d ASC"
    rows = c.execute(f"SELECT * FROM rows{w} ORDER BY {order} LIMIT ? OFFSET ?", args + [per, (page - 1) * per]).fetchall()
    return total, [dict(r) for r in rows]


def get(code):
    r = con().execute("SELECT * FROM rows WHERE code=?", (code,)).fetchone()
    return dict(r) if r else None


def slice_counts():
    have = {r[0]: r[1] for r in con().execute("SELECT s, count(*) FROM rows GROUP BY s")}
    sl = load()["slices"]
    return [{"label": SLICE_LABELS.get(k, k), "have": have.get(k, 0), "api_total": sl.get(k, {}).get("api_total", 0)} for k in SLICE_LABELS]


def lex_match(number):
    """The same decision in our lex.uz store (real text + real reg number), or None."""
    if not number or not LEX_DB.exists():
        return None
    c = sqlite3.connect(f"file:{LEX_DB}?mode=ro", uri=True)
    r = c.execute("SELECT id, title, text, url, adopted FROM decisions WHERE reg_number=? AND length(text)>300 "
                  "ORDER BY length(text) DESC LIMIT 1", (number,)).fetchone()
    c.close()
    return {"id": r[0], "title": r[1], "text": r[2], "url": r[3], "adopted": r[4]} if r else None


def audit(number, text, title):
    """Real Mezon rule report for this decision (cached)."""
    from .ai.real import audit_live, real_report
    rep = real_report(number)
    if rep:
        return rep
    cache = json.loads(AUDIT_CACHE.read_text(encoding="utf-8")) if AUDIT_CACHE.exists() else {}
    if number not in cache:
        cache[number] = audit_live(text, title)
        AUDIT_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache[number]


LAWS_CACHE = ROOT / "tmp_real" / "eqaror_laws_cache.json"


def laws(code, text, date):
    """Law cards for the acts + articles cited in this decision's basis, read as of its date (mezon.tools.law_as_of)."""
    import subprocess
    cache = json.loads(LAWS_CACHE.read_text(encoding="utf-8")) if LAWS_CACHE.exists() else {}
    if code in cache:
        return cache[code]
    p = subprocess.run([os.environ.get("MEZON_PY", r"D:\10_projects\mezon\.venv\Scripts\python.exe"), "-X", "utf8", str(ROOT / "tools" / "laws_for.py")],
                       input=json.dumps({"text": text, "date": date}).encode("utf-8"), capture_output=True, timeout=120,
                       cwd=os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"))
    cards = json.loads(p.stdout.decode("utf-8")) if p.returncode == 0 and p.stdout else []
    cache[code] = cards
    LAWS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache[code]


ORIG = ROOT / "tmp_real" / "orig"


def _lex_cache_dirs():
    out = []
    f = Path(os.environ.get("MEZON_REPO", r"D:\10_projects\mezon")) / "data" / "cache_root.txt"
    if f.exists():
        out.append(Path(f.read_text(encoding="utf-8").strip()) / "lexuz")
    out.append(Path(os.environ.get("MEZON_REPO", r"D:\10_projects\mezon")) / "data" / "cache" / "lexuz")
    return out


def original_pdf(lexid):
    """The real lex.uz PDF of a decision, unmodified. Cached on disk; fetched once from lex.uz on first request
    (the file link named on the decision's own page; one polite request)."""
    import re
    import urllib.request
    import zipfile
    lexid = re.sub(r"\D", "", str(lexid))
    ORIG.mkdir(parents=True, exist_ok=True)
    out = ORIG / f"{lexid}.pdf"
    if out.exists() and out.stat().st_size > 0:
        return out
    html = ""
    for d in _lex_cache_dirs():
        p = d / "docs" / f"{lexid}.html"
        if p.exists():
            html = p.read_text(encoding="utf-8", errors="replace")
            break
    hdr = {"User-Agent": "Mozilla/5.0 (Mezon platform; polite)"}
    if not html:
        for u in (f"https://lex.uz/uz/docs/-{lexid}", f"https://lex.uz/uz/docs/{lexid}"):
            try:
                html = urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=40).read().decode("utf-8", "replace")
                break
            except Exception:
                continue
    links = re.findall(r"/uz/files/(-?\d+)\.(pdf|zip)", html)
    links.sort(key=lambda x: x[1] != "pdf")
    for fid, ext in links:
        url = f"https://lex.uz/uz/files/{fid.lstrip('-')}.{ext}"
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60).read()
        except Exception:
            continue
        if ext == "zip":
            import io
            z = zipfile.ZipFile(io.BytesIO(data))
            names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
            if not names:
                continue
            data = z.read(names[0])
        if data[:4] == b"%PDF":
            out.write_bytes(data)
            return out
    return None


_DASH = {"key": None, "data": None}


def dashboard_data():
    """Home page data, recomputed only when sorov.sqlite changes (it is rebuilt, never edited in place)."""
    import time as _t
    key = (DB.stat().st_mtime if DB.exists() else 0, int(_t.time() // 600))  # file version + 10-minute window
    if _DASH["key"] != key:
        _DASH["data"], _DASH["key"] = _dashboard_data(), key
    return _DASH["data"]


def _dashboard_data():
    """Everything on the home page comes from sorov.sqlite (the real rows + the real Mezon result)."""
    import datetime as dt
    c = con()
    tot = {r[0]: r[1] for r in c.execute("SELECT st, count(*) FROM rows GROUP BY st")}
    newest = c.execute("SELECT max(d) FROM rows").fetchone()[0] or dt.date.today().isoformat()
    end = dt.date.fromisoformat(newest)
    wk = (end - dt.timedelta(days=7)).isoformat()
    new7 = {r[0]: r[1] for r in c.execute("SELECT st, count(*) FROM rows WHERE d>? GROUP BY st", (wk,))}
    days = [(end - dt.timedelta(days=i)) for i in range(29, -1, -1)]
    by = {}
    for d, st, n in c.execute("SELECT d, st, count(*) FROM rows WHERE d>=? GROUP BY d, st", (days[0].isoformat(),)):
        by.setdefault(d, {})[st] = n
    chart = []
    for d in days:
        x = by.get(d.isoformat(), {})
        chart.append({"label": f"{d.day}.{d.month:02d}", "t": d.isoformat(), "a": x.get(2, 0), "c": x.get(1, 0), "b": x.get(0, 0)})
    spark = lambda st: [sum(by.get((end - dt.timedelta(days=6 - i)).isoformat(), {}).get(st, 0) for _ in [0]) for i in range(7)]  # noqa: E731
    regions = []
    for r, n1, n3, n2, n0 in c.execute("SELECT r, sum(st=1), sum(st=3), sum(st=2), sum(st=0) FROM rows WHERE r>0 GROUP BY r"):
        regions.append({"r": r, "name": REGION_NAMES.get(r, str(r)), "flag": n1, "unclear": n3, "clean": n2, "none": n0})
    regions.sort(key=lambda x: -x["flag"])
    flagged = [dict(x) for x in c.execute("SELECT * FROM rows WHERE st=1 ORDER BY d DESC LIMIT 8")]
    for x in flagged:
        x["region"] = REGION_NAMES.get(x["r"], "")
    total = sum(tot.values())
    kpis = [
        {"label": "Jami qaror", "value": total, "new": sum(new7.values()), "spark": [sum(by.get((end - dt.timedelta(days=6 - i)).isoformat(), {}).values()) for i in range(7)]},
        {"label": "Ehtimoliy buzilish", "value": tot.get(1, 0), "new": new7.get(1, 0), "spark": spark(1)},
        {"label": "Ekspert tekshiradi", "value": tot.get(3, 0), "new": new7.get(3, 0), "spark": spark(3)},
        {"label": "Muammo topilmadi", "value": tot.get(2, 0), "new": new7.get(2, 0), "spark": spark(2)},
        {"label": "Matnsiz", "value": tot.get(0, 0), "new": new7.get(0, 0), "spark": spark(0)},
    ]
    analysed = tot.get(1, 0) + tot.get(2, 0) + tot.get(3, 0)
    verdicts = [{"key": "conflict", "label": "Ehtimoliy buzilish", "n": tot.get(1, 0), "pct": round(100 * tot.get(1, 0) / analysed) if analysed else 0},
                {"key": "minor", "label": "Ekspert tekshiradi", "n": tot.get(3, 0), "pct": round(100 * tot.get(3, 0) / analysed) if analysed else 0},
                {"key": "compliant", "label": "Muammo topilmadi", "n": tot.get(2, 0), "pct": round(100 * tot.get(2, 0) / analysed) if analysed else 0}]
    return {"kpis": kpis, "chart": chart, "verdicts": verdicts, "analysed": analysed, "flagged": flagged, "regions": regions, "newest": newest, "total": total}
