"""Corruption-inducing factors in the text of a decision, as the Law on anti-corruption expertise defines them.

O'RQ-860 (08.08.2023, lex.uz -6561894) lists 29 factors in four families (arts. 12-15) and makes the expertise a
checklist in its annex (arts. 16-17); district and regional adliya units examine hokim and Kengash drafts (art. 7).
A factor is a property of a NORM ("huquqiy normalar", art. 3), never an accusation against anyone, so every flag here
is "unclear: needs expert" and names the law's own factor.

Only the factors whose wording a rule can see are checked. Each pattern was measured on 1,104 texts before it was kept
(19.11.2026): broad phrases that are ordinary drafting ("belgilangan tartibda", "o'z vaqtida", "bundan mustasno" with
a stated criterion) were dropped for precision. Factors 5 (unclear executor) and 17 (vague time limits) were also
dropped after reading samples: "mas'ul tashkilotlar" mostly names a defined group, and "zudlik bilan" mostly orders a
state body, not a person; both need the reader on the box, which can tell who a norm is addressed to. The rest of the checklist is filled by checklist() below.
"""

import csv
import re
from pathlib import Path

from mezon.report import Flag
from mezon.rules.common import SafeLaw, cite, operative_clauses, text_evidence
from research.textnorm import fold

FACTORS_CSV = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "corruption_factors_860.csv"

# factor number -> (pattern on the folded clause, the article, a needle to quote the factor from that article)
RULES = {
    4: (r"zarur (?:hollarda|bolganda|bolgan hollarda)|zarurat (?:bolganda|tugilganda)|oz ixtiyoriga kora",
        "art:13", "diskretsion vakolatlarning kengligi"),
    15: (r"alohida hollarda|istisno tariqasida", "art:14", "istisnolarning asossiz"),
    18: (r"kelishilgan narx\w*|kelishuv asosidagi narx\w*", "art:14", "miqdorlarining noaniqligi"),
    24: (r"taqiqlanmagan boshqa manbalar|boshqa manbalar hisobidan", "art:14", "moliyalashtirish manbalarining"),
}


def factors() -> list[dict]:
    with FACTORS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(d: dict, law: SafeLaw | None = None) -> list:
    law = law or SafeLaw(None)
    text = d.get("text") or ""
    if not text:
        return []
    names = {int(r["n"]): r["factor_uz"] for r in factors()}
    on = d.get("adopted") or d.get("disc_end") or ""
    flags = []
    for n, (pattern, article, needle) in RULES.items():
        for num, clause in operative_clauses(text):
            m = re.search(pattern, fold(clause))
            if not m:
                continue
            flags.append(
                Flag(
                    check="R_corruption_factor",
                    title=f"Possible corruption-inducing factor {n}: {names.get(n, '')}",
                    explanation=(
                        f"Clause {num} uses \"{m.group(0)}\", the kind of wording O'RQ-860 lists as a corruption-inducing "
                        f"factor (\"{names.get(n, '')}\", {article.replace('art:', 'art. ')}). A factor is a property of "
                        "the norm, not of any person: the expert decides whether the wording is justified here and, "
                        "if not, how to restate it (O'RQ-860 arts. 16, 18)."
                    ),
                    severity="medium",
                    status="unclear_needs_expert",
                    evidence=[text_evidence(d, f"clause {num}", clause)],
                    citations=[cite(law, "anticorruption860", article, on, needle)],
                    impact="business" if n in (18, 24) else "",
                )
            )
            break  # one flag per factor per decision: the checklist row, with its first clause as evidence
    return flags


def checklist(report: dict, has_text: bool) -> list[dict]:
    """The O'RQ-860 annex checklist, pre-filled: one row per factor, with what Mezon could and could not see."""
    found = {}
    for f in report.get("flags", []):
        if f["check"] == "R_corruption_factor":
            m = re.search(r"factor (\d+)", f["title"])
            if m:
                found[int(m.group(1))] = f
    # Other Mezon checks already answer two rows: acting outside competence (factor 7) and transparency gaps (factor 27).
    linked = {7: ("R_competence_land", "R_form"), 27: ("R_discussion",)}
    for n, checks in linked.items():
        hit = next((f for f in report.get("flags", []) if f["check"] in checks), None)
        if hit and n not in found:
            found[n] = hit
    rows = []
    for r in factors():
        n = int(r["n"])
        if n in found:
            ev = found[n]["evidence"][0]
            src = "" if found[n]["check"] == "R_corruption_factor" else f"[{found[n]['check']}] "
            answer, note = "bor (ehtimoliy)", f"{src}{ev.get('locator', '')}: {ev.get('quote', '')[:240]}"
        elif r["method"] == "rule" and n in RULES:
            answer, note = ("aniqlanmadi" if has_text else "matn yo'q"), "Qoida bo'yicha tekshirildi."
        elif r["method"] == "rule":
            answer, note = "ekspert", "Qoida sinab ko'rildi, lekin aniqligi yetarli emas: ekspert baholaydi."
        elif r["method"] == "llm":
            answer, note = "AI tekshiruvi kerak", "Mahalliy til modeli (Qwen) bilan, iqtibos bilan tekshiriladi."
        else:
            answer, note = "ekspert", "Matndan aniqlab bo'lmaydi: ekspert baholaydi."
        rows.append({"n": n, "family": r["family"], "article": r["article"], "factor_uz": r["factor_uz"],
                     "answer": answer, "note": note})
    return rows
