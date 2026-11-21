"""A one-page report for a regional adliya head: the queue, dead-article citations, repeats, O'RQ-860 factors."""

import csv
import datetime as dt
import json
import re
from pathlib import Path

from mezon.version import ruleset
from research import regnum

LISTED = Path(__file__).resolve().parents[1] / "data" / "interim" / "listed_in_force.csv"
SNAPSHOTS = Path(__file__).resolve().parents[1] / "data" / "interim" / "snapshots"


def previous(region_code: int, today: str) -> tuple[str, dict] | None:
    """The newest snapshot taken before today for this region (research/snapshot.py), if any."""
    if not SNAPSHOTS.exists():
        return None
    for path in sorted(SNAPSHOTS.glob("*.json"), reverse=True):
        if path.stem < today:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if str(region_code) in data:
                return path.stem, {**data[str(region_code)], "_ruleset": data.get("_ruleset", "")}
    return None


def _delta(now: int, before: dict | None, key: str) -> str:
    if not before or key not in before:
        return ""
    diff = now - before[key]
    return f" (o'tgan safar {before[key]} ta, {'+' if diff > 0 else ''}{diff})" if diff else f" (o'tgan safar ham {now} ta)"


SHORT_UZ = {
    "R_basis": "kuchini yo'qotgan modda yoki hujjatga tayanadi", "R_duplicate": "amaldagi qarorning nusxasi",
    "R_double_repeal": "bekor qilingan qarorni qayta bekor qiladi", "R_expertise": "adliya ekspertizasi qayd etilmagan",
    "R_discussion": "jamoatchilik muhokamasi qayd etilmagan", "R_retroactive": "orqaga qaytish kuchi",
    "R_business_3m": "tadbirkorga 3 oydan oldin majburiyat", "R_tax_timing": "soliq stavkasi muddati",
    "R_competence_land": "yer bo'yicha vakolat", "R_form": "farmoyish shakli",
    "R_corruption_factor": "korrupsiyani keltirib chiqaruvchi omil (O'RQ-860)",
    "R_discussion_short": "muhokama 15 kundan qisqa", "R_draft_window": "muhokama tugamasdan kuchga kiradi",
}


def _line(item: dict) -> str:
    checks = ", ".join(SHORT_UZ.get(c, c) for c in item["checks"])
    who = (item.get("body") or "").strip() or (item.get("title") or "")[:70]
    return f"  - {item['reg_number']} ({item['adopted']}) {who}: {checks}\n    {item['url']}"


def _left(before: dict | None, queue_items: list[dict], lookup) -> list[str]:
    """Decisions in the last snapshot's queue that are no longer flagged, each with the reason Mezon can see."""
    if not before or "ids" not in before:
        return []
    now = {i["id"] for i in queue_items}
    lines = []
    for did in before["ids"].get("flagged", []):
        if did in now:
            continue
        d = lookup(did) if lookup else None
        if not d:
            why = "bazada topilmadi: qayta tekshiring"
        elif d.get("lost_force"):
            why = f"kuchini yo'qotgan ({d['lost_force']}, lex.uz)"
        else:
            why = "endi belgilanmaydi (tuzatilgan yoki qayta qabul qilingan): ekspert tasdiqlasin"
        lines.append(f"  - {(d or {}).get('reg_number') or did}: {why}")
    return lines


def build(region_code: int, region_name: str, queue_items: list[dict], flags: dict[str, list[dict]],
          lookup=None) -> str:
    today = dt.date.today().isoformat()
    hard = [i for i in queue_items if i["n_hard"]]
    dead = [i for i in queue_items if "R_basis" in i["checks"]]
    repeats = [i for i in queue_items if {"R_duplicate", "R_double_repeal"} & set(i["checks"])]
    factors = []
    for i in queue_items:
        for f in flags.get(i["id"], []):
            if f["check"] == "R_corruption_factor":
                m = re.search(r"factor (\d+): (.+)", f["title"])
                factors.append((i, m.group(1) if m else "", m.group(2) if m else f["title"]))
    listed = []
    if LISTED.exists():
        with LISTED.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                p = regnum.parse(r["older"]) or {}
                if p.get("region") == region_code:
                    listed.append(r)
    prev = previous(region_code, today)
    version = ruleset()
    same = bool(prev) and prev[1].get("_ruleset") == version
    before = prev[1] if same else None
    dead_n, rep_n = len(dead), len(repeats)
    out = [
        f"HUDUDIY ADLIYA UCHUN HISOBOT (LOYIHA): {region_name}",
        f"Sana: {today}. Mezon tomonidan tayyorlangan; har bir belgini ekspert hal qiladi (AI etikasi qoidalari, 3787-son).",
        "Belgilangan ≠ noqonuniy: bu ko'rib chiqish ro'yxati, ayblov emas.",
        "",
        (f"Taqqoslash: {prev[0]} holatiga nisbatan." if same else
         f"Taqqoslash qilinmadi: {prev[0]} dagi holat boshqa qoidalar versiyasi bilan olingan." if prev else
         "Taqqoslash: avvalgi holat saqlanmagan."),
        f"Mezon qoidalari versiyasi: {version}",
        "",
        (f"1. Ko'rib chiqish navbati: {len(queue_items)} ta qaror belgilangan{_delta(len(queue_items), before, 'flagged')}, "
        f"{len(hard)} tasida ehtimoliy qoidabuzarlik."),
        "   Eng muhim 10 tasi:",
        *[_line(i) for i in queue_items[:10]],
        "",
        (f"2. Qabul qilingan kuni kuchini yo'qotgan modda yoki hujjatga tayanadigan qarorlar: {dead_n} ta"
        f"{_delta(dead_n, before, 'dead_article')}."),
        "   Tuzatish: muqaddimada hozir amalda bo'lgan moddani ko'rsatish.",
        *[_line(i) for i in dead[:15]],
        "",
        f"3. Nusxa yoki takroriy bekor qilish (yuridik-texnik xato): {rep_n} ta{_delta(rep_n, before, 'repeats')}.",
        *[_line(i) for i in repeats[:10]],
        "",
        f"4. Korrupsiyani keltirib chiqaruvchi ehtimoliy omillar (O'RQ-860, 11-15-moddalar): {len(factors)} ta.",
        *[f"  - {i['reg_number']}: {n}-omil, {name}\n    {i['url']}" for i, n, name in factors[:10]],
        "",
        f"5. Reyestrni tozalash: nusxasi qabul qilingan, lekin lex.uz da hamon amalda ko'rsatilgan qarorlar: {len(listed)} ta.",
        ("   (NHH to'g'risidagi Qonun, 46-modda 1-qism: yangi hujjat bilan qamrab olingan eski hujjatlar kuchini yo'qotgan deb "
        "topilishi kerak.)"),
        *[f"  - {r['older']} ({r['older_adopted']}); keyingi nusxalar: {r['newer_copies']}\n    {r['older_url']}"
          for r in listed],
        "",
        *(["6. O'tgan safardan beri ro'yxatdan chiqqan qarorlar va sababi:", *left, ""] if (left := _left(
            before, queue_items, lookup)) else []),
        "Hisobotni tayyorlagan: Mezon. Tekshirgan ekspert: ____________________   Sana: __________",
    ]
    return "\n".join(out)
