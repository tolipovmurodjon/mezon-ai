"""Why were local decisions cancelled? Reason categories mined from the texts of the cancelling decisions.

Each POSITIVE cancelling decision (adliya representation, prosecutor protest, court) is scanned for reason phrases.
A decision can carry several reasons. Output: data/interim/cancel_reasons.csv and counts printed with N.
The phrases are a first pass; the lawyer confirms the categories on a sample before any number is used on stage.
"""

import csv
import re
from collections import Counter

from mezon.config import DATA
from mezon.decisions.store import DecisionStore
from research.textnorm import fold

OUT = DATA / "interim" / "cancel_reasons.csv"

# category -> (pattern on folded text, the Mezon rule that covers it or "" if none yet)
REASONS = {
    "contrary_to_law": (r"qonun\w* (?:hujjat\w* )?(?:talab\w* )?zid|qonunchilik\w* zid|qonunga muvofiq emas", "R_conflict (LLM)"),
    "beyond_competence": (r"vakolat\w* (?:doira\w* )?(?:dan )?tashqari|vakolati(?:ga)? kirmaydi|vakolatsiz", "R_competence_*"),
    "no_legal_expertise": (r"huquqiy ekspertiza\w*(?:dan)? o?tkaz\w*ma|ekspertiza\w* xulosa\w*siz|ekspertizadan otkazilmasdan", "R_expertise"),
    "no_public_discussion": (r"muhokama\w* (?:o?tkaz\w*ma|qilinmas)|muhokamaga qo?yilmas", "R_discussion"),
    "not_published": (r"e[ ']?lon qilinma|rasmiy e[ ']?lon qilinmagan", ""),
    "wrong_form": (r"farmoyish shaklida|farmoyish\w* bilan .{0,60}normativ", "R_form"),
    "business_burden": (r"tadbirkor\w*.{0,80}(?:cheklov|majburiyat|to?siq)|ombudsman", "R_business_3m"),
    "land_property": (r"yer uchastka\w*|mulk huquq\w*|olib qo?yish", "R_competence_land"),
    "duplicate_or_repeal": (r"takror\w*|kuchini yo?qotgan .{0,80}qayta|ilgari qabul qilingan", "R_duplicate / R_double_repeal"),
    "fees_tariffs": (r"to?lov\w*|tarif\w*|yig?im\w*|stavka\w*", "R_fee (none yet)"),
    "retroactive": (r"orqaga qaytish|oldingi davr\w*ga", "R_retroactive"),
    "vague_or_corruption": (r"korrupsiya\w*|noaniq", "R_vague (LLM)"),
}


def main() -> None:
    s = DecisionStore()
    cancelling = [s.get(i) for i in s.ids("cancelling")]
    cancelling = [d for d in cancelling if d and d["label"] == "POSITIVE" and d["text"]]
    counts, rows = Counter(), []
    for d in cancelling:
        f = fold(d["text"])
        hit = []
        for name, (pat, _) in REASONS.items():
            m = re.search(pat, f)
            if m:
                hit.append(name)
                counts[name] += 1
                rows.append({"cancelling": d["reg_number"], "url": d["url"], "reason": name,
                             "snippet": f[max(0, m.start() - 120): m.end() + 120]})
        if not hit:
            counts["(no reason phrase)"] += 1
            rows.append({"cancelling": d["reg_number"], "url": d["url"], "reason": "(no reason phrase)", "snippet": ""})
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["cancelling", "url", "reason", "snippet"])
        w.writeheader()
        w.writerows(rows)
    print(f"POSITIVE cancelling decisions with text: N={len(cancelling)}")
    for name, n in counts.most_common():
        rule = REASONS.get(name, ("", ""))[1]
        print(f"  {name:24s} {n:3d}  ({n / len(cancelling):.0%})  rule: {rule or '-'}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
