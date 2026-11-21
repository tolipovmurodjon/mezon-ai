"""A draft legal-expertise conclusion in the three-verdict format of Adliya order No. 3333, for the reviewer to edit and sign.

It is a draft, never a conclusion: Mezon fills in what it flagged, with the law's exact words, and the expert decides.
Layout follows the order's verdicts and the "defect -> article -> quote" rule (brief 2k); the exact official template
should be checked with a district adliya expert before the format is called official.
"""

VERDICT_UZ = {
    "positive": "Ijobiy",
    "positive_with_fixable_defects": "Bartaraf etiladigan kamchiliklar bilan ijobiy",
    "negative": "Salbiy",
    "not_checked": "Tekshirilmagan",
}
UNIT_UZ = {"art": "modda", "part": "qism", "cl": "band", "annex": "ilova", "para": "xatboshi", "ch": "bob"}


def _unit(path: str) -> str:
    out = []
    for seg in (path or "").split("/"):
        key, _, val = seg.partition(":")
        out.append(f"{val}-{UNIT_UZ[key]}" if key in UNIT_UZ and val else seg)
    return ", ".join(out)


def draft(report: dict) -> str:
    """Plain-text draft conclusion from an audit report (Report.to_dict(), optionally enriched by mezon.plain)."""
    lines = [
        "HUQUQIY EKSPERTIZA XULOSASI (LOYIHA)",
        "Mezon tomonidan tayyorlangan qoralama. Ekspert tomonidan tekshirilib, tahrir qilinishi va imzolanishi kerak.",
        "",
        f"Hujjat: {report.get('body', '')}ning {report.get('date', '')} dagi {report.get('reg_number', '')}-sonli",
        f"«{report.get('title', '')}» qarori",
        f"Manba: {report.get('url', '')}",
        "",
        f"Taklif etilayotgan xulosa: {VERDICT_UZ.get(report.get('verdict', ''), report.get('verdict', ''))}",
        "",
    ]
    flags = report.get("flags") or []
    if not flags:
        lines.append("Avtomatik tekshiruvlar bo'yicha kamchilik aniqlanmadi. Ekspert qolgan masalalarni ko'rib chiqadi.")
    for i, f in enumerate(flags, 1):
        status = "ehtimoliy qoidabuzarlik" if f.get("status") == "possible_violation" else "noaniq, ekspert xulosasi kerak"
        lines.append(f"{i}. {f.get('title_uz') or f.get('title', '')} ({status})")
        for ev in f.get("evidence") or []:
            if ev.get("quote"):
                label = "lex.uz holati" if ev.get("source") == "lexuz" else "Qarordan"
                lines.append(f"   {label}: «{ev['quote']}»")
        for ct in f.get("citations") or []:
            ref = f"{ct.get('act_title', '')}, {_unit(ct.get('article', ''))} ({ct.get('on_date', '')} holatiga)"
            lines.append(f"   Asos: {ref}" + (f": «{ct['quote']}»" if ct.get("quote") else ""))
        lines.append("   Ekspert xulosasi: [ ] tasdiqlanadi   [ ] rad etiladi   Izoh: ____________")
        lines.append("")
    ling = report.get("linguistic_662") or {}
    if ling.get("findings"):
        lines.append("LINGVISTIK EKSPERTIZA (VMQ-662, ilova, 9-band: imlo va orfografiya qoidalari)")
        for x in ling["findings"]:
            lines.append(f"   «{x['word']}» → «{x['fixed']}» (lotin va kirill harflari aralashgan)")
        lines.append("")
    rows = report.get("checklist_860") or []
    if rows:
        found = [r for r in rows if r["answer"].startswith("bor")]
        lines += [
            "KORRUPSIYAGA QARSHI EKSPERTIZA (O'RQ-860, 16-18-moddalar, ilovadagi cheklist)",
            f"Korrupsiyani keltirib chiqaruvchi omillar: {len(found)} ta ehtimoliy omil, {len(rows)} ta omildan.",
        ]
        for r in rows:
            mark = {"bor (ehtimoliy)": "[bor?]", "aniqlanmadi": "[yo'q]"}.get(r["answer"], "[ekspert]")
            line = f"  {r['n']:>2}. {mark} {r['factor_uz']}"
            if r["answer"].startswith("bor"):
                line += f"\n      Norma: {r['note']}\n      Tavsiya: ____________________"
            elif r["answer"] not in ("aniqlanmadi",):
                line += f"  ({r['answer']})"
            lines.append(line)
        lines.append("")
    lines += [
        f"Tekshirilgan qoidalar: {', '.join(report.get('checks_run') or [])}",
        f"Mezon qoidalari versiyasi: {report.get('ruleset', 'nomalum')} (shu versiya bilan natijani qayta olish mumkin)",
        (f"lex.uz holati tekshirilgan: {report['lexuz_checked']}"
         + (" (o'z kuchini yo'qotgan: ekspert e'tibori)" if report.get("lexuz_status", "").startswith("lost force") else "")
         if report.get("lexuz_checked") else "lex.uz holati hali qayta tekshirilmagan: imzolashdan oldin lex.uz da ko'ring."),
        (f"Tekshirilgan qaror matni: sha256 {report['text_sha']} ({report.get('url', '')}); matn keyin o'zgarsa, "
         "bu belgi mos kelmaydi." if report.get("text_sha") else "Qaror matni bizda yo'q: faqat E-qaror bosqichlari tekshirildi."),
        "Belgilangan ≠ noqonuniy. Har bir belgi bo'yicha qarorni ekspert qabul qiladi (AI etikasi qoidalari, 3787-son).",
        "",
        "Ekspert: ____________________   Imzo: __________   Sana: __________",
    ]
    return "\n".join(lines)
