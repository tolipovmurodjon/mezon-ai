"""Procedure: public discussion (NLA art. 24), the draft window, and the mandatory adliya expertise (order 3333 ¶6)."""

import re

from mezon.report import Evidence, Flag
from mezon.rules.common import SafeLaw, cite, date, stage, text_evidence
from research.regulation_window import entry_into_force
from research.textnorm import fold, similarity

MIN_WINDOW_DAYS = 15
# Mid-year allocations of extra budget revenue ("qo'shimcha manbalar hisobidan mablag' yo'naltirish") fill most of the
# portal's 10-day windows (168 of 172 short open drafts on 19.11.2026). NLA art. 24 part 3 binds normative drafts, and
# these spend money rather than set general rules, so the short-window rule skips them until a lawyer says otherwise.
BUDGET_ALLOCATION = re.compile(
    r"(?:b[iy]?u?dj?e?t|byudjet|budjet)\w*.{0,120}(?:qo.?shimcha|qos[iı]msha|qöşimça|ortti?ri?b|oshirib|artt[iı]r|erkin qoldiq|"
    r"optimizats|optimizaci)|(?:qo.?shimcha|qos[iı]msha|qöşimça) (?:manba|derek)|mablag\w* (?:ajrat|yo.?nalt|xarajat)|"
    r"qarj[iı]lard[iı]\w* (?:jumsal|ba[gǵ]darla|b[oó]list)"
)


def is_budget_allocation(title: str) -> bool:
    return bool(BUDGET_ALLOCATION.search(fold(title or "")))


DRAFT_MATCH = 0.75
STAGE_CAVEAT = (
    " The E-qaror stage strip is a signal, not proof: it has shown a skipped stage for a discussion "
    "that was in fact held (Tashkent design-code), so an expert should confirm."
)


def _stage_ev(d: dict, name: str, done: int) -> Evidence:
    return Evidence(
        source="eqaror_stages",
        locator=name,
        quote=f"{name}: {'bajarilgan' if done else 'o‘tkazilmagan (kulrang)'}",
        url=d.get("url") or "",
    )


def draft_window(d: dict, law: SafeLaw) -> list:
    if d.get("role") != "draft" or not d.get("disc_end"):
        return []
    flags = []
    end, start = date(d["disc_end"]), date(d.get("disc_start"))
    eif = entry_into_force(d["text"]) if d.get("text") else {"kind": "none"}
    meta = Evidence(
        source="regulation_metadata",
        locator="discussion",
        quote=f"Muhokama: {d.get('disc_start')} – {d['disc_end']}",
        url=d.get("url") or "",
    )
    if eif["kind"] == "date" and end and eif["date"] <= end:
        flags.append(
            Flag(
                check="R_draft_window",
                title="The draft takes effect before its public discussion ends",
                explanation=(
                    f"The draft says it takes effect on {eif['date'].isoformat()}, but its public discussion "
                    f"on regulation.gov.uz runs until {end.isoformat()}. Comments can't shape a rule that is "
                    "already in force (NLA art. 24)."
                ),
                severity="high",
                evidence=[text_evidence(d, "entry into force", eif["sentence"]), meta],
                citations=[cite(law, "nla", "art:24/part:4", d["disc_end"])],
            )
        )
    if start and end and (end - start).days < MIN_WINDOW_DAYS and not is_budget_allocation(d.get("title")):
        flags.append(
            Flag(
                check="R_discussion_short",
                title=f"Public discussion shorter than {MIN_WINDOW_DAYS} days",
                explanation=(
                    f"The discussion window is {(end - start).days} days ({start} – {end}); the NLA Law requires at "
                    f"least {MIN_WINDOW_DAYS} days from posting (art. 24 part 3). Many local drafts on the portal "
                    "run 10 days, so an expert should confirm before this is raised."
                ),
                severity="medium",
                status="unclear_needs_expert",
                evidence=[meta],
                citations=[cite(law, "nla", "art:24/part:3", d["disc_end"], "on besh")],
            )
        )
    return flags


def _place(body: str) -> tuple[str, bool]:
    """(the place name before tuman/shahar/viloyat, is it a Kengash) from a body or draft creator."""
    f = fold(body)
    m = re.search(r"(\w+) (?:tuman|shahar|shahri|viloyat)", f)
    return (m[1] if m else ""), "kengash" in f


def matching_draft(d: dict, drafts: list[dict]) -> dict | None:
    """The same body's draft with a near-identical title (school-district decisions look alike everywhere)."""
    title = d.get("title") or ""
    place = _place(d.get("body") or "")
    if not title or not place[0]:
        return None
    same = [x for x in drafts if _place(x.get("body") or "") == place]
    best = max(same, key=lambda x: similarity(title, x.get("title") or ""), default=None)
    return best if best and similarity(title, best.get("title") or "") >= DRAFT_MATCH else None


def discussion(d: dict, law: SafeLaw, drafts: list[dict]) -> list:
    if d.get("role") == "draft" or d.get("is_normative") != 1:
        return []
    done = stage(d, "jamoatchilik")
    on = d.get("adopted") or ""
    draft = matching_draft(d, drafts)
    if draft:
        adopted, end = date(d.get("adopted")), date(draft.get("disc_end"))
        if adopted and end and adopted < end:
            return [
                Flag(
                    check="R_adopted_before_end",
                    title="Adopted before its public discussion ended",
                    explanation=(
                        f"The decision was adopted on {adopted}, but its draft ({draft['url']}) was open for "
                        f"discussion until {end} (NLA art. 24)."
                    ),
                    severity="high",
                    evidence=[
                        Evidence(
                            "regulation_metadata",
                            "discussion",
                            f"Muhokama: {draft.get('disc_start')} – {draft['disc_end']}",
                            draft["url"],
                        )
                    ],
                    citations=[cite(law, "nla", "art:24/part:1", on)],
                )
            ]
        return []
    if done != 0:
        return []
    return [
        Flag(
            check="R_discussion",
            title="No public discussion recorded for a normative decision",
            explanation=(
                "E-qaror shows the public-discussion stage as skipped, and no matching draft was found on "
                "regulation.gov.uz. Normative drafts must go to public discussion (NLA art. 24)."
                + STAGE_CAVEAT
            ),
            severity="medium",
            status="unclear_needs_expert",
            evidence=[_stage_ev(d, "Jamoatchilik muhokamasi", 0)],
            citations=[cite(law, "nla", "art:24/part:1", on)],
        )
    ]


def expertise(d: dict, law: SafeLaw) -> list:
    if d.get("role") == "draft" or d.get("is_normative") != 1 or stage(d, "huquqiy ekspertiza") != 0:
        return []
    return [
        Flag(
            check="R_expertise",
            title="No adliya legal expertise recorded for a normative decision",
            explanation=(
                "E-qaror shows the legal-expertise stage as skipped. A positive conclusion of the regional "
                "adliya body is a mandatory condition for adopting a local normative decision (order 3333 ¶6)."
                + STAGE_CAVEAT
            ),
            severity="medium",
            evidence=[_stage_ev(d, "Huquqiy ekspertiza", 0)],
            citations=[cite(law, "o3333", "annex:1/cl:6", d.get("adopted") or "")],
        )
    ]
