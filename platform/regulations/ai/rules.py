"""
Fourteen rule checks that run without an LLM.

Each check reads the request's documents and returns a CheckResult: a
status for the checks matrix, plus zero or more findings for the expert.
They are deliberately conservative heuristics: a flag means "an expert should
look here", never "this is a violation".
"""
import datetime as dt
import re
from dataclasses import dataclass, field

from ..text import mixed_script_words
from .laws import LAWS, RULE_SOURCES, A, find_law_mentions

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
DATE_RX = re.compile(r"(\d{4})-yil\s+(\d{1,2})-(" + "|".join(MONTHS) + r")(\w*)", re.IGNORECASE)
CLAUSE_RX = re.compile(r"^\s*(\d{1,2})\.\s")


@dataclass
class CheckResult:
    status: str = "pass"           # pass | warn | fail | skip
    detail: str = ""
    findings: list = field(default_factory=list)


@dataclass
class Unit:
    doc: object
    clause: str
    text: str

    @property
    def source(self):
        return f"{self.doc.title}, {self.clause}" if self.clause else self.doc.title


class Context:
    def __init__(self, req, documents):
        self.req = req
        self.docs = list(documents)
        self.draft = next((d for d in self.docs if d.kind == "draft"), self.docs[0] if self.docs else None)
        self.text_all = "\n".join(d.text for d in self.docs)
        self.text_draft = self.draft.text if self.draft else ""
        self.submitted = req.submitted_at.date()
        self.units = list(self._units())

    def _units(self):
        for doc in self.docs:
            clause = "preambula" if doc.kind == "draft" else ""
            for line in doc.text.splitlines():
                if not line.strip():
                    continue
                m = CLAUSE_RX.match(line)
                if m and doc.kind == "draft":
                    clause = f"{m.group(1)}-band"
                for sentence in re.split(r"(?<=[.;:])\s+(?=[A-ZА-ЯЎҚҒҲO‘“«\d])", line.strip()):
                    if sentence.strip():
                        yield Unit(doc, clause, sentence.strip())

    def draft_units(self):
        return [u for u in self.units if self.draft and u.doc.pk == self.draft.pk]

    def find(self, pattern, units=None, flags=re.IGNORECASE):
        rx = re.compile(pattern, flags)
        for u in units if units is not None else self.units:
            if rx.search(u.text):
                return u
        return None

    def find_all(self, pattern, units=None, flags=re.IGNORECASE):
        rx = re.compile(pattern, flags)
        return [u for u in (units if units is not None else self.units) if rx.search(u.text)]

    def dates_in(self, text):
        out = []
        for m in DATE_RX.finditer(text):
            try:
                out.append((dt.date(int(m.group(1)), MONTHS.index(m.group(3).lower()) + 1, int(m.group(2))), m.group(0)))
            except ValueError:
                continue
        return out

    @property
    def affects_business(self):
        return bool(re.search(r"tadbirkor|yuridik shaxs|savdo shoxobcha|xo{A}jalik yurituvchi|bozor".replace("{A}", A),
                              self.text_draft, re.IGNORECASE))


def finding(code, severity, title, explanation, unit=None, suggestion="", law_ref=None, law_text="", category=None):
    return {
        "type": "finding",
        "code": code,
        "category": category or CHECK_LABELS.get(code, code),
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "quote": unit.text if unit else "",
        "quote_source": unit.source if unit else "",
        "law_ref": law_ref if law_ref is not None else RULE_SOURCES.get(code, ""),
        "law_text": law_text,
        "suggestion": suggestion,
    }


def fmt_date(d):
    return d.strftime("%d.%m.%Y")


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def check_legal_basis(ctx):
    mentions = find_law_mentions(ctx.text_draft)
    articles = re.findall(r"\d+-moddas", ctx.text_draft)
    if mentions or articles:
        names = sorted({LAWS[k]["title"] for k, _, _ in mentions})
        return CheckResult("pass", f"{len(names) or len(articles)} ta havola" + (f": {names[0]}" if names else ""))
    return CheckResult("fail", "Havola topilmadi", [finding(
        "legal_basis", "serious", "Qaror loyihasida huquqiy asos ko‘rsatilmagan",
        "Preambulada qaysi qonun yoki moddaga muvofiq qabul qilinayotgani yozilmagan. Asossiz qaror mahalliy "
        "hokimiyat vakolati doirasida ekanini tekshirib bo‘lmaydi.",
        ctx.draft_units()[0] if ctx.draft_units() else None,
        "Preambulaga qarorning huquqiy asosini, qonun nomi va moddasi bilan, qo‘shing.",
        law_ref=RULE_SOURCES["form"],
    )])


def check_dead_article(ctx):
    found = []
    for unit in ctx.draft_units():
        for key, start, end in find_law_mentions(unit.text):
            lost = LAWS[key].get("lost") or {}
            window = unit.text[max(0, start - 60): end + 120]
            for art in re.findall(r"(\d+)-moddas", window):
                art = int(art)
                if art in lost:
                    date_s, note = lost[art]
                    lost_on = dt.date.fromisoformat(date_s)
                    if lost_on <= ctx.submitted:
                        found.append(finding(
                            "dead_article", "critical",
                            f"Qaror kuchini yo‘qotgan moddaga tayanadi: {LAWS[key]['title']}, {art}-modda",
                            f"Bu modda {fmt_date(lost_on)} dan beri amalda emas ({note}). Loyiha esa "
                            f"{fmt_date(ctx.submitted)} da yuborilgan, ya’ni uning huquqiy asosi yo‘q.",
                            unit,
                            "Huquqiy asosni amaldagi tahrirdagi moddaga almashtiring va vakolat saqlanib qolganini tekshiring.",
                            law_ref=f"{LAWS[key]['title']}, {art}-modda · {note}",
                            law_text="Qaror sanasidagi tahrirda ushbu modda mavjud emas.",
                        ))
    if found:
        return CheckResult("fail", f"{len(found)} ta kuchsiz havola", found)
    return CheckResult("pass", "Barcha havolalar amalda")


def check_competence(ctx):
    unit = ctx.find(r"(yer solig{A}i|soliq stavka|koeffitsient)\w*[^.]*?(belgilansin|tasdiqlansin|qo{A}llanilsin)".replace("{A}", A),
                    ctx.draft_units())
    if unit:
        return CheckResult("fail", "Kengash vakolati", [finding(
            "competence", "critical", "Hokim Kengash vakolatidagi masalani hal qilmoqda",
            "Mahalliy soliq stavkalari va yer solig‘i koeffitsientlarini xalq deputatlari Kengashi belgilaydi. "
            "Hokim qarori bilan ularni o‘rnatish vakolat doirasidan chiqadi.",
            unit,
            "Masalani xalq deputatlari Kengashi sessiyasiga kiriting yoki ushbu bandni loyihadan chiqaring.",
        )])
    return CheckResult("pass", "Hokim vakolati doirasida")


def check_form(ctx):
    if ctx.req.doc_type != "farmoyish":
        return CheckResult("pass", "Qaror shakli")
    unit = ctx.find(r"barcha (jismoniy|yuridik)|majburiy|umummajburiy|jismoniy va yuridik shaxslar", ctx.draft_units())
    if unit:
        return CheckResult("fail", "Farmoyishda umummajburiy norma", [finding(
            "form", "serious", "Umummajburiy normalar farmoyish shaklida berilgan",
            "Farmoyish tashkiliy va tezkor masalalar uchun. Fuqarolar va tashkilotlar uchun majburiy qoidalar "
            "qaror shaklida qabul qilinishi kerak.",
            unit, "Hujjatni qaror shaklida qayta rasmiylashtiring.",
        )])
    return CheckResult("pass", "Farmoyish · tashkiliy masala")


def check_retroactivity(ctx):
    for unit in ctx.draft_units():
        if not re.search(r"dan boshlab|kuchga kir|qo{A}llanil|tatbiq".replace("{A}", A), unit.text, re.IGNORECASE):
            continue
        for d, raw in ctx.dates_in(unit.text):
            if d < ctx.submitted and re.search(r"munosabat|qo{A}llanil|kuchga kir|tatbiq|hisoblan".replace("{A}", A), unit.text, re.IGNORECASE):
                return CheckResult("fail", f"{fmt_date(d)} dan amal qiladi", [finding(
                    "retroactivity", "critical", "Qaror o‘tgan davrga nisbatan qo‘llanmoqda",
                    f"Qaror {fmt_date(ctx.submitted)} da yuborilgan, lekin {fmt_date(d)} dan boshlab qo‘llanishi "
                    "belgilangan. Majburiyat yuklovchi yoki javobgarlikni og‘irlashtiruvchi norma orqaga qaytish "
                    "kuchiga ega bo‘lmaydi.",
                    unit,
                    "Kuchga kirish sanasini rasmiy e’lon qilingan kundan keyingi sana qilib belgilang.",
                    law_text="Fuqarolar va yuridik shaxslarga yangi majburiyat yuklovchi normalar orqaga qaytish kuchiga ega emas.",
                )])
    return CheckResult("pass", "Kelgusi sanadan kuchga kiradi")


def _effective_date(ctx):
    unit = ctx.find(r"kuchga kir", ctx.draft_units())
    if not unit:
        return None, None
    if re.search(r"e{A}lon qilingan kun".replace("{A}", A), unit.text, re.IGNORECASE):
        if re.search(r"\b(uch|3) oy", unit.text, re.IGNORECASE):
            return ctx.submitted + dt.timedelta(days=92), unit
        return ctx.submitted, unit
    dates = ctx.dates_in(unit.text)
    return (dates[0][0] if dates else None), unit


def check_business_3m(ctx):
    burden = ctx.find(r"(yig{A}im|to{A}lov|majburiy|talab etilsin|ruxsatnoma)".replace("{A}", A), ctx.draft_units())
    if not (ctx.affects_business and burden):
        return CheckResult("skip", "Tadbirkorlarga yangi majburiyat yo‘q")
    eff, unit = _effective_date(ctx)
    if eff is None:
        return CheckResult("warn", "Kuchga kirish sanasi yo‘q", [finding(
            "business_3m", "warning", "Kuchga kirish sanasi ko‘rsatilmagan",
            "Loyiha tadbirkorlarga yangi majburiyat yuklaydi, lekin qachondan kuchga kirishi yozilmagan.",
            burden, "Kuchga kirish sanasini rasmiy e’lon qilingandan kamida 3 oy keyin belgilang.",
        )])
    if (eff - ctx.submitted).days < 90:
        return CheckResult("fail", "3 oydan kam", [finding(
            "business_3m", "serious", "Tadbirkorlarga yangi majburiyat 3 oydan oldin kuchga kiradi",
            f"Loyiha tadbirkorlik subyektlariga yangi majburiyat yuklaydi va {fmt_date(eff)} dan kuchga kiradi. "
            "Bunday hujjatlar rasmiy e’lon qilingandan kamida 3 oy o‘tib kuchga kirishi kerak.",
            unit or burden,
            "Kuchga kirish sanasini rasmiy e’lon qilingandan kamida 3 oy keyinga suring.",
        )])
    return CheckResult("pass", f"{fmt_date(eff)} · 3 oy saqlangan")


def check_public_discussion(ctx):
    required = ctx.affects_business or re.search(r"yer|soliq|yig{A}im|to{A}lov".replace("{A}", A), ctx.req.category + " " + ctx.text_draft, re.IGNORECASE)
    unit = ctx.find(r"muhokama")
    if not required:
        return CheckResult("skip", "Talab etilmaydi")
    if not unit:
        return CheckResult("fail", "Muhokama o‘tkazilmagan", [finding(
            "public_discussion", "serious", "Loyiha jamoatchilik muhokamasidan o‘tkazilmagan",
            "Loyiha tadbirkorlar va aholi manfaatiga taalluqli, lekin hujjatlarda uning jamoatchilik "
            "muhokamasiga qo‘yilgani haqida ma’lumot yo‘q.",
            None,
            "Loyihani kamida 15 kun muhokamaga qo‘ying va takliflar yig‘ma jadvalini ilova qiling.",
        )])
    days = [int(x) for x in re.findall(r"(\d{1,3})\s*kun", unit.text)]
    if days and max(days) < 15:
        return CheckResult("warn", f"{max(days)} kun", [finding(
            "public_discussion", "warning", f"Muhokama muddati {max(days)} kun, 15 kundan kam",
            "Loyiha muhokamaga qo‘yilgan, lekin muhokama muddati talab qilinganidan qisqa.",
            unit, "Muhokamani uzaytiring yoki qisqa muddat sababini tushuntirish xatida asoslang.",
        )])
    return CheckResult("pass", f"{max(days)} kun" if days else "O‘tkazilgan")


def check_tax_timing(ctx):
    unit = ctx.find(r"soliq\w*\s[^.]*?(stavka|miqdor)", ctx.draft_units())
    if not unit:
        return CheckResult("skip", "Soliq normasi yo‘q")
    dates = ctx.dates_in(unit.text)
    if dates and not (dates[0][0].month == 1 and dates[0][0].day == 1):
        return CheckResult("warn", "Yil o‘rtasida", [finding(
            "tax_timing", "warning", "Soliq miqdori yil o‘rtasida o‘zgartirilmoqda",
            "Soliq stavkalari va miqdorlari odatda keyingi soliq davri boshidan o‘zgartiriladi.",
            unit, "O‘zgarishni keyingi yilning 1-yanvaridan boshlab qo‘llang.",
        )])
    return CheckResult("pass", "Soliq davri boshidan")


def _norm_title(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def check_duplicate(ctx):
    from ..models import RegulationRequest  # local import: rules stay importable without Django apps loaded
    title = _norm_title(ctx.req.title)
    since = ctx.req.submitted_at - dt.timedelta(days=365)
    for other in (RegulationRequest.objects
                  .filter(region=ctx.req.region, status="accepted", submitted_at__gte=since, submitted_at__lt=ctx.req.submitted_at)
                  .exclude(pk=ctx.req.pk).only("number", "title", "district")):
        if _norm_title(other.title) == title and other.district == ctx.req.district:
            return CheckResult("warn", f"{other.number} bilan bir xil", [finding(
                "duplicate", "warning", f"Shu mazmundagi qaror avval qabul qilingan ({other.number})",
                "Bir xil nomdagi qaror shu hududda bir yil ichida qabul qilingan. Ikki hujjat bir-birini takrorlashi "
                "yoki bir-biriga zid bo‘lishi mumkin.",
                None, "Avvalgi qarorga o‘zgartirish kiritish yoki uni o‘z kuchini yo‘qotgan deb topish kerakligini aniqlang.",
                law_ref=RULE_SOURCES["form"],
            )])
    return CheckResult("pass", "Takror topilmadi")


def check_citations(ctx):
    names = re.findall(r"[“\"«]([^”\"»]{6,140}?to" + A + "g" + A + r"risida)[”\"»]", ctx.text_draft)
    unknown = []
    for name in names:
        low = name.lower()
        if not any(re.search(law["match"], low, re.IGNORECASE) for law in LAWS.values()):
            unknown.append(name)
    if unknown:
        unit = ctx.find(re.escape(unknown[0]), ctx.draft_units())
        return CheckResult("warn", f"{len(unknown)} ta tekshirilmadi", [finding(
            "citations", "info", f"Havolani avtomatik tekshirib bo‘lmadi: “{unknown[0]}”",
            "Bu hujjat Mezon qonunlar reyestrida yo‘q, shuning uchun uning qaror sanasidagi tahriri avtomatik "
            "tekshirilmadi. Havolani qo‘lda tekshiring.",
            unit, "Hujjat nomi, raqami va qabul qilingan sanasini to‘liq ko‘rsating.",
            law_ref="Qonunchilik ma’lumotlari milliy bazasi (lex.uz)", category="Iqtiboslar aniqligi",
        )])
    return CheckResult("pass", f"{len(names)} ta iqtibos mos" if names else "Iqtibos yo‘q")


VAGUE = [
    r"zarur (deb topilgan )?hollarda",
    r"boshqa hujjatlar(ni)? (ham )?talab",
    r"kelishilgan holda",
    r"o{A}z ixtiyoriga ko{A}ra",
    r"alohida hollarda",
    r"belgilangan tartibda(?! va muddatlarda)",
]


def check_anti_corruption(ctx):
    hits = []
    for pat in VAGUE:
        hits += ctx.find_all(pat.replace("{A}", A), ctx.draft_units())
    hits = list({id(u): u for u in hits}.values())
    if not hits:
        return CheckResult("pass", "Omillar topilmadi")
    return CheckResult("warn", f"{len(hits)} ta omil", [finding(
        "anti_corruption", "warning",
        "Mansabdor shaxsga keng ixtiyoriy vakolat beruvchi norma" + (f" ({len(hits)} ta)" if len(hits) > 1 else ""),
        "Aniq mezonsiz “zarur hollarda”, “boshqa hujjatlar talab qilinishi mumkin” kabi iboralar korrupsiyaviy "
        "omil hisoblanadi: qaror qabul qilish mansabdor shaxsning ixtiyoriga qoladi.",
        hits[0], "Har bir holat uchun aniq mezon, hujjatlarning yopiq ro‘yxati va ko‘rib chiqish muddatini yozing.",
    )])


def check_linguistic(ctx):
    words = mixed_script_words(ctx.text_all)
    if not words:
        return CheckResult("pass", "Aralash yozuv yo‘q")
    unit = ctx.find(re.escape(words[0]))
    return CheckResult("warn", f"{len(words)} ta so‘z", [finding(
        "linguistic", "info", f"Lotin va kirill harflari aralashgan so‘z: “{words[0]}”" + (f" va yana {len(words) - 1} ta" if len(words) > 1 else ""),
        "So‘z ichida lotin va kirill harflari aralashgan. Bunday matn qidiruvda topilmaydi va rasmiy nashrda xato hisoblanadi.",
        unit, "Matnni bitta yozuvda (lotin) qayta tering.",
    )])


def check_rights(ctx):
    unit = ctx.find(r"faqat\s[^.]{0,60}?(doimiy ro{A}yxat|propiska|doimiy yashovchi)|(erkak|ayol)lar(ga|ning)? [^.]{0,40}taqiql".replace("{A}", A),
                    ctx.draft_units())
    if unit:
        return CheckResult("fail", "Kamsitish belgisi", [finding(
            "rights", "critical", "Fuqarolarni yashash joyi bo‘yicha cheklash: teng huquqlilikka zid",
            "Xizmat yoki huquqdan foydalanish doimiy ro‘yxatdan o‘tganlik bilan cheklangan. Bu fuqarolarning teng "
            "huquqliligi prinsipiga va etik me’yorlarga zid; qonunda nazarda tutilmagan cheklovni mahalliy hujjat kirita olmaydi.",
            unit, "Cheklovni olib tashlang yoki uni qonun bilan belgilangan asosga bog‘lang.",
            category="Inson huquqlari va etika",
        )])
    return CheckResult("pass", "Cheklov topilmadi")


def check_budget(ctx):
    units = ctx.find_all(r"mablag{A}(lar)? ajratilsin|moliyalashtirilsin".replace("{A}", A), ctx.draft_units())
    bad = [u for u in units if not re.search(r"hisobidan|manba", u.text, re.IGNORECASE)]
    if not units:
        return CheckResult("skip", "Moliyalashtirish yo‘q")
    if bad:
        return CheckResult("warn", "Manba ko‘rsatilmagan", [finding(
            "budget", "warning", "Mablag‘ ajratiladi, lekin moliyalashtirish manbai ko‘rsatilmagan",
            "Qaror mablag‘ ajratishni nazarda tutadi, ammo qaysi byudjet yoki jamg‘arma hisobidan ekani yozilmagan.",
            bad[0], "Manbani (masalan, “tuman byudjetining qo‘shimcha manbalari hisobidan”) va summani ko‘rsating.",
        )])
    return CheckResult("pass", "Manba ko‘rsatilgan")


CHECKS = [
    ("legal_basis", "Huquqiy asos", check_legal_basis),
    ("dead_article", "Kuchini yo‘qotgan norma", check_dead_article),
    ("competence", "Vakolat doirasi", check_competence),
    ("form", "Hujjat shakli", check_form),
    ("retroactivity", "Orqaga qaytish kuchi", check_retroactivity),
    ("business_3m", "Tadbirkorlar uchun 3 oy", check_business_3m),
    ("public_discussion", "Jamoatchilik muhokamasi", check_public_discussion),
    ("tax_timing", "Soliq muddatlari", check_tax_timing),
    ("duplicate", "Takroriy qaror", check_duplicate),
    ("citations", "Iqtiboslar aniqligi", check_citations),
    ("anti_corruption", "Korrupsiyaviy omillar", check_anti_corruption),
    ("linguistic", "Til va imlo", check_linguistic),
    ("rights", "Inson huquqlari va etika", check_rights),
    ("budget", "Moliyaviy manba", check_budget),
]
CHECK_LABELS = {code: label for code, label, _ in CHECKS}

SEVERITY_WEIGHT = {"critical": 30, "serious": 15, "warning": 7, "info": 2}


def run_checks(req, documents):
    """Run every check. Returns (ctx, [(code, label, CheckResult)])."""
    ctx = Context(req, documents)
    results = []
    for code, label, fn in CHECKS:
        try:
            res = fn(ctx)
        except Exception as exc:  # one broken heuristic must not sink the whole review
            res = CheckResult("skip", f"Tekshirib bo‘lmadi: {exc.__class__.__name__}")
        results.append((code, label, res))
    return ctx, results


def verdict_for(findings):
    sev = [f["severity"] for f in findings]
    score = max(5, 100 - sum(SEVERITY_WEIGHT.get(s, 0) for s in sev))
    if "critical" in sev:
        return "conflict", "reject", min(score, 49)
    if "serious" in sev or "warning" in sev:
        return "minor", "revise", min(max(score, 50), 89)
    return "compliant", "accept", max(score, 90)
