"""Uzbek wording, a plain "what it means for you" line, the official channels, and a ready appeal draft for each flag."""

import re

ADLIYA = {"name": "Tuman (shahar) adliya bo'limi", "why": "mahalliy qarorlar qonuniyligini nazorat qiladi",
          "url": "https://murojaat.gov.uz"}
OMBUDSMAN = {"name": "Biznes ombudsman", "why": "tadbirkorlar huquqlarini himoya qiladi", "url": "https://biznesombudsman.uz"}
PETITION = {"name": "Jamoaviy murojaat (petition.gov.uz)", "why": "tuman Kengashi 1 000 ovozda ko'rib chiqadi",
            "url": "https://petition.gov.uz"}
COURT = {"name": "Ma'muriy sud (my.sud.uz)", "why": "qarorni haqiqiy emas deb topishi mumkin", "url": "https://my.sud.uz"}

GATES = {"0_draft": "Loyiha bosqichi (qabul qilinishidan oldin)", "1_slipped": "Tartib buzilgan holda qabul qilingan",
         "2_adopted": "Qabul qilingan qaror"}

# check -> (Uzbek title, plain meaning, channels)
TEXTS = {
    "R_business_3m": ("Tadbirkorlarga yangi majburiyat 3 oydan oldin kuchga kiradi",
                      ("Agar qaror kuchda qolsa, biznesingiz yangi talab yoki to'lovga qonun bergan 3 oylik "
                      "tayyorgarlik muddatisiz duch keladi."), [OMBUDSMAN, ADLIYA]),
    "R_corruption_factor": ("Korrupsiyani keltirib chiqaruvchi omil bo'lishi mumkin (O'RQ-860)",
                            ("Qonun bunday ifodani suiiste'mol uchun imkon yaratishi mumkin bo'lgan norma deb biladi. Bu "
                             "shaxsga ayblov emas: ekspert normani aniqroq ifodalash kerakmi, hal qiladi."), [ADLIYA]),
    "R_tax_timing": ("Soliq stavkasi o'zgarishi keyingi oyning 1-kunidan oldin kuchga kiradi",
                     ("Soliq kodeksiga ko'ra stavka o'zgarishi e'lon qilingan oydan keyingi oyning birinchi kunidan "
                      "kuchga kiradi; bu qarorda muddat ertaroq."), [OMBUDSMAN, ADLIYA]),
    "R_retroactive": ("Majburiyat qaror qabul qilinishidan oldingi sanadan kuchga kiradi",
                      "Qonun yangi majburiyatni orqaga qaytib qo'llashni taqiqlaydi.", [ADLIYA, COURT]),
    "R_discussion": ("Normativ qaror uchun jamoatchilik muhokamasi qayd etilmagan",
                     "Qaror sizni ham qamrab olsa, siz fikr bildirish imkoniyatidan mahrum bo'lgan bo'lishingiz mumkin.",
                     [ADLIYA, PETITION]),
    "R_discussion_short": ("Jamoatchilik muhokamasi 15 kundan qisqa",
                           "Qonun loyiha bo'yicha fikr bildirish uchun kamida 15 kun beradi; bu loyihada muddat qisqaroq.",
                           [ADLIYA, PETITION]),
    "R_draft_window": ("Loyiha muhokamasi tugashidan oldin kuchga kirishi belgilangan",
                       "Muhokama natijalari hisobga olinmasdan qaror kuchga kirishi mumkin.", [ADLIYA, PETITION]),
    "R_adopted_before_end": ("Muhokama tugashidan oldin qabul qilingan",
                             "Bildirilgan takliflar ko'rib chiqilmasdan qaror qabul qilingan bo'lishi mumkin.",
                             [ADLIYA, PETITION]),
    "R_expertise": ("Adliya huquqiy ekspertizasi qayd etilmagan",
                    "Ijobiy adliya xulosasi normativ qaror qabul qilinishining majburiy shartidir.", [ADLIYA]),
    "R_duplicate": ("lex.uz da amalda ko'rsatilgan boshqa qarorning deyarli aynan nusxasi",
                    ("Bir masala bo'yicha ikki qaror amalda bo'lsa, qaysi biriga amal qilish noaniq qoladi. Holat lex.uz "
                    "ma'lumotiga ko'ra; ekspert rasmiy holatni tasdiqlaydi."), [ADLIYA]),
    "R_double_repeal": ("Allaqachon bekor qilingan qarorni yana bekor qiladi",
                        "Qaror yuridik-texnik xatoga ega: u o'z kuchini yo'qotgan hujjatga tayanadi.", [ADLIYA]),
    "R_form": ("Normativ qoidalar farmoyish shaklida chiqarilgan",
               ("Normativ qoida faqat qaror shaklida bo'lishi kerak; farmoyish fuqaro va bizneslar uchun "
               "majburiy qoida o'rnata olmaydi."), [ADLIYA, COURT]),
    "R_competence_land": ("Tuman (shahar) hokimi yer huquqlarini bekor qiladi yoki qayta taqsimlaydi",
                          ("Yer bo'yicha bu vakolat qonun bilan cheklangan; huquqingizga ta'sir qilsa, sud orqali "
                          "himoyalanishingiz mumkin."), [COURT, OMBUDSMAN, ADLIYA]),
    "R_basis": ("Qaror qabul qilingan kuni amalda bo'lmagan hujjat yoki moddaga tayanadi",
                "Asos hujjat kuchini yo'qotgan bo'lsa, qarorning huquqiy asosi zaiflashadi.", [ADLIYA]),
}

_NUM = re.compile(r"\b(?:[IVX]+-)?\d+(?:-\d+)+-[QFK]/\d{2}\b")


def explain(flag: dict, report: dict) -> dict:
    """Uzbek title, plain meaning, channels and an appeal draft the person sends themselves."""
    title, plain, channels = TEXTS.get(flag["check"], (flag["title"], flag["explanation"], [ADLIYA]))
    nums = [n for n in _NUM.findall(flag["title"]) if n != report["reg_number"]]
    if nums:
        title = f"{title} ({', '.join(nums)})"
    law = flag["citations"][0] if flag["citations"] else None
    law_line = f"{law['act_title']}, {law['article']}: «{law['quote']}»" if law and law.get("quote") else ""
    appeal = "\n".join(line for line in [
        "Hurmatli mutasaddilar!",
        (f"{report['body']} tomonidan {report['date']} da qabul qilingan {report['reg_number']}-sonli "
        f"«{report['title']}» qarori bo'yicha murojaat qilaman."),
        f"Ehtimoliy kamchilik: {title}.",
        law_line,
        "Ushbu qarorning qonunchilikka muvofiqligini tekshirib, natijasi haqida xabar berishingizni so'rayman.",
        "Murojaatchi: ____________ (F.I.Sh., manzil, telefon)",
    ] if line)
    return {"title_uz": title, "plain_uz": plain, "channels": channels, "appeal_uz": appeal}


# What each group of checks looked at, for the "Nega belgilanmadi?" list on a clean result.
CHECKED = {
    "R_business_3m+R_retroactive": (("Tadbirkorga yangi to'lov yoki majburiyat va kuchga kirish sanasi "
                                    "(NHH Qonuni 40, 41-moddalar; Soliq kodeksi 4-modda)"), True),
    "R_draft_window+R_discussion_short": ("Loyiha muhokamasi muddati va kuchga kirish sanasi (NHH Qonuni 24-modda)", False),
    "R_discussion+R_adopted_before_end": ("Jamoatchilik muhokamasi o'tkazilgani va qabul qilish sanasi", False),
    "R_expertise": ("Adliya huquqiy ekspertizasi bosqichi (E-qaror)", False),
    "R_form": ("Normativ qoida farmoyish shaklida chiqarilmagani", True),
    "R_competence_land": ("Tuman (shahar) hokimining yer huquqlari bo'yicha vakolati (PF-6243, 4-band, sanasiga ko'ra)",
                          True),
    "R_duplicate+R_double_repeal": ("Amaldagi qarorning nusxasi yoki takroriy bekor qilish emasligi", True),
    "R_basis": ("Asos qilingan hujjatlar qaror kuni amalda bo'lgani", True),
}


def checked(report: dict, text: str, law=None, on: str = "") -> list[dict]:
    """One line per check group that raised nothing: what was looked at and why it stayed silent."""
    from mezon.rules.business import burden_clause
    from research.regulation_window import entry_into_force

    flagged = {f["check"] for f in report["flags"]}
    out = []
    for group in report["checks_run"]:
        name = group.split(" (")[0]
        what, needs_text = CHECKED.get(name, (name, False))
        if any(c in flagged for c in name.split("+")):
            continue
        if name == "R_draft_window+R_discussion_short" and report.get("gate") != "0_draft":
            why = "Faqat loyihalar uchun: bu qabul qilingan qaror."
        elif needs_text and not text:
            why = "Qaror matni bizda yo'q: tekshirilmadi."
        elif name == "R_business_3m+R_retroactive":
            found = burden_clause(text)
            if not found:
                why = "Yangi to'lov yoki majburiyat belgilovchi band topilmadi."
            elif entry_into_force(text)["kind"] == "none":
                why = ("Kuchga kirish sanasi ko'rsatilmagan: qonunning o'zi (NHH Qonuni 40-modda 2-qism) tadbirkor uchun "
                       "kamida 3 oyni ta'minlaydi, shuning uchun kamchilik yo'q.")
            else:
                why = "Kuchga kirish sanasi qonunda belgilangan muddatga mos."
        elif name == "R_basis":
            why = _basis_seen(text, law, on)
        elif name == "R_duplicate+R_double_repeal":
            why = ("Shu organning avvalgi qarorlari bilan bandma-band solishtirildi: amaldagi deyarli aynan nusxa yoki "
                   "allaqachon bekor qilingan qarorni qayta bekor qilish topilmadi.")
        elif "not checked" in group:
            why = "Qonun bazasi mavjud emas: tekshirilmadi."
        else:
            why = "Tekshirildi, kamchilik topilmadi."
        out.append({"check": name, "what_uz": what, "why_uz": why})
    return out


def _basis_seen(text: str, law, on: str) -> str:
    """Name each act the preamble cites and what the law store says about it on the decision date."""
    from mezon.rules.basis import references

    refs = [num for num, _ in references(text)]
    if not refs:
        return "Muqaddimada PF, PQ, VMQ yoki O'RQ raqamli hujjat topilmadi."
    seen, unknown = [], []
    names = {"@taxcode": "Soliq kodeksi", "@budgetcode": "Budjet kodeksi", "@landcode": "Yer kodeksi",
             "@lsp": "Mahalliy davlat hokimiyati to'g'risida Qonun", "@nla": "NHH to'g'risida Qonun"}
    for ref in refs[:6]:
        num = names.get(ref, ref)
        key = (ref[1:] if ref.startswith("@") else law.find_act(ref)) if law else None
        if not key:
            unknown.append(num)
        elif law.in_force(key, on) is not False:
            seen.append(num)
    parts = []
    if seen:
        parts.append(f"{', '.join(seen)}: {on} holatiga amalda.")
    if unknown:
        parts.append(f"{', '.join(unknown)}: qonun bazamizda yo'q, tekshirilmadi.")
    return " ".join(parts)
