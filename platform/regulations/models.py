"""
Data model.

A hokimlik sends a *request* (so‘rov): one draft regulation plus its
supporting documents. Mezon AI writes an *analysis* with *findings*.
A human expert makes the *decision*. Every step lands in the *event* log.
"""
import hashlib

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Region(models.Model):
    name = models.CharField("Nomi", max_length=80, unique=True)          # Farg‘ona viloyati
    short = models.CharField("Qisqa nomi", max_length=40)                # Farg‘ona
    code = models.CharField("Kod", max_length=3, unique=True)            # FAR
    # position on the 7×3 tile cartogram (column, row), 1-based
    grid_col = models.PositiveSmallIntegerField(default=1)
    grid_row = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["name"]
        verbose_name = "Hudud"
        verbose_name_plural = "Hududlar"

    def __str__(self):
        return self.name


class RegulationRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        IN_REVIEW = "in_review", "Ko‘rilmoqda"
        ACCEPTED = "accepted", "Qabul qilingan"
        REJECTED = "rejected", "Rad etilgan"

    class DocType(models.TextChoices):
        QAROR = "qaror", "Qaror"
        FARMOYISH = "farmoyish", "Farmoyish"

    OPEN_STATUSES = (Status.NEW, Status.IN_REVIEW)

    number = models.CharField("So‘rov raqami", max_length=32, unique=True, editable=False)
    draft_number = models.CharField("Loyiha raqami", max_length=40, blank=True)
    region = models.ForeignKey(Region, verbose_name="Hudud", on_delete=models.PROTECT, related_name="requests")
    district = models.CharField("Tuman / shahar", max_length=80, blank=True)
    issuer_name = models.CharField("Hokim (F.I.Sh.)", max_length=120)
    issuer_title = models.CharField("Lavozimi", max_length=160)
    title = models.CharField("Qaror loyihasi nomi", max_length=300)
    doc_type = models.CharField("Hujjat shakli", max_length=12, choices=DocType.choices, default=DocType.QAROR)
    category = models.CharField("Soha", max_length=80)
    summary = models.TextField("Qisqacha mazmuni", blank=True)
    submitted_at = models.DateTimeField("Yuborilgan vaqt", default=timezone.now, db_index=True)
    status = models.CharField("Holat", max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "So‘rov"
        verbose_name_plural = "So‘rovlar"

    def __str__(self):
        return f"{self.number} · {self.title}"

    def save(self, *args, **kwargs):
        if not self.number:
            year = (self.submitted_at or timezone.now()).year
            last = RegulationRequest.objects.filter(number__startswith=f"SR-{year}-").order_by("-number").first()
            seq = int(last.number.rsplit("-", 1)[1]) + 1 if last else 1
            self.number = f"SR-{year}-{seq:05d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("review", args=[self.pk])

    # -- convenience ---------------------------------------------------------
    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def source_label(self):
        return f"{self.region.short}, {self.district}" if self.district else self.region.name

    @property
    def latest_analysis(self):
        # uses the prefetch cache when a list view prefetched analyses
        cached = getattr(self, "_prefetched_objects_cache", {}).get("analyses")
        if cached is not None:
            done = [a for a in cached if a.state == Analysis.State.DONE]
            return max(done, key=lambda a: a.started_at) if done else None
        return self.analyses.filter(state=Analysis.State.DONE).order_by("-started_at").first()

    @property
    def decision(self):
        try:
            return self._decision
        except Decision.DoesNotExist:
            return None

    def full_text(self):
        """Every document's text, in order; what the model reads and what we fingerprint."""
        parts = []
        for doc in self.documents.all():
            parts.append(f"### {doc.title}\n{doc.text}")
        return "\n\n".join(parts)

    def text_fingerprint(self):
        return hashlib.sha256(self.full_text().encode("utf-8")).hexdigest()


class Document(models.Model):
    class Kind(models.TextChoices):
        DRAFT = "draft", "Qaror loyihasi"
        NOTE = "note", "Tushuntirish xati"
        FINANCE = "finance", "Moliyaviy-iqtisodiy asoslash"
        DISCUSSION = "discussion", "Jamoatchilik muhokamasi natijalari"
        ANNEX = "annex", "Ilova"
        LETTER = "letter", "Kuzatuv xati"

    request = models.ForeignKey(RegulationRequest, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField("Nomi", max_length=200)
    kind = models.CharField("Turi", max_length=12, choices=Kind.choices, default=Kind.DRAFT)
    file = models.FileField("Fayl", upload_to="documents/%Y/%m/", blank=True)
    pages = models.PositiveSmallIntegerField("Betlar", default=1)
    text = models.TextField("Matn", blank=True, help_text="Bo‘sh qoldirilsa, fayldan avtomatik ajratib olinadi (.txt, .docx, .pdf).")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Hujjat"
        verbose_name_plural = "Hujjatlar"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.file and not self.text:
            from .text import extract_text
            self.text = extract_text(self.file)
        super().save(*args, **kwargs)

    @property
    def word_count(self):
        return len(self.text.split())

    @property
    def extension(self):
        if self.file:
            return self.file.name.rsplit(".", 1)[-1].lower()
        return "txt"

    @property
    def icon(self):
        return {"finance": "file-spreadsheet", "discussion": "users", "letter": "file-text", "annex": "paperclip"}.get(self.kind, "file-text")


class Analysis(models.Model):
    class State(models.TextChoices):
        RUNNING = "running", "Bajarilmoqda"
        DONE = "done", "Tayyor"
        FAILED = "failed", "Xato"

    class Verdict(models.TextChoices):
        COMPLIANT = "compliant", "Qonunga mos"
        MINOR = "minor", "Kamchiliklar bor"
        CONFLICT = "conflict", "Ehtimoliy buzilish"

    class Recommendation(models.TextChoices):
        ACCEPT = "accept", "Qabul qilish mumkin"
        REVISE = "revise", "Tuzatishlar bilan qabul qilish"
        REJECT = "reject", "Rad etish tavsiya etiladi"

    request = models.ForeignKey(RegulationRequest, on_delete=models.CASCADE, related_name="analyses")
    state = models.CharField(max_length=10, choices=State.choices, default=State.RUNNING)
    verdict = models.CharField("Xulosa", max_length=12, choices=Verdict.choices, blank=True)
    recommendation = models.CharField("Tavsiya", max_length=10, choices=Recommendation.choices, blank=True)
    score = models.PositiveSmallIntegerField("Muvofiqlik, %", null=True, blank=True)
    summary = models.TextField("Xulosa matni", blank=True)
    steps = models.JSONField("Agent qadamlari", default=list, blank=True)
    checks = models.JSONField("Tekshiruvlar", default=list, blank=True)
    sources = models.JSONField("Manbalar", default=list, blank=True)
    backend = models.CharField(max_length=60, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    rules_version = models.CharField(max_length=20, blank=True)
    text_sha256 = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "AI tahlili"
        verbose_name_plural = "AI tahlillari"

    def __str__(self):
        return f"{self.request.number} · {self.get_verdict_display() or self.get_state_display()}"

    @property
    def duration_s(self):
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def tone(self):
        return {"compliant": "good", "minor": "warning", "conflict": "critical"}.get(self.verdict, "")

    @property
    def counts(self):
        out = {"critical": 0, "serious": 0, "warning": 0, "info": 0}
        for f in self.findings.all():
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    @property
    def checks_passed(self):
        return sum(1 for c in self.checks if c.get("status") == "pass")


class Finding(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Jiddiy"
        SERIOUS = "serious", "Muhim"
        WARNING = "warning", "O‘rtacha"
        INFO = "info", "Kichik"

    SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2, "info": 3}

    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE, related_name="findings")
    code = models.CharField(max_length=40)                      # rule id, e.g. "retroactivity"
    category = models.CharField("Toifa", max_length=80)          # Orqaga qaytish kuchi
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=240)
    explanation = models.TextField(blank=True)
    quote = models.TextField("Hujjatdagi matn", blank=True)
    quote_source = models.CharField(max_length=200, blank=True)
    law_ref = models.CharField("Qonun havolasi", max_length=300, blank=True)
    law_text = models.TextField("Qonun talabi", blank=True)
    suggestion = models.TextField("Tavsiya", blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Aniqlangan muammo"
        verbose_name_plural = "Aniqlangan muammolar"

    def __str__(self):
        return self.title

    @property
    def tone(self):
        return {"critical": "critical", "serious": "serious", "warning": "warning"}.get(self.severity, "")


class Decision(models.Model):
    class Outcome(models.TextChoices):
        ACCEPT = "accept", "Qabul qilindi"
        REJECT = "reject", "Rad etildi"

    request = models.OneToOneField(RegulationRequest, on_delete=models.CASCADE, related_name="_decision")
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    comment = models.TextField("Izoh", blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(default=timezone.now, db_index=True)
    analysis = models.ForeignKey(Analysis, null=True, blank=True, on_delete=models.SET_NULL,
                                 help_text="Qaror qabul qilingan paytdagi AI tahlili")
    ai_recommendation = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["-decided_at"]
        verbose_name = "Qaror"
        verbose_name_plural = "Qarorlar"

    def __str__(self):
        return f"{self.request.number} · {self.get_outcome_display()}"

    @property
    def agrees_with_ai(self):
        if not self.ai_recommendation:
            return None
        if self.outcome == "reject":
            return self.ai_recommendation == "reject"
        return self.ai_recommendation in ("accept", "revise")


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Foydalanuvchi"
        ASSISTANT = "assistant", "Mezon AI"

    request = models.ForeignKey(RegulationRequest, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Suhbat xabari"
        verbose_name_plural = "Suhbat xabarlari"


class Event(models.Model):
    class Kind(models.TextChoices):
        SUBMITTED = "submitted", "Yuborildi"
        OPENED = "opened", "Ochildi"
        ANALYZED = "analyzed", "AI tahlili"
        ANALYSIS_FAILED = "analysis_failed", "Tahlil xatosi"
        ACCEPTED = "accepted", "Qabul qilindi"
        REJECTED = "rejected", "Rad etildi"

    request = models.ForeignKey(RegulationRequest, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    text = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Hodisa"
        verbose_name_plural = "Faoliyat jurnali"

    @property
    def is_ai(self):
        return self.kind in (self.Kind.ANALYZED, self.Kind.ANALYSIS_FAILED)

    @property
    def is_key(self):
        return self.kind in (self.Kind.ACCEPTED, self.Kind.REJECTED)

    @property
    def is_critical(self):
        return self.kind in (self.Kind.REJECTED, self.Kind.ANALYSIS_FAILED)
