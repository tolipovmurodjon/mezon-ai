import datetime as dt
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .ai import get_analyzer
from .ai.rules import run_checks, verdict_for
from .models import Analysis, ChatMessage, Decision, Document, Event, Region, RegulationRequest
from .text import format_ai_text, mixed_script_words

FAST = override_settings(MEZON_AI={**settings.MEZON_AI, "BACKEND": "demo", "DEMO_SPEED": 0})

BAD_DRAFT = """XATIRCHI TUMANI HOKIMINING
QARORI

Avtoturargohlardan foydalanganlik uchun to‘lov joriy etish to‘g‘risida

“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonunning 25-moddasiga muvofiq qaror qilaman:

1. Tadbirkorlik subyektlari uchun avtoturargoh to‘lovi joriy etilsin.
2. Zarur hollarda mas’ul bo‘lim boshqa hujjatlarni ham talab qilishi mumkin.
3. Xizmatdan faqat shu hududda doimiy ro‘yxatda turgan fuqarolar foydalanadi.
4. Yuridik shaxslar uchun yer solig‘i bo‘yicha 0,7 dan 3,0 gacha koeffitsientlar belgilansin.
5. Ushbu qaror 2026-yil 1-sentabrdan boshlab yuzaga kelgan munosabatlarga nisbatan qo‘llaniladi.
"""

GOOD_DRAFT = """QO‘QON SHAHAR HOKIMINING
QARORI

Ko‘p qavatli uylar hududini obodonlashtirish to‘g‘risida

“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonunning 6-moddasiga muvofiq qaror qilaman:

1. Obodonlashtiriladigan uylar ro‘yxati 1-ilovaga muvofiq tasdiqlansin.
2. Ishlar uchun 2 400 mln so‘m mablag‘ ajratilsin tuman byudjetining qo‘shimcha manbalari hisobidan.
3. Ushbu qaror rasmiy e’lon qilingan kundan boshlab kuchga kiradi.
"""


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ekspert", password="test-pass-123", first_name="Dilnoza", last_name="Rahimova")
        cls.region = Region.objects.create(name="Navoiy viloyati", short="Navoiy", code="NAV", grid_col=2, grid_row=1)
        when = timezone.make_aware(dt.datetime(2026, 11, 20, 10, 0))
        cls.bad = RegulationRequest.objects.create(
            region=cls.region, district="Xatirchi tumani", issuer_name="Shuhrat Mirzayev", issuer_title="Xatirchi tumani hokimi",
            title="Avtoturargohlardan foydalanganlik uchun to‘lov joriy etish to‘g‘risida", category="Transport", submitted_at=when)
        Document.objects.create(request=cls.bad, kind="draft", title="Qaror loyihasi", text=BAD_DRAFT)
        cls.good = RegulationRequest.objects.create(
            region=cls.region, district="Karmana tumani", issuer_name="Akmal Yusupov", issuer_title="Karmana tumani hokimi",
            title="Ko‘p qavatli uylar hududini obodonlashtirish to‘g‘risida", category="Obodonlashtirish", submitted_at=when)
        Document.objects.create(request=cls.good, kind="draft", title="Qaror loyihasi", text=GOOD_DRAFT)

    def setUp(self):
        self.client.force_login(self.user)

    def stream(self, url, data=None):
        resp = self.client.post(url, data or {})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/event-stream"))
        body = b"".join(resp.streaming_content).decode("utf-8")
        return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


class RuleTests(Base):
    def test_bad_draft_is_flagged_on_every_planted_defect(self):
        _, results = run_checks(self.bad, self.bad.documents.all())
        status = {code: res.status for code, _, res in results}
        for code in ("dead_article", "retroactivity", "competence", "rights"):
            self.assertEqual(status[code], "fail", code)
        self.assertEqual(status["anti_corruption"], "warn")
        findings = [f for _, _, r in results for f in r.findings]
        self.assertEqual(verdict_for(findings)[0], "conflict")
        # every quote is verbatim document text
        for f in findings:
            if f["quote"]:
                self.assertIn(f["quote"], BAD_DRAFT)

    def test_clean_draft_passes(self):
        _, results = run_checks(self.good, self.good.documents.all())
        findings = [f for _, _, r in results for f in r.findings]
        self.assertEqual(findings, [])
        self.assertEqual(verdict_for(findings)[0], "compliant")

    def test_mixed_script(self):
        self.assertEqual(mixed_script_words("TАRKIBI va oddiy so‘z"), ["TАRKIBI"])  # Cyrillic А

    def test_ai_text_is_escaped(self):
        html = format_ai_text("Salom <script>x</script> **qalin**\n\n- band")
        self.assertNotIn("<script>", html)
        self.assertIn("<b>qalin</b>", html)
        self.assertIn("<li>band</li>", html)


@FAST
class FlowTests(Base):
    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_pages_render(self):
        for url in [reverse("dashboard"), reverse("requests"), reverse("requests") + "?holat=jarayonda&hudud=NAV&q=uy"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(reverse("requests")), "Xatirchi")

    def test_opening_moves_request_into_review(self):
        resp = self.client.get(reverse("review", args=[self.bad.pk]))
        self.assertContains(resp, "Tekshirish")
        self.assertContains(resp, 'data-autostart="1"')
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "in_review")
        self.assertTrue(Event.objects.filter(request=self.bad, kind="opened").exists())

    def test_analysis_streams_and_persists(self):
        events = self.stream(reverse("analyze", args=[self.bad.pk]))
        kinds = [e["type"] for e in events]
        self.assertIn("step", kinds)
        self.assertEqual(kinds.count("check"), 14)
        result = events[-1]
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["verdict"], "conflict")
        self.assertIn("Aniqlangan muammolar", result["html"])
        a = Analysis.objects.get(pk=result["analysis_id"])
        self.assertEqual(a.state, "done")
        self.assertGreaterEqual(a.findings.count(), 5)
        self.assertEqual(len(a.text_sha256), 64)
        # the saved analysis renders on reload without re-running
        resp = self.client.get(reverse("review", args=[self.bad.pk]))
        self.assertContains(resp, 'data-autostart="0"')
        self.assertContains(resp, "Qonunga zid")

    def test_chat_after_analysis(self):
        self.stream(reverse("analyze", args=[self.bad.pk]))
        events = self.stream(reverse("chat", args=[self.bad.pk]), {"message": "Bandlarni qanday tuzatish kerak?"})
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(ChatMessage.objects.filter(request=self.bad).count(), 2)

    def test_reject_needs_a_reason(self):
        resp = self.client.post(reverse("decide", args=[self.bad.pk]), {"outcome": "reject", "comment": " "})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Decision.objects.filter(request=self.bad).exists())

    def test_decision_is_final(self):
        self.stream(reverse("analyze", args=[self.bad.pk]))
        self.client.post(reverse("decide", args=[self.bad.pk]), {"outcome": "reject", "comment": "Kuchini yo‘qotgan modda"})
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "rejected")
        d = self.bad.decision
        self.assertEqual(d.ai_recommendation, "reject")
        self.assertTrue(d.agrees_with_ai)
        self.client.post(reverse("decide", args=[self.bad.pk]), {"outcome": "accept"})
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "rejected")
        self.assertEqual(Decision.objects.filter(request=self.bad).count(), 1)

    def test_document_download(self):
        d = self.good.documents.first()
        dl = self.client.get(reverse("document_download", args=[d.pk]))
        self.assertEqual(dl.status_code, 200)

    def test_backend_failure_is_reported_not_hidden(self):
        with override_settings(MEZON_AI={**settings.MEZON_AI, "BACKEND": "http", "URL": "http://127.0.0.1:9", "TIMEOUT": 2}):
            events = self.stream(reverse("analyze", args=[self.good.pk]))
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(Analysis.objects.filter(request=self.good).first().state, "failed")

    def test_get_analyzer_by_dotted_path(self):
        self.assertEqual(get_analyzer("regulations.ai.demo.DemoAnalyzer").name, "demo")
