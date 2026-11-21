"""Business burdens that take effect too soon (NLA art. 40) or reach back in time (NLA art. 41)."""

import datetime as dt
import re

from mezon.report import Flag
from mezon.rules.common import SafeLaw, add_months, cite, date, operative_clauses, text_evidence
from mezon.rules.procedure import is_budget_allocation
from research.regulation_window import entry_into_force
from research.textnorm import fold

MONEY = re.compile(r"\b(?:tolov\w*|yigim\w*|jarima\w*|tarif\w*|stavka\w*|badal\w*|ijara haqi|narx\w*)")
OBLIGATION = re.compile(r"\b(?:majburiy|majbur\w*|taqiqlan\w*|ruxsatnoma\w*|litsenziya\w*|talab qilinadi)")
BUSINESS = re.compile(
    r"\b(?:tadbirkor\w*|yuridik shaxs\w*|xojalik yurituvchi|savdo\w*|xizmat korsatuvchi|korxona\w*|biznes\w*"
    r"|mchj|dokon\w*|restoran\w*|umumiy ovqatlanish)"
)
SETS = re.compile(r"\b(?:belgilan\w*|tasdiqlan\w*|joriy etil\w*|undiril\w*|majbur\w*|taqiqlan\w*)")
THREE_MONTHS = re.compile(r"\b(?:3|uch) oy\w*")
# Titles of cited acts ("…tadbirkorlik subyektlari…to'g'risida") and tables glued onto a clause were the main sources
# of false burdens, so detection reads only the clause's own words, and only its head.
QUOTED = re.compile(r"[“\"«„][^”\"»“]{0,400}[”\"»“]")
CLAUSE_HEAD = 600
# Annual job quotas for vulnerable groups (VMQ No. 965) are 66 % of the high-confidence 3-month flags (82 of 125 on
# 19.11.2026). The quota is required by higher law and set every year, so whether NLA art. 40 applies is one open
# legal question for the whole group: they stay flagged, but as "needs expert" until a lawyer answers it once.
JOB_QUOTA = re.compile(r"ishga joylasht|ish orinlari\w* (?:eng kam|zaxira|kvota)|kvota|ehtiyojmand|ijtimoiy muhofazaga muhtoj")
# Local tax rates and coefficients: Tax Code art. 4 part 6 (same wording since 2020) puts a rate change in force from
# the first day of the month after publication, a special rule that likely displaces the NLA 3-month rule.
TAX_RATE = re.compile(r"yer solig|mol-mulk solig|soliq stavka|bazaviy soliq|koeffitsiyent")
TAX_NOTE = (
    " This sets local tax rates or coefficients. The Tax Code (art. 4 part 6) puts a change of tax rates in force from "
    "the first day of the month after official publication, a special rule that likely displaces NLA art. 40; an "
    "expert should confirm which applies."
)
QUOTA_NOTE = (
    " This is an annual job quota for vulnerable groups, which higher law (VMQ No. 965) requires the hokim to set "
    "each year; whether the 3-month rule applies to it is one question for an expert, answered once for all of them."
)


def burden(text: str) -> dict:
    f = fold(QUOTED.sub(" ", text[:CLAUSE_HEAD]))
    return {
        "money": bool(MONEY.search(f)),
        "obligation": bool(OBLIGATION.search(f)),
        "business": bool(BUSINESS.search(f)),
        "sets": bool(SETS.search(f)),
    }


def burden_clause(text: str) -> tuple[int, str, dict] | None:
    """The first operative clause that sets a money or obligation burden."""
    for n, clause in operative_clauses(text):
        b = burden(clause)
        if (b["money"] or b["obligation"]) and b["sets"]:
            return n, clause, b
    return None


def check(d: dict, law: SafeLaw | None = None) -> list:
    law = law or SafeLaw(None)
    text = d.get("text") or ""
    if not text:
        return []
    found = burden_clause(text)
    if not found:
        return []
    n, clause, b = found
    eif = entry_into_force(text)
    is_draft = d.get("role") == "draft"
    base = date(d.get("disc_end") if is_draft else (d.get("published") or d.get("adopted")))
    on = d.get("adopted") or d.get("disc_end") or ""
    flags = []
    burden_ev = text_evidence(d, f"clause {n}", clause)
    # Spending decisions ("budjetning qo'shimcha manbalari hisobidan mablag' yo'naltirish") rarely bind business, so a
    # money word in them is never enough for a high-confidence 3-month flag.
    explicit_business = b["business"] and not is_budget_allocation(d.get("title"))
    quota = bool(JOB_QUOTA.search(fold(d.get("title") or "")))
    tax_rate = bool(TAX_RATE.search(fold(d.get("title") or "")))
    if quota or tax_rate:
        explicit_business = False

    if eif["kind"] == "date" and base and eif["date"] < base and not is_draft:
        flags.append(
            Flag(
                check="R_retroactive",
                title="A burden takes effect before the decision was adopted",
                explanation=(
                    f"Clause {n} sets a burden, and the decision takes effect on {eif['date'].isoformat()}, "
                    f"before its adoption on {base.isoformat()}. Acts may not reach back in time when they "
                    "create or increase obligations (NLA art. 41)."
                ),
                severity="high",
                evidence=[burden_ev, text_evidence(d, "entry into force", eif["sentence"])],
                citations=[cite(law, "nla", "art:41/part:1", on, "orqaga")],
            )
        )

    # A decision that states no entry-into-force date is never flagged here, on purpose: NLA art. 40 part 1 gives
    # publication as the default only "agar hujjatlarning o'zida kechroq muddat ko'rsatilmagan bo'lsa", and part 2
    # itself puts a business burden in force no earlier than 3 months after publication. The law fills the silence,
    # so only a decision that STATES an earlier date conflicts with it (checked 19.11.2026, art. 40 unchanged since 2021).
    later_stated = bool(THREE_MONTHS.search(fold(eif["sentence"])))
    if tax_rate and not is_draft:
        # The more specific law governs: a tax-rate decision is checked against the Tax Code's own timing.
        flags.extend(_tax_timing(d, law, eif, base, on, burden_ev, n, later_stated))
        return flags

    soon = eif["kind"] == "relative" or (eif["kind"] == "date" and base and eif["date"] < add_months(base, 3))
    if soon and not later_stated:
        when = "on publication" if eif["kind"] == "relative" else eif["date"].isoformat()
        ref = "the end of public discussion" if is_draft else "adoption"
        flags.append(
            Flag(
                check="R_business_3m",
                title="A business burden takes effect in under 3 months",
                explanation=(
                    f"Clause {n} sets a burden ({'fees or payments' if b['money'] else 'obligations'}"
                    f"{' on business' if explicit_business else ''}), and the decision takes effect {when}, "
                    f"less than 3 months after {ref}. Acts that add obligations for entrepreneurs take effect "
                    "no earlier than 3 months after official publication (NLA art. 40)."
                    + (
                        QUOTA_NOTE
                        if quota
                        else TAX_NOTE
                        if tax_rate
                        else ""
                        if explicit_business
                        else " Whether it binds business is not explicit: an expert should confirm who pays."
                    )
                ),
                severity="high",
                status="possible_violation" if explicit_business else "unclear_needs_expert",
                evidence=[burden_ev, text_evidence(d, "entry into force", eif["sentence"])]
                if eif["sentence"]
                else [burden_ev],
                citations=[cite(law, "nla", "art:40/part:2", on, "uch oy")]
                + ([cite(law, "taxcode", "art:4/part:6", on, "oydan keyingi oyning birinchi")] if tax_rate else []),
                impact="business",
            )
        )
    return flags


def _first_of_next_month(day: dt.date) -> dt.date:
    return (day.replace(day=1) + dt.timedelta(days=32)).replace(day=1)


def _tax_timing(d, law, eif, base, on, burden_ev, n, later_stated) -> list:
    """Tax Code art. 4 part 6: a change of tax rates takes effect from the first day of the month after publication."""
    if not base or later_stated or eif["kind"] not in ("date", "relative"):
        return []
    effective = eif["date"] if eif["kind"] == "date" else base
    if effective < base:
        return []  # reaching back before adoption is R_retroactive's flag
    first = _first_of_next_month(base)
    if effective >= first:
        return []
    when = "on publication" if eif["kind"] == "relative" else effective.isoformat()
    return [
        Flag(
            check="R_tax_timing",
            title="A tax-rate change takes effect before the first day of the next month",
            explanation=(
                f"Clause {n} sets local tax rates or coefficients, and the decision takes effect {when} "
                f"(published or adopted {base.isoformat()}). The Tax Code puts a change of tax rates in force from "
                f"the first day of the month after official publication, here {first.isoformat()} (art. 4 part 6). "
                "Many districts use \"in force on publication\" for these decisions, so an expert should confirm."
            ),
            severity="medium",
            status="unclear_needs_expert",
            evidence=[burden_ev, text_evidence(d, "entry into force", eif["sentence"])],
            citations=[cite(law, "taxcode", "art:4/part:6", on, "oydan keyingi oyning birinchi")],
            impact="business",
        )
    ]
