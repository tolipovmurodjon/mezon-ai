"""Stage 01 worker: one task (a lex id, or an OCR key) -> one extraction record. Pure reads from the cache."""

import hashlib
import re
from dataclasses import asdict
from pathlib import Path

from mezon.lawstore.parse import parse_units
from mezon.lawstore.store import iso
from research.refinery import config
from research.refinery import sources as src
from research.refinery.extract_html import assemble_text, card1_status, fallback_text, unit_versions
from research.refinery.extract_ocr import extract_ocr
from research.refinery.extract_pdf import doc_text, extract_pdf
from research.refinery.meta import build_meta

CATALOG: src.Catalog | None = None  # set by the parent before forking workers
VOCAB: set[str] | None = None


def _blocks(act) -> list[dict]:
    return [asdict(b) for b in act.blocks]


def pages_for_units(
    current: str, editions: list[tuple[str, Path]], cut: bool = False
) -> list[tuple[str, str, bool]]:
    """[(ondate, page, provisional)] oldest first. The current page stands in for the last edition (as the store
    does) unless a time cut removed newer editions: then the last kept edition is read from its own file."""
    from mezon.lawstore.fetch import has_pending_banner

    out = []
    for i, (d, p) in enumerate(editions):
        last = i == len(editions) - 1
        page = current if (last and not cut) else p.read_bytes().decode("utf-8", "replace")
        out.append((d, page, bool(has_pending_banner(page)) if last else False))
    return out


def edition_rows(
    lex_id: str,
    current: str,
    doc_page_for_script: str | None,
    root: Path | None = None,
    cutoff: str | None = None,
    ed_files=None,
    default_ondate: str = "01.01.1900 00",
) -> tuple[list[dict], list[dict], list[tuple]]:
    """(unit_versions rows, editions summary, kept [(ondate, page, provisional)]). Editions on/after the time cut
    are left out; with no edition files the current page is the only edition."""
    files = ed_files if ed_files is not None else src.edition_files(lex_id, doc_page_for_script, root)
    cut = False
    if cutoff:
        kept = [(d, p) for d, p in files if iso(d) < cutoff]
        cut = len(kept) < len(files)
        files = kept
    pages = pages_for_units(current, files, cut) if files else []
    if not pages:
        pages = [(default_ondate, current, False)]
    parsed = [(d, parse_units(pg), prov) for d, pg, prov in pages]
    rows = unit_versions(parsed)
    starts = [iso(d) for d, _, _ in parsed]
    eds = [
        {
            "ondate": d,
            "valid_from": starts[i],
            "valid_to": starts[i + 1] if i + 1 < len(starts) else None,
            "provisional": prov,
            "n_units": len(u),
        }
        for i, (d, u, prov) in enumerate(parsed)
    ]
    return rows, eds, pages


def extract_task(task: dict) -> dict:
    """Dispatch on task['kind']: html (national acts and local decision pages, PDF through the page's file link) or ocr."""
    cat = CATALOG or src.Catalog()
    if task["kind"] == "ocr":
        return _extract_ocr_task(task, cat)
    lex_id = task["lex_id"]
    c = cat.get(lex_id)
    rec: dict = {
        "lex_id": lex_id,
        "stratum": task["stratum"],
        "task": {k: v for k, v in task.items() if k != "pop"},
    }
    page, key = src.doc_page(lex_id, cat.expect_script(lex_id))
    if page is None:
        rec["error"] = "no_page"
        return rec
    rec["source_keys"] = [key]
    rec["sha1_raw"] = hashlib.sha1(page.encode()).hexdigest()
    act = assemble_text(page)
    card_page = src.panel(lex_id, "card1")
    card = card1_status(card_page) if card_page else None
    rec["cites"] = src.panel_ids(src.panel(lex_id, "correspondents"))[:200]
    rec["cited_by_n"] = len(src.panel_ids(src.panel(lex_id, "respondents")))
    rec["notes"] = [asdict(n) for n in act.notes]
    rec["n_table_chars"], rec["table_numeric_share"] = act.n_table_chars, act.table_numeric_share
    pdf_text = None
    if act.meta.get("pdf_only") or (not act.blocks and src.file_ids(page)):
        fids = [f for f in src.file_ids(page)]
        for fid in fids:
            for ext in ("zip", "pdf"):
                p = config.CACHE / "files" / f"{fid}.{ext}"
                if p.exists() and p.stat().st_size:
                    res = extract_pdf(p, fid, VOCAB)
                    rec["source_keys"].append(f"files/{fid}.{ext}")
                    if res and not res[0].scanned and res[0].text:
                        pdf_text = res[0]
                    elif res and res[0].scanned:
                        o = extract_ocr(res[0].key)
                        rec["scanned"] = True
                        if o is not None:
                            rec["ocr"] = {
                                "key": o.key,
                                "pages": o.pages,
                                "failed_pages": o.failed_pages,
                                "partial": o.ocr_partial,
                            }
                            rec["source_keys"].append(f"ocr/{o.key}.md")
                            pdf_text = o
                    break
            if pdf_text is not None:
                break
        if pdf_text is None:  # Word / RTF attachments, converted earlier by research.doc_text_all
            for fid in fids:
                dt = doc_text(fid)
                if dt is not None:
                    rec["source_keys"].append(f"doctext/{fid}")
                    rec["doc_text"] = True
                    pdf_text = dt
                    break
    head = pdf_text.text[:1500] if pdf_text is not None else ""
    rec["meta"] = build_meta(lex_id, c, act, card, head)
    if pdf_text is not None:
        is_ocr = hasattr(pdf_text, "ocr_partial")
        rec["source_kind"] = "ocr" if is_ocr else "pdf_text"
        rec["blocks"] = [
            {"kind": u.get("kind", "text"), "text": u["text"], "path": u["path"], "art": None, "eid": ""}
            for u in pdf_text.units
        ]
        rec["ocr_partial"] = bool(getattr(pdf_text, "ocr_partial", False))
        rec["pdf_pages"] = getattr(pdf_text, "pages", 0)
        rec["n_table_lines"] = getattr(pdf_text, "n_table_lines", 0)
        rec["editions"], rec["unit_rows"], rec["original"] = [], [], None
        return rec
    if act.blocks and sum(len(b.text) for b in act.blocks) > 0:
        rec["source_kind"] = "html"
        adopted = rec["meta"]["adopted"]
        dflt = f"{adopted[8:10]}.{adopted[5:7]}.{adopted[:4]} 00" if adopted else "01.01.1900 00"
        rows, eds, pages = edition_rows(lex_id, page, page, cutoff=config.TIME_CUT, default_ondate=dflt)
        rec["editions"], rec["unit_rows"] = eds, rows
        latest = pages[-1][1]
        rec["blocks"] = _blocks(act if latest is page else assemble_text(latest))
        rec["original"] = None
        if len(pages) > 1:
            first = assemble_text(pages[0][1])
            rec["original"] = {
                "ondate": pages[0][0],
                "valid_from": iso(pages[0][0]),
                "valid_to": iso(pages[1][0]),
                "blocks": _blocks(first),
            }
        return rec
    fb = fallback_text(page)
    rec["source_kind"] = "html_fallback" if len(fb) >= config.MIN_CHARS else "no_text"
    rec["blocks"] = [
        {"kind": "text", "text": ln, "path": None, "art": None, "eid": ""} for ln in fb.splitlines()
    ]
    rec["editions"], rec["unit_rows"], rec["original"] = [], [], None
    return rec


def find_doc_for_file(fid: str) -> str | None:
    """Doc id whose page links `/uz/files/<fid>.zip`: doc ids sit within a few dozen of the file id."""
    n = int(fid.split("__")[0])
    for d in sorted(range(-40, 41), key=abs):
        for sign in ("m", "p"):
            page = src.read_cache(f"docs/{n + d}_{sign}.html")
            if page and f"/uz/files/{n}." in page:
                return f"-{n + d}" if sign == "m" else str(n + d)
    return None


def _extract_ocr_task(task: dict, cat: src.Catalog) -> dict:
    key = task["key"]
    rec: dict = {"lex_id": task["lex_id"], "stratum": "ocr", "task": task, "source_keys": [f"ocr/{key}.md"]}
    o = extract_ocr(key, vocab=VOCAB)
    if o is None:
        rec["error"] = "ocr_missing"
        return rec
    lex_id = find_doc_for_file(key)
    rec["doc_lex_id"] = lex_id
    c = cat.get(lex_id) if lex_id else {}
    page, _ = src.doc_page(lex_id, cat.expect_script(lex_id)) if lex_id else (None, "")
    act = assemble_text(page) if page else None
    rec["meta"] = build_meta(lex_id or re.sub(r"\D", "", key.split("__")[0]), c, act, None, o.text[:1500])
    rec["source_kind"] = "ocr"
    rec["ocr"] = {"key": key, "pages": o.pages, "failed_pages": o.failed_pages, "partial": o.ocr_partial}
    rec["ocr_partial"] = o.ocr_partial
    rec["blocks"] = [
        {"kind": u.get("kind", "text"), "text": u["text"], "path": u["path"], "art": None, "eid": ""}
        for u in o.units
    ]
    rec["editions"], rec["unit_rows"], rec["original"], rec["notes"] = [], [], None, []
    rec["n_table_chars"], rec["table_numeric_share"], rec["cites"], rec["cited_by_n"] = 0, 0.0, [], 0
    return rec
