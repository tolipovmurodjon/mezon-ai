"""Stage 04: one metadata row per act (schema 4a): type, level, number, dates, status, lost-force, topics."""

import re

from mezon.lawstore.store import iso
from research import regnum
from research.refinery.extract_html import ActText, title_parts
from research.textnorm import fold

# folded badge / title patterns -> act type (order matters)
_TYPES = [
    ("constitution", re.compile(r"konstitutsiyasi$|konstitutsiya$|konstitutsiyasi\b(?!.*sud)")),
    ("court", re.compile(r"sudining|sudi\b|konstitutsiyaviy sud|konstitutsionnogo suda|verxovnogo suda")),
    ("code", re.compile(r"kodeks|kodeksi")),
    ("pf", re.compile(r"prezidentining farmoni|farmoni\b|ukaz\b")),
    ("pq", re.compile(r"prezidentining qarori|prezidentining qarori|postanovlenie prezidenta")),
    ("f", re.compile(r"prezidentining farmoyishi|rasporyazhenie prezidenta")),
    ("vmq", re.compile(r"vazirlar mahkamasining|kabineta ministrov|vazirlar mahkamasi qarori")),
    ("chamber_resolution", re.compile(r"senatining|qonunchilik palatasining|oliy majlis")),
    ("law", re.compile(r"qonuni$|qonuni\b|zakon\b|\bqonun\b")),
    (
        "ministry_order",
        re.compile(
            r"vazirligi|vazirining|buyrugi|qomitasi|komitet|agentligi|ministerstv|byuro|"
            r"markaziy bank|boshqarmasi|inspeksiyasi"
        ),
    ),
]
_REG_FIND = re.compile(
    r"[IVX]{1,4}-\d{1,3}-\d{1,4}-\d{1,2}-\d{1,3}-K/\d{2}|\d{1,4}-\d{1,2}-\d{1,3}-[QF]/\d{2}|"
    r"\d{1,4}-\d{1,2}-\d{1,3}/[QF]"
)


def act_type(badge: str, title: str, number: str) -> tuple[str, str]:
    """(act_type, level). Local types come from the registration number letter (Q, K, F) via regnum."""
    reg = reg_number(number) or reg_number(badge) or reg_number(title)
    if reg:
        p = regnum.parse(reg)
        if p:
            return {"Q": "local_hokim_qaror", "F": "local_farmoyish", "K": "local_kengash_qaror"}[
                p["type"]
            ], "local"
    f = fold(badge or title)
    if re.search(r"tumani|shahri|viloyati|nohiyasi|hokimining|kengashining|kengashi\b", f) and re.search(
        r"hokim|kengash", f
    ):
        if "farmoyish" in f:
            return "local_farmoyish", "local"
        return ("local_kengash_qaror" if "kengash" in f else "local_hokim_qaror"), "local"
    if re.search(r"konstitutsiyasi\b", f) and "sud" not in f:
        return "constitution", "national"
    for t, rx in _TYPES:
        if rx.search(f):
            return t, "national"
    return "other", "national"


def reg_number(text: str) -> str | None:
    m = _REG_FIND.search(text or "")
    return m.group(0) if m else None


def build_meta(lex_id: str, cat: dict, act: ActText | None, card: dict | None, pdf_head: str = "") -> dict:
    """One acts.parquet row (as a dict). Sources: catalog (lang, badge, number), page title, page warnings,
    the legal analysis card, and (for PDF decisions) the PDF head."""
    t = title_parts(act.title if act else "")
    number = cat.get("number") or t["number"]
    badge = cat.get("badge", "")
    atype, level = act_type(badge, t["name"] or cat.get("title", ""), number or "")
    adopted = t["adopted"] or (iso(cat["adopted"]) if cat.get("adopted") else None)
    m = act.meta if act else {}
    status = m.get("status", "unknown")
    lost_on = m.get("lost_force_on")
    if card:
        if card.get("card_lost_force") and not lost_on:
            lost_on = card["card_lost_force"]
        if status == "unknown" and re.search(
            r"Утратил|Не действ|Отмен", card.get("card_status", ""), re.IGNORECASE
        ):
            status = "lost_force"
        elif status == "unknown" and re.search(r"Действ", card.get("card_status", ""), re.IGNORECASE):
            status = "in_force"
    if status == "unknown":
        status = {"y": "in_force", "r": "lost_force", "n": "not_yet_in_force"}.get(
            cat.get("status", ""), "unknown"
        )
    cancelled_by = [
        n.text for n in (act.notes if act else []) if n.source == "lexuz_sharhi" and n.kind == "lost_force"
    ]
    reg_a, reg_b = reg_number(number or ""), reg_number(pdf_head)
    return {
        "lex_id": lex_id,
        "abs_id": int(lex_id.lstrip("-")),
        "act_type": atype,
        "level": level,
        "number": number,
        "reg_number": reg_a or reg_b,
        "title": t["name"] or cat.get("title", ""),
        "body": m.get("body") or cat.get("body", ""),
        "adopted": adopted,
        "status": status,
        "lost_force": {
            "date": lost_on,
            "cancelled_by_text": cancelled_by[:2],
            "card_reason": (card or {}).get("card_reason", ""),
        }
        if status == "lost_force"
        else None,
        "in_force_from": (card or {}).get("card_in_force_from"),
        "provisional": bool(m.get("provisional")),
        "topics": m.get("topics", []),
        "registration": m.get("registration", ""),
        "catalog_lang": cat.get("lang", ""),
        "catalog_title": cat.get("title", ""),
        "meta_conflict": bool(reg_a and reg_b and reg_a != reg_b),
        "pdf_only": bool(m.get("pdf_only")),
        "pending_act": m.get("pending_act"),
        "source_url": f"https://lex.uz/uz/docs/{lex_id}",
    }
