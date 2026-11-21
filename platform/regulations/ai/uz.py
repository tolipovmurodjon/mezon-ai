"""Uzbek wording for Mezon rule flags (titles, explanations, law references)."""
import re

ACTS = {
    "Normativ-huquqiy hujjatlar to'g'risida Qonun (O'RQ-682)": "NHH Qonuni (O‘RQ-682)",
    "O'zbekiston Respublikasining Soliq kodeksi": "Soliq kodeksi",
    "Adliya vazirligining 3333-son buyrug'i: mahalliy loyihalar qoidalari": "Adliya vazirligining 3333-son buyrug‘i",
    "Mahalliy davlat hokimiyati to'g'risida Qonun (913-XII)": "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun",
    "Vazirlar Mahkamasining 390-son qarori (E-qaror nizomi)": "Vazirlar Mahkamasining 390-son qarori",
}
LSP = "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun"


def article(a):
    """art:18/part:3 -> 18-modda 3-qism ; annex:1/cl:6 -> 1-ilova 6-band"""
    out = []
    for p in (a or "").split("/"):
        k, _, v = p.partition(":")
        out.append({"art": f"{v}-modda", "part": f"{v}-qism", "annex": f"{v}-ilova", "cl": f"{v}-band"}.get(k, p))
    return " ".join(out)


def law_ref(c):
    return f"{ACTS.get(c.get('act_title', ''), c.get('act_title', ''))}, {article(c.get('article', ''))}".strip(", ")


def _clause(e):
    m = re.search(r"Clause (\d+)", e)
    return f"{m[1]}-band" if m else "Qarorda"


def translate(f):
    """(title, explanation) in Uzbek for one report flag dict."""
    code, t, e = f["check"], f["title"], f.get("explanation", "")
    c = _clause(e)
    nums = re.findall(r"\d{1,4}-\d{1,2}-\d{1,3}-[QF]/\d{2}|[IVX]+-\d+-\d+-\d+-\d+-K/\d{2}", t + " " + e)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", t + " " + e)
    tail = " Bu belgi ekspert tomonidan tasdiqlanishi kerak."
    if code == "R_business_3m":
        quota = " Bu yillik ish o\u2018rinlari kvotasi bo\u2018lishi mumkin: yuqori turuvchi hujjat (VMQ-965) hokimga uni har yili belgilashni yuklaydi, 3 oylik qoida unga tatbiq etilishi ekspert tomonidan aniqlanadi." if ("quota" in e.lower() or "VMQ" in e) else ""
        return ("Tadbirkorlik majburiyati qabul qilinganidan 3 oydan kam muddatda kuchga kiradi",
                f"{c}da majburiyatlar belgilangan, qaror esa rasmiy e’lon qilingan kuni kuchga kiradi. Tadbirkorlarga majburiyat "
                "yuklaydigan hujjatlar rasmiy e’lon qilinganidan kamida 3 oy o‘tgach kuchga kiradi (NHH Qonuni, 40-modda 2-qism). "
                "Yuqori turuvchi hujjat talab qilgan majburiyat (masalan, yillik kvota) istisno bo‘lishi mumkin." + quota + tail)
    if code == "R_tax_timing":
        when = f", ya’ni {dates[-1]} dan" if dates else ""
        return ("Soliq stavkasi o‘zgarishi keyingi oyning 1-kunidan oldin kuchga kiradi",
                f"{c}da mahalliy soliq stavkalari yoki koeffitsientlari belgilangan va qaror e’lon qilingan kuni kuchga kiradi. "
                f"Soliq kodeksi (4-modda 6-qism) stavka o‘zgarishini rasmiy e’londan keyingi oyning 1-kunidan kuchga kiritadi{when}. "
                "Ko‘p tumanlar “e’lon qilingan kundan” deb yozadi." + tail)
    if code == "R_discussion":
        return ("Normativ qaror uchun jamoatchilik muhokamasi qayd etilmagan",
                "E-qaror’da jamoatchilik muhokamasi bosqichi o‘tkazilmagan deb ko‘rinadi va regulation.gov.uz’da mos loyiha topilmadi. "
                "Normativ loyihalar jamoatchilik muhokamasiga qo‘yilishi shart (NHH Qonuni, 24-modda 1-qism). E-qaror bosqich belgisi dalil emas, "
                "faqat signal: ba’zan muhokama o‘tkazilgan bo‘lsa ham o‘tkazilmagan deb ko‘rinadi." + tail)
    if code == "R_expertise":
        return ("Normativ qaror uchun adliya huquqiy ekspertizasi qayd etilmagan",
                "E-qaror’da huquqiy ekspertiza bosqichi o‘tkazilmagan deb ko‘rinadi. Hududiy adliya organining ijobiy xulosasi mahalliy "
                "normativ qarorni qabul qilishning majburiy sharti (Adliya vazirligining 3333-son buyrug‘i, 1-ilova 6-band). "
                "Bosqich belgisi dalil emas, faqat signal." + tail)
    if code == "R_duplicate":
        n = nums[0] if nums else "oldingi qaror"
        return (f"{n} qarorini so‘zma-so‘z takrorlaydi, u hali kuchda",
                f"Amaliy bandlar {n} qaror bilan so‘zma-so‘z mos keladi, eski qaror esa bekor qilinmagan: bir masalani ikkita hujjat tartibga solmoqda. "
                "Yangi hujjat qabul qilgan organ unga zid eski hujjatlarni o‘zgartirishi yoki bekor qilishi shart (NHH Qonuni, 46-modda 1-qism)." + tail)
    if code == "R_double_repeal":
        n = nums[0] if nums else "qaror"
        return (f"{n} qarorini bekor qiladi, u allaqachon bekor qilingan",
                f"Qaror {n} ni bekor deb e’lon qiladi, lekin u avvalroq bekor qilingan. Boshqa qarorlarni o‘zgartirish va bekor qilish to‘g‘ri bo‘lishi "
                "kerak (Adliya vazirligining 3333-son buyrug‘i, 1-ilova 51-band); ikki marta bekor qilish hujjat holati tekshirilmaganini ko‘rsatadi." + tail)
    if code == "R_corruption_factor":
        m = re.search(r'corruption-inducing factor (\d+): ([^"]+)', t)
        q = re.search(r'uses "([^"]+)"', e)
        return (f"Korrupsiya omili ehtimoli: {m[2] if m else 'noaniq vakolat'}",
                f"{c}da “{q[1] if q else ''}” iborasi ishlatilgan — O‘RQ-860 korrupsiya omillari qatorida sanalgan ibora (13-modda). "
                "Omil me’yorning xususiyati, shaxsniki emas: shu ibora o‘rinli yoki yo‘qligini va uni qanday qayta yozishni ekspert hal qiladi." + tail
                if q else "Noaniq vakolat bildiruvchi ibora topildi (O‘RQ-860, 13-modda)." + tail)
    if code == "R_retroactive":
        d = f"; qaror {dates[0]} dan kuchga kiradi, qabul qilingan sana {dates[1]}" if len(dates) > 1 else ""
        return ("Majburiyat qaror qabul qilinishidan oldin kuchga kiradi",
                f"{c}da majburiyat belgilangan{d}. Hujjatlar majburiyat yaratganda yoki oshirganda orqaga qaytmaydi (NHH Qonuni, 41-modda 1-qism)." + tail)
    if code == "R_basis":
        m = re.search(r"article (\d+)", t)
        d = re.search(r"\d{4}-\d{2}-\d{2}", t)
        a = m[1] if m else ""
        extra = " (19.10.2024 dan kuchsiz)" if a == "25" else ""
        return (f"Qaror {LSP}ning {a}-moddasiga tayanadi — bu modda {d[0] if d else ''} holatida kuchda bo‘lmagan{extra}",
                f"Preambulada {a}-modda asos qilib keltirilgan, lekin {d[0] if d else 'qaror sanasi'} holatidagi tahrirda bu modda yo‘q (kuchini yo‘qotgan yoki bekor qilingan). "
                "Hujjat kuchda bo‘lmagan me’yorga tayana olmaydi (NHH Qonuni, 18-modda 3-qism); hozir amaldagi moddani keltirish kerak." + tail)
    generic = {
        "R_adopted_before_end": ("Jamoatchilik muhokamasi tugamasdan qabul qilingan", "Qaror muhokama muddati tugashidan oldin qabul qilingan."),
        "R_discussion_short": ("Jamoatchilik muhokamasi 15 kundan qisqa", "Muhokama muddati qonunda belgilangan 15 kundan kam."),
        "R_draft_window": ("Loyiha muhokama tugamasdan kuchga kiradi", "Loyiha jamoatchilik muhokamasi tugashidan oldin kuchga kirishi belgilangan."),
        "R_form": ("Normativ hujjat farmoyish shaklida chiqarilgan", "Mahalliy normativ hujjat faqat qaror shaklida chiqariladi (NHH Qonuni, 16-modda)."),
        "R_competence_land": ("Hokimning yer bo‘yicha vakolatidan tashqari", "Qarorda yer munosabatlari bo‘yicha vakolat doirasi tekshirilishi kerak."),
    }
    if code in generic:
        return generic[code][0], generic[code][1] + tail
    return t, e


def clean_quote(q):
    """pdftotext layout leaves indentation and glued words ("maqsadidaO'zbekiston", "25-moddalariga6"): normalise."""
    q = re.sub(r"\s+", " ", q or "").strip(" \u2026.")
    q = re.sub(r"(?<=[a-z\u2018\u2019\u02bb\u02bc'])(?=[A-Z])", " ", q)
    q = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", q)
    q = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", q)
    q = re.sub(r"(\d+) ?- ?(Q|F|K)\b", r"\1-\2", q)
    return q


def quote_html(q):
    import html as _h
    q = _h.escape(clean_quote(q))
    return re.sub(r"(\d+(?:\s*(?:va|,)\s*\d+)*-?\s*modda\w*)", r"<mark>\1</mark>", q)
