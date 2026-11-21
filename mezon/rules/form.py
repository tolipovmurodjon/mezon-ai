"""Form: a local normative act must be a qaror, never a farmoyish (NLA art. 16; order 3333 ¶1-2)."""

import re

from mezon.report import Evidence, Flag
from mezon.rules.common import SafeLaw, cite, operative_clauses, text_evidence
from research.textnorm import fold

STRONG = re.compile(r"\b(?:taqiqlan\w*|majburiy|jarima\w*|(?:tartib\w*|nizom\w*|qoidalar\w*) tasdiqlansin)")
WEAK = re.compile(r"\bbarcha\b.{0,80}\b(?:belgilansin|majbur\w*|amal qilsin)")


def check(d: dict, law: SafeLaw) -> list:
    if d.get("type") != "F" or d.get("role") == "draft":
        return []
    on = d.get("adopted") or ""
    cites = [cite(law, "nla", "art:16", on), cite(law, "o3333", "annex:1/cl:1", on)]
    if d.get("is_normative") == 1:
        return [
            Flag(
                check="R_form",
                title="A normative act issued as a farmoyish",
                explanation=(
                    "E-qaror marks this farmoyish as normative. Local normative acts are adopted only as a "
                    "qaror; a farmoyish can't carry binding norms (NLA art. 16; order 3333 ¶1-2)."
                ),
                severity="medium",
                evidence=[Evidence("eqaror_metadata", "Hujjat xarakteri", "Normativ", d.get("url") or "")],
                citations=cites,
            )
        ]
    for n, clause in operative_clauses(d.get("text") or ""):
        f = fold(clause)
        strong, weak = STRONG.search(f), WEAK.search(f)
        if strong or weak:
            return [
                Flag(
                    check="R_form",
                    title="Binding norms inside a farmoyish",
                    explanation=(
                        f"Clause {n} of this farmoyish reads like a binding norm. Local normative acts are "
                        "adopted only as a qaror (NLA art. 16; order 3333 ¶1-2)."
                    ),
                    severity="medium" if strong else "low",
                    status="possible_violation" if strong else "unclear_needs_expert",
                    evidence=[text_evidence(d, f"clause {n}", clause)],
                    citations=cites,
                )
            ]
    return []
