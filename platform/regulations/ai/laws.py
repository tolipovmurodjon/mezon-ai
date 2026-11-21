"""
A small registry of the acts the demo checks can recognise.

The real model reads the full law store, every edition by date. This registry
covers the handful of acts named in the project brief, so the demo can find
citations and spot an article that has lost force. Treat it as sample data.
"""
import re

A = r"[‘'`ʻ’ʼ]"  # any of the apostrophes people type for o‘ / g‘

LAWS = {
    "nhh": {
        "title": "“Normativ-huquqiy hujjatlar to‘g‘risida”gi Qonun",
        "match": rf"normativ-huquqiy hujjatlar to{A}g{A}risida",
    },
    "mdh": {
        "title": "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun",
        "match": rf"mahalliy davlat hokimiyati to{A}g{A}risida",
        # article -> (date it lost force, note shown to the expert)
        "lost": {25: ("2024-10-19", "O‘RQ-976 bilan kuchini yo‘qotgan (19.10.2024)")},
    },
    "tadbirkor": {
        "title": "“Tadbirkorlik faoliyati erkinligining kafolatlari to‘g‘risida”gi Qonun",
        "match": r"tadbirkorlik faoliyati erkinligining kafolatlari",
    },
    "talim": {
        "title": "“Ta’lim to‘g‘risida”gi Qonun",
        "match": rf"ta{A}?lim to{A}g{A}risida",
    },
    "xarid": {
        "title": "“Davlat xaridlari to‘g‘risida”gi Qonun",
        "match": rf"davlat xaridlari to{A}g{A}risida",
    },
    "soliq": {"title": "O‘zbekiston Respublikasi Soliq kodeksi", "match": r"soliq kodeksi"},
    "yer": {"title": "O‘zbekiston Respublikasi Yer kodeksi", "match": r"yer kodeksi"},
    "konst": {"title": "O‘zbekiston Respublikasi Konstitutsiyasi", "match": r"konstitutsiya"},
}

# Rule sources: what each check measures against.
RULE_SOURCES = {
    "retroactivity": "“Normativ-huquqiy hujjatlar to‘g‘risida”gi Qonun, 41-modda",
    "anti_corruption": "O‘RQ-860 · korrupsiyaga qarshi ekspertiza (29 omil)",
    "linguistic": "VMQ-662, 9-band · davlat tilida hujjat yuritish",
    "public_discussion": "NHH loyihalarini jamoatchilik muhokamasiga qo‘yish (kamida 15 kun)",
    "business_3m": "Tadbirkorlarga yangi majburiyat: e’lon qilingandan kamida 3 oy o‘tib kuchga kiradi",
    "competence": "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun · Kengash va hokim vakolatlari",
    "rights": "O‘zbekiston Respublikasi Konstitutsiyasi · fuqarolarning teng huquqliligi",
    "form": "“Normativ-huquqiy hujjatlar to‘g‘risida”gi Qonun · hujjat shakllari",
    "tax_timing": "O‘zbekiston Respublikasi Soliq kodeksi · stavkalarni o‘zgartirish muddatlari",
    "budget": "O‘zbekiston Respublikasi Byudjet kodeksi · moliyalashtirish manbai",
}

_compiled = {key: re.compile(law["match"], re.IGNORECASE) for key, law in LAWS.items()}


def find_law_mentions(text):
    """Return [(law_key, match_start, match_end)] for every recognised act in the text."""
    hits = []
    for key, rx in _compiled.items():
        for m in rx.finditer(text):
            hits.append((key, m.start(), m.end()))
    return sorted(hits, key=lambda h: h[1])
