"""Duplicates in force at once and repeals of already repealed acts (reuses research/duplicates.py)."""

import re

from mezon.report import Evidence, Flag
from mezon.rules.common import SafeLaw, cite, clip, operative_clauses, text_evidence
from research import duplicates
from research.textnorm import fold, similarity

_CACHE: dict[tuple, list[dict]] = {}


def _ddmmyyyy(iso: str | None) -> str | None:
    if not iso:
        return None
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def _group_flags(decisions, region, district, typ) -> list[dict]:
    key = (id(decisions), region, district, typ)
    if key not in _CACHE:
        docs = [
            {
                "id": r["src_id"],
                "number": r["reg_number"],
                "date": _ddmmyyyy(r["adopted"]),
                "lost_force": _ddmmyyyy(r["lost_force"]),
                "url": r["url"],
            }
            for r in decisions.same_body(region, district, typ)
            if r["reg_number"] and r["adopted"]
        ]
        _CACHE[key] = duplicates.analyse(docs)
    return _CACHE[key]


def _first_clause(text: str) -> str:
    cl = operative_clauses(text)
    return cl[0][1] if cl else ""


def _repeal_sentence(text: str, number: str) -> str:
    from research.textnorm import normalize

    for s in normalize(text).replace(";", ".").split(". "):
        if number in s and duplicates.REPEAL_VERB.search(s):
            return s
    return ""


# Successive budget reports, amendments and seasonal limits share a template title at 0.69-0.82; true copies are 1.0.
TITLE_SIM = 0.9
_CLEANUP_TITLE = re.compile(r"eskirgan|a[hx]amiyatini yoqotgan|kuchini yoqotgan deb|bekor qilish")
_NUMBER = re.compile(r"\d+")


def _same_matter(d: dict, older: dict) -> bool:
    """Two acts govern the same matter: similar titles that carry the same numbers (period, year, object), and neither
    is a clean-up or cancelling decision, whose texts look alike by template."""
    a, b = fold(d.get("title") or ""), fold(older.get("title") or "")
    if _CLEANUP_TITLE.search(a) or _CLEANUP_TITLE.search(b):
        return False
    return set(_NUMBER.findall(a)) == set(_NUMBER.findall(b)) and similarity(a, b) >= TITLE_SIM


def check(d: dict, law: SafeLaw, decisions) -> list:
    if d.get("source") != "lex.uz" or not d.get("text") or not d.get("reg_number") or decisions is None:
        return []
    out = []
    for f in _group_flags(decisions, d["region"], d["district"], d["type"]):
        if f["newer_number"] != d["reg_number"]:
            continue
        older_ids = decisions.by_reg(f["older_number"])
        older = decisions.get(older_ids[0]) if older_ids else None
        if not older:
            continue
        on = d["adopted"]
        if f["repealed_number"]:
            x = f["repealed_number"]
            out.append(
                Flag(
                    check="R_double_repeal",
                    title=f"Repeals {x}, which was already repealed",
                    explanation=(
                        f"This decision declares {x} void, but {older['reg_number']} ({older['adopted']}) had "
                        "already done so. Amendments and repeals of other decisions must be correct "
                        "(order 3333 ¶51); a double repeal shows the drafter didn't check the act's status."
                    ),
                    severity="medium",
                    evidence=[
                        text_evidence(d, "repeal clause", _repeal_sentence(d["text"], x)),
                        Evidence(
                            "related_decision",
                            older["id"],
                            clip(_repeal_sentence(older["text"], x)),
                            older["url"],
                        ),
                    ],
                    citations=[cite(law, "o3333", "annex:1/cl:51", on, "kuchini")],
                )
            )
        elif _same_matter(d, older):
            out.append(
                Flag(
                    check="R_duplicate",
                    title=f"Near-copy of {older['reg_number']}, which is still in force",
                    explanation=(
                        f"The operative clauses match {older['reg_number']} ({older['adopted']}) at "
                        f"{f['operative_sim']} (annex {f['annex_bag_sim'] or 'n/a'}), and the older decision "
                        "wasn't repealed, so two acts govern the same matter. A body adopting a new act must "
                        "amend or repeal its conflicting older acts (NLA art. 46)."
                    ),
                    severity="high",
                    evidence=[
                        text_evidence(d, "clause 1", _first_clause(d["text"])),
                        Evidence(
                            "related_decision", older["id"], clip(_first_clause(older["text"])), older["url"]
                        ),
                    ],
                    citations=[cite(law, "nla", "art:46/part:1", on)],
                )
            )
    return out
