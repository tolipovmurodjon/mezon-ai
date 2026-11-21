"""Stage 10: training documents (headers, article-boundary chunks), change documents from the edition intervals, and
the lesson-input rows that research/law_school_data.py consumes (design sections 4c, 4d, 5; Boss's decision 1).

Tier A = latest edition in full; A0 = original edition in full when it differs (Jaccard < 0.97); tier B change
documents = one document per change date, listing every changed, inserted, removed, renumbered or moved unit and the
lex.uz note that says why (including "oz kuchini yoqotgan" and renumbering notes)."""

import itertools
import re
from collections import defaultdict

from research.mezonbench import human_path
from research.refinery import config
from research.refinery.extract_html import classify_note
from research.textnorm import fold, similarity

TUR = {
    "constitution": "konstitutsiya",
    "law": "qonun",
    "code": "kodeks",
    "chamber_resolution": "palata qarori",
    "pf": "Prezident farmoni",
    "pq": "Prezident qarori",
    "f": "Prezident farmoyishi",
    "vmq": "VMQ qarori",
    "ministry_order": "vazirlik hujjati",
    "local_hokim_qaror": "hokim qarori",
    "local_kengash_qaror": "Kengash qarori",
    "local_farmoyish": "hokim farmoyishi",
    "court": "sud hujjati",
    "other": "boshqa",
}
HOLAT = {
    "uz-Latn": {
        "in_force": "amalda",
        "lost_force": "kuchini yoʻqotgan",
        "not_yet_in_force": "kuchga kirmagan",
        "unknown": "nomaʼlum",
        "provisional": "oʻzgartirish kiritilmoqda",
        "original": "dastlabki tahrir",
    },
    "uz-Cyrl": {
        "in_force": "амалда",
        "lost_force": "кучини йўқотган",
        "not_yet_in_force": "кучга кирмаган",
        "unknown": "номаълум",
        "provisional": "ўзгартириш киритилмоқда",
        "original": "дастлабки таҳрир",
    },
    "ru": {
        "in_force": "действует",
        "lost_force": "утратил силу",
        "not_yet_in_force": "не вступил в силу",
        "unknown": "неизвестно",
        "provisional": "вносятся изменения",
        "original": "первоначальная редакция",
    },
    "en": {
        "in_force": "in force",
        "lost_force": "lost force",
        "not_yet_in_force": "not yet in force",
        "unknown": "unknown",
        "provisional": "amendment pending",
        "original": "original text",
    },
}


def lang_tag(lang: str, script: str) -> str:
    return {"uz": f"uz-{script}", "ru": "ru", "en": "en"}.get(lang, f"{lang}-{script}")


def header(
    meta: dict, lang: str, script: str, valid_from: str | None, valid_to: str | None, holat_key: str
) -> str:
    """[HUJJAT] <title> | tur | raqam | qabul | tahrir | holat | til | lex  (constant Latin labels, ISO dates)."""
    tag = lang_tag(lang, script)
    h = HOLAT.get(tag, HOLAT["uz-Latn"])
    holat = h.get(holat_key, holat_key)
    if holat_key == "lost_force" and meta.get("lost_force", {}) and meta["lost_force"].get("date"):
        holat += f" ({meta['lost_force']['date']})"
    tahrir = (
        (f"{valid_from} dan {valid_to} gacha" if valid_to else f"{valid_from} dan hozirgacha")
        if valid_from
        else "-"
    )
    return (
        f"[HUJJAT] {meta.get('title', '')} | tur: {TUR.get(meta['act_type'], 'boshqa')} | "
        f"raqam: {meta.get('number') or '-'} | qabul: {meta.get('adopted') or '-'} | tahrir: {tahrir} | "
        f"holat: {holat} | til: {tag} | lex: {meta['abs_id']}"
    )


def chunk_by_article(blocks: list[dict], hdr: str, max_words: int = config.MAX_CHUNK_WORDS) -> list[dict]:
    """Split at article boundaries (a block of kind 'article' starts a unit); never mid-article unless one article
    alone exceeds the limit (then at block boundaries). The header repeats on every chunk; the current chapter
    heading is carried as a second line."""
    groups: list[list[dict]] = []
    for b in blocks:
        if b["kind"] in {"article", "heading", "annex"} or not groups:
            groups.append([b])
        else:
            groups[-1].append(b)
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    words = 0
    for g in groups:
        gw = sum(len(b["text"].split()) for b in g)
        if gw > max_words:
            if cur:
                chunks.append(cur)
                cur, words = [], 0
            part: list[dict] = []
            pw = 0
            for b in g:
                bw = len(b["text"].split())
                if part and pw + bw > max_words:
                    chunks.append(part)
                    part, pw = [], 0
                part.append(b)
                pw += bw
            if part:
                chunks.append(part)
            continue
        if cur and words + gw > max_words:
            chunks.append(cur)
            cur, words = [], 0
        cur.extend(g)
        words += gw
    if cur:
        chunks.append(cur)
    out, chapter = [], ""
    for i, ch in enumerate(chunks):
        body = _join(ch)
        lines = [hdr]
        if i > 0 and chapter and not (ch and ch[0]["kind"] == "heading"):
            lines.append(chapter)
        lines.append(body)
        out.append(
            {"chunk": i, "text": "\n".join(lines), "header_chars": len(hdr), "n_words": len(body.split())}
        )
        for b in ch:
            if b["kind"] == "heading":
                chapter = b["text"]
    return out


def _join(blocks: list[dict]) -> str:
    out: list[str] = []
    for b in blocks:
        if b["kind"] in {"article", "heading", "annex"} and out and out[-1] != "":
            out.append("")
        out.append(b["text"])
    return "\n".join(out).strip()


def original_differs(latest_text: str, original_text: str) -> tuple[bool, float]:
    s = similarity(latest_text[:20000], original_text[:20000])
    return s < config.A0_SIMILARITY, round(s, 4)


def _cap(t: str, n: int = 1500) -> str:
    t = t.strip()
    return t if len(t) <= n else t[:n].rstrip() + " ..."


def change_events(rows: list[dict]) -> dict[str, list[dict]]:
    """Group unit-interval rows into change events per edition start date. Events: changed, inserted, removed,
    and (by identical text under another path on the same date) moved/renumbered."""
    by_path: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("is_container"):
            continue
        by_path[r["path"]].append(r)
    first_from = min((r["valid_from"] for r in rows), default=None)
    events: dict[str, list[dict]] = defaultdict(list)
    for path, rs in by_path.items():
        rs = sorted(rs, key=lambda r: (r["valid_from"], r["seq_from"]))
        for prev, nxt in itertools.pairwise(rs):
            if prev["valid_to"] == nxt["valid_from"] or prev["seq_to"] + 1 == nxt["seq_from"]:
                events[nxt["valid_from"]].append(
                    {"type": "changed", "path": path, "before": prev, "after": nxt}
                )
            else:
                events[nxt["valid_from"]].append(
                    {
                        "type": "inserted",
                        "path": path,
                        "before": None,
                        "after": nxt,
                        "gap_from": prev["valid_to"],
                    }
                )
        head, tail = rs[0], rs[-1]
        if first_from and head["valid_from"] > first_from and head["seq_from"] > 0:
            events[head["valid_from"]].append(
                {"type": "inserted", "path": path, "before": None, "after": head}
            )
        if tail["valid_to"]:
            events[tail["valid_to"]].append({"type": "removed", "path": path, "before": tail, "after": None})
    for evs in events.values():
        ins = [e for e in evs if e["type"] == "inserted"]
        rem = [e for e in evs if e["type"] == "removed"]
        if not ins or not rem:
            continue
        idx = defaultdict(list)
        for e in ins:
            idx[fold(e["after"]["text"])].append(e)
        small = len(ins) <= 25 and len(rem) <= 25
        for r in rem:
            ft = fold(r["before"]["text"])
            match = idx.get(ft, [None])[0] if len(ft) > 40 else None
            if match is None and small and len(ft) > 40:
                match = next(
                    (e for e in ins if similarity(r["before"]["text"], e["after"]["text"]) >= 0.9), None
                )
            if match is not None and match["path"] != r["path"]:
                r["type"] = "moved"
                r["to_path"] = match["path"]
                match["type"] = "moved_in"
                match["from_path"] = r["path"]
    return events


def _fix_note(text: str) -> str:
    """The store keeps notes as plain page text, where a superscript becomes a separate word ('25 1 -modda'):
    put the hyphen back ('25-1-modda')."""
    return re.sub(r"(\d+)\s+(\d+)\s+-(modda|band|bob|ilova)", r"\1-\2-\3", text)


def amendment_docs(
    meta: dict, rows: list[dict], lang: str, script: str, cutoff: str = config.TIME_CUT
) -> list[dict]:
    """Tier B change documents, one per change date (chunked at entry boundaries), never for dates on or after the
    time cut. One entry per changed unit: changed, inserted, removed or lost force, or moved/renumbered."""
    events = change_events(rows)
    out = []
    for date in sorted(events):
        if date >= cutoff:
            continue
        head = (
            f"[OʻZGARISH] {meta.get('title', '')} | lex: {meta['abs_id']} | sana: {date} | "
            f"til: {lang_tag(lang, script)}"
        )
        entries: list[str] = []
        for e in sorted(events[date], key=lambda e: e["path"]):
            if e["type"] == "moved_in":
                continue  # described once, at the old path
            after, before = e.get("after"), e.get("before")
            where = human_path(e["path"])
            notes = [n for n in (after or before or {}).get("notes", "").split("\n") if n.strip()]
            asos = _fix_note(" | ".join(notes[:3]))
            why = f" Asos: {asos}" if asos else ""
            kinds = {classify_note(n)["kind"] for n in notes}
            if e["type"] == "moved":
                entries.append(
                    f"{where}: {human_path(e['to_path'])} ga koʻchirilgan yoki qayta raqamlangan ({date} dan)."
                    + why
                )
            elif (
                e["type"] == "removed"
                or "lost_force" in kinds
                or (e["type"] == "changed" and not (after["text"] or "").strip())
            ):
                old = (
                    f" Oldingi matn ({before['valid_from']} dan {date} gacha): {_cap(before['text'])}"
                    if before
                    else ""
                )
                entries.append(f"{where}: {date} dan kuchini yoʻqotgan yoki chiqarilgan." + old + why)
            else:
                label = "yangi kiritilgan" if e["type"] == "inserted" else "oʻzgartirilgan"
                lines = [f"{where}: {label} ({date} dan)." + why]
                if before:
                    lines.append(
                        f"Oldin ({before['valid_from']} dan {before['valid_to']} gacha): {_cap(before['text'])}"
                    )
                to = f" {after['valid_to']} gacha" if after["valid_to"] else ""
                lines.append(f"Keyin ({after['valid_from']} dan{to}): {_cap(after['text'])}")
                entries.append("\n".join(lines))
        chunk: list[str] = []
        words, part = 0, 0
        for ent in entries:
            w = len(ent.split())
            if chunk and words + w > config.MAX_CHUNK_WORDS:
                out.append({"date": date, "part": part, "text": "\n".join([head, *chunk]), "n_words": words})
                chunk, words, part = [], 0, part + 1
            chunk.append(ent)
            words += w
        if chunk:
            out.append({"date": date, "part": part, "text": "\n".join([head, *chunk]), "n_words": words})
    return out


def status_doc(meta: dict, lang: str, script: str) -> dict | None:
    """One short document saying when and why an act lost force (from the page warning, the card, LexUZ sharhi)."""
    lf = meta.get("lost_force")
    if meta.get("status") != "lost_force" or not lf:
        return None
    why = re.sub(r"\s+", " ", " ".join(lf.get("cancelled_by_text") or []) or lf.get("card_reason") or "")
    text = (
        f"[HOLAT] {meta.get('title', '')} | lex: {meta['abs_id']} | til: {lang_tag(lang, script)}\n"
        f"Hujjat {lf.get('date') or '(sana nomaʼlum)'} dan kuchini yoʻqotgan."
        + (f" Asos: {why}" if why else "")
    )
    return {"text": text, "n_words": len(text.split())}


LESSON_TYPE = {
    "constitution": "constitution",
    "law": "law",
    "code": "code",
    "pf": "pf",
    "pq": "pq",
    "vmq": "vmq",
    "ministry_order": "ministry",
    "local_hokim_qaror": "local_hokim",
    "local_kengash_qaror": "local_kengash",
    "local_farmoyish": "local_hokim",
    "court": "court",
    "f": "f",
    "chamber_resolution": "chamber",
    "other": "other",
}


def lesson_inputs(
    meta: dict, rows: list[dict], act_key: str, blocklist: set[str], cutoff: str = config.TIME_CUT
) -> list[dict]:
    """Rows with the columns lesson() reads (act_key, path, heading, text, valid_from, valid_to) plus act_type, title,
    number and prev_text. Never container rows, never blocklisted units, never intervals starting on/after the cut."""
    by_path: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_path[r["path"]].append(r)
    out = []
    for path in sorted(by_path):
        prev = None
        for r in sorted(by_path[path], key=lambda r: (r["valid_from"], r["seq_from"])):
            p, prev = prev, r
            if r.get("is_container") or len(r["text"]) < 80 or r["valid_from"] >= cutoff:
                continue
            if path in blocklist or path.split("/part:")[0] in blocklist:
                continue
            out.append(
                {
                    "act_key": act_key,
                    "path": path,
                    "heading": r["heading"],
                    "text": r["text"],
                    "valid_from": r["valid_from"],
                    "valid_to": r["valid_to"],
                    "act_type": meta["act_type"],
                    "type": LESSON_TYPE.get(meta["act_type"], "other"),
                    "title": meta.get("title", ""),
                    "number": meta.get("number", ""),
                    "prev_text": p["text"] if p else None,
                    "lex_id": meta["lex_id"],
                }
            )
    return out
