"""
python manage.py seed_real

Wipes the synthetic rows and loads REAL local decisions (lex.uz) with their real
Mezon rule-engine reports (tmp_real/real.json, exported from D:/10_projects/mezon).
No invented people: the issuer is the organ ("Qarshi tumani hokimligi").
"""
import datetime as dt
import json
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from django.utils import timezone

from regulations import eqaror, services
from regulations.ai.real import DATA, RealAnalyzer
from regulations.management.commands.seed_demo import REGIONS
from regulations.models import Document, Event, Region, RegulationRequest

CODE = {1: "AND", 2: "BUX", 3: "JIZ", 4: "QAS", 5: "NAV", 6: "NAM", 7: "SAM", 8: "SUR", 9: "SIR",
        10: "TSV", 11: "FAR", 12: "XOR", 13: "QQR", 14: "TSH"}
CATS = [("yer", "Yer munosabatlari"), ("soliq", "Soliq va to‘lovlar"), ("maktab", "Ta’lim"), ("ta’lim", "Ta’lim"),
        ("transport", "Transport"), ("savdo", "Savdo va xizmat ko‘rsatish"), ("tadbirkor", "Tadbirkorlik"),
        ("kommunal", "Kommunal xizmatlar"), ("obodon", "Obodonlashtirish"), ("ijtimoiy", "Ijtimoiy himoya"),
        ("qishloq", "Qishloq xo‘jaligi")]


def norm(s):
    return (s or "").replace("ʻ", "‘").replace("ʼ", "’")


class Command(BaseCommand):
    help = "Sintetik ma’lumotlarni o‘chirib, haqiqiy qarorlarni yuklaydi."

    def handle(self, *a, **o):
        rows = json.loads(DATA.read_text(encoding="utf-8"))
        RegulationRequest.objects.all().delete()
        for name, short, code, col, row, _ in REGIONS:
            Region.objects.update_or_create(code=code, defaults={"name": name, "short": short, "grid_col": col, "grid_row": row})
        me = get_user_model().objects.get(username="ekspert")
        rows.sort(key=lambda r: r["adopted"] or "")
        with override_settings(MEZON_AI={**settings.MEZON_AI, "DEMO_SPEED": 0}):
            an = RealAnalyzer({**settings.MEZON_AI, "DEMO_SPEED": 0})
            for r in rows:
                p = r["p"]
                reg = Region.objects.get(code=CODE[p["region"]])
                body = norm(r["body"] or "")
                kengash = p["type"] == "K"
                organ = re.sub(r"(?i)\s*(hokimi|qarori)$", "", body).strip()
                organ = re.sub(r"(?i)^xalq deputatlari\s+", "", organ)
                full = eqaror.organ_for(p["region"], p["district"], kengash)
                issuer = full or (body if kengash else organ + " hokimligi")
                district = re.sub(r"\s*(hokimligi|Kengashi)$", "", full.replace(reg.name, "").strip()) if p["district"] else ""
                tl = norm(r["title"]).lower()
                cat = next((c for k, c in CATS if k in tl), "Mahalliy qaror")
                at = timezone.make_aware(dt.datetime.strptime(r["adopted"][:10], "%Y-%m-%d").replace(hour=10))
                req = RegulationRequest.objects.create(
                    region=reg, district=district, issuer_name=issuer,
                    issuer_title="Kengash qarori" if kengash else "Hokimlik qarori",
                    title=norm(r["title"])[:300], doc_type="farmoyish" if p["type"] == "F" else "qaror", category=cat,
                    summary=f"Haqiqiy mahalliy qaror, lex.uz: {r['url']}", submitted_at=at, status="new",
                    draft_number=r["reg"])
                Event.objects.create(request=req, kind=Event.Kind.SUBMITTED, created_at=at, text=issuer)
                text = norm(r["text"])
                Document.objects.create(request=req, kind="draft", title=f"Qaror {r['reg']}", text=text,
                                        pages=max(1, len(text) // 1800 + 1), order=0)
                req.status = "in_review"
                req.save(update_fields=["status"])
                for _ in services.run_analysis(req, me, analyzer=an, render_html=False):
                    pass
        self.stdout.write(self.style.SUCCESS(f"Haqiqiy: {RegulationRequest.objects.count()} ta qaror yuklandi."))
