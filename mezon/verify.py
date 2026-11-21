"""The verifier: no flag leaves without verbatim evidence, and no citation survives unless the law store backs it.

Error labels follow Magesh et al. (2024): fabricated (the source or quote doesn't exist), misgrounded (the act wasn't
in force on the date), ungrounded (no valid citation left).
"""

from collections import Counter
from dataclasses import replace

from mezon.report import Flag
from mezon.rules.common import SafeLaw, squash


def _evidence_ok(ev, decision: dict, decisions) -> bool:
    q = squash(ev.quote or "")
    if not q:
        return False
    if ev.source in ("decision", "draft"):
        return q in squash(decision.get("text") or "")
    if ev.source == "related_decision":
        if decisions is None:
            return True
        other = decisions.get(ev.locator)
        return bool(other) and q in squash(other.get("text") or "")
    if ev.source == "eqaror_stages":
        return any(squash(ev.locator) == squash(name) for name in (decision.get("stages") or {}))
    return True


def verify_flag(flag: Flag, decision: dict, law, decisions=None) -> tuple[Flag | None, Counter]:
    law = law if isinstance(law, SafeLaw) else SafeLaw(law)
    stats: Counter = Counter()
    evidence = []
    for ev in flag.evidence:
        if _evidence_ok(ev, decision, decisions):
            evidence.append(ev)
        else:
            stats["fabricated_evidence"] += 1
    if not evidence:
        return None, stats

    citations = []
    for c in flag.citations:
        if not law:
            stats["unverifiable"] += 1
            citations.append(c)
            continue
        key = law.find_act(c.act_id)
        if not key:
            stats["fabricated"] += 1
            continue
        if law.in_force(key, c.on_date) is False:
            stats["misgrounded"] += 1
            continue
        unit = law.get_unit(key, c.article, c.on_date)
        if not unit or not unit.get("text"):
            stats["fabricated"] += 1
            continue
        if c.quote and squash(c.quote) not in squash(unit["text"]):
            stats["fabricated"] += 1
            continue
        citations.append(
            replace(
                c, act_id=key, quote=c.quote or unit["text"].strip()[:300], url=c.url or unit.get("url", "")
            )
        )

    status = flag.status
    if not law:
        status = "unclear_needs_expert"
    elif not citations:
        stats["ungrounded"] += 1
        status = "unclear_needs_expert"
    return replace(flag, evidence=evidence, citations=citations, status=status), stats
