"""Competence over land (PF-6243, 08.06.2021, cl. 4 and 8), read in the edition in force on the decision's date.

From 01.08.2021 local bodies lost the power to allocate land directly, grant it for use, reserve or attach it, or
otherwise dispose of it (except permanent use for state organisations and signing lease contracts), and district and
city bodies lost the power to set, recognise or change land rights. Revoking land rights was on that list until the
edition of 01.05.2026, which removed it: so a revocation is flagged only if the ban was in force on the decision date.
"""

import datetime as dt
import re

from mezon.report import Flag
from mezon.rules.common import SafeLaw, cite, date, operative_clauses, squash, text_evidence
from research.textnorm import fold

IN_FORCE = dt.date(2021, 8, 1)
LAND = re.compile(r"\byer (?:uchastka|maydon)\w*|\bdehqon xojalig\w*|\bfermer xojalig\w*|\bmeros qilib qoldiriladigan")
ALLOCATE = re.compile(
    r"\b(?:ajratilsin|ajratib berilsin|foydalanishga berilsin|biriktirilsin|biriktirib berilsin|zaxiralansin"
    r"|obodonlashtirish uchun berilsin|ijaraga berilsin)"
)
RIGHTS = re.compile(
    r"\b(?:nomiga (?:otkazilsin|qayta rasmiylashtirilsin|rasmiylashtirilsin)|qayta rasmiylashtirilsin"
    r"|huquq\w* (?:belgilansin|etirof etilsin|ozgartirilsin|tan olinsin))"
)
REVOKE = re.compile(
    r"\b(?:olib qoyilsin|zaxira\w* qaytarilsin|zaxiraga olinsin|qaytarib olinsin|huquqi\w* bekor qilinsin"
    r"|ijara\w* bekor qilinsin|tugatilsin)"
)
EXCEPTION = re.compile(r"doimiy foydalanish\w*|ijara shartnoma\w*|auksion\w*|ochiq tanlov\w*")
COURT = re.compile(r"\b(?:sud\w*|hal qiluv qarori|prokuror\w*|protest\w*)\b")


def _revoke_banned(law: SafeLaw, on: str) -> bool:
    """Was "bekor qilish" of land rights still among the ended district powers on this date?"""
    u = law.get_unit("pf6243", "cl:4", on) if law else None
    return bool(u and squash("o'zgartirish, bekor qilish") in squash(u["text"]))


def check(d: dict, law: SafeLaw) -> list:
    adopted = date(d.get("adopted"))
    if d.get("type") != "Q" or not d.get("district") or d.get("role") != "adopted" or not adopted:
        return []
    if adopted < IN_FORCE:
        return []
    on = d["adopted"]
    for n, clause in operative_clauses(d.get("text") or ""):
        f = fold(clause)
        if not LAND.search(f):
            continue
        if ALLOCATE.search(f):
            kind, needle = "allocates or grants land", "togridan-togri ajratish"
        elif RIGHTS.search(f):
            kind, needle = "sets or changes land rights", "huquqlarni belgilash"
        elif REVOKE.search(f) and _revoke_banned(law, on):
            kind, needle = "revokes land rights", "huquqlarni belgilash"
        else:
            continue
        unclear = bool(COURT.search(f) or EXCEPTION.search(f))
        return [
            Flag(
                check="R_competence_land",
                title=f"A district or city hokim {kind} after 01.08.2021",
                explanation=(
                    f"Clause {n} {kind}. PF-6243 cl. 4, in the edition in force on {on}, ended this power of "
                    "district and city bodies from 01.08.2021; land now goes through e-auction or open tender, and "
                    "cl. 8 stops any other allocation."
                    + (" The clause mentions a court, a prosecutor, an auction, a tender, a lease contract or "
                       "permanent use for a state body, which can be a lawful exception." if unclear else "")
                ),
                severity="high" if not unclear else "medium",
                status="unclear_needs_expert" if unclear else "possible_violation",
                evidence=[text_evidence(d, f"clause {n}", clause)],
                citations=[cite(law, "pf6243", "cl:4", on, needle)],
            )
        ]
    return []
