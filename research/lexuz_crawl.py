"""Crawl lex.uz for local (hokim / Kengash) cancellation decisions: search titles, doc metadata, decision text."""

import html
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

from research.polite_http import CACHE, ROOT, WRITE_CACHE, fetch

BASE = "https://lex.uz"
INTERIM = ROOT / "data" / "interim"
TEXTS = CACHE / "lexuz" / "text"
LOCAL_RE = re.compile(r"hokim|kengash|ҳоким|кенгаш", re.IGNORECASE)
UI_NOISE = re.compile(r"Hujjatga taklif yuborish|Audioni tinglash|Hujjat elementidan havola olish")

PHRASES = [
    "qarorini bekor qilish",
    "farmoyishini bekor qilish",
    "qarorlarini bekor qilish",
    "bandini bekor qilish",
    "qismini bekor qilish",
    "oʻz kuchini yoʻqotgan deb hisoblash",
    "qarorini oʻz kuchini yoʻqotgan",
    "haqiqiy emas deb",
    "taqdimnomasi",
    "protesti",
    "eskirgan va oʻz ahamiyatini yoʻqotgan",
    "қарорини бекор қилиш",
    "фармойишини бекор қилиш",
    "қарорларини бекор қилиш",
]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _slug(s: str) -> str:
    return re.sub(r"\W+", "_", s).strip("_")[:60]


def _hidden(page: str, name: str) -> str:
    m = re.search(rf'id="{re.escape(name)}"[^>]*value="([^"]*)"', page) or re.search(
        rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', page
    )
    return html.unescape(m.group(1)) if m else ""


def parse_hits(page: str) -> list[dict]:
    hits = []
    for row in re.findall(r'<tr class="dd-table__main-item">(.*?)</tr>', page, re.DOTALL):
        a = re.search(r'class="lx_link\s*" href="/uz/docs/(-?\d+)"[^>]*>(.*?)</a>', row, re.DOTALL)
        if not a:
            continue
        badge = (
            _text(m.group(1))
            if (m := re.search(r'<span class="badge[^"]*">(.*?)</span>', row, re.DOTALL))
            else ""
        )
        date = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*(?:yildagi|йилдаги)", badge)
        num = re.search(r"(?:yildagi|йилдаги)\s+(.+?)-(?:son|сон)\b", badge)
        status = re.search(r"status_code_(\w+)", row)
        hits.append(
            {
                "id": a.group(1),
                "title": _text(a.group(2)),
                "badge": badge,
                "body": badge.split(",")[0].strip(),
                "date": date.group(1) if date else None,
                "number": num.group(1).strip() if num else None,
                "status": status.group(1) if status else None,
            }
        )
    return hits


def search(phrase: str, max_pages: int = 60) -> tuple[int, list[dict]]:
    return search_url(
        f"{BASE}/uz/search/all?searchtitle={quote(phrase)}", f"search/{_slug(phrase)}", max_pages
    )


def search_url(url: str, folder: str, max_pages: int = 60) -> tuple[int, list[dict]]:
    """All hits of one lex.uz search URL, paging with the page's own "Keyingisi" postback."""
    slug = folder
    page = fetch(url, "lexuz", key=f"{slug}/p1.html").decode("utf-8", "replace")
    total = int(m.group(1)) if (m := re.search(r"(\d[\d\s]*)\s*hujjat topildi", page)) else 0
    hits, seen = [], set()
    for n in range(1, max_pages + 1):
        new = [h for h in parse_hits(page) if h["id"] not in seen]
        if not new:
            break
        for h in new:
            seen.add(h["id"])
            hits.append(h)
        if len(seen) >= total or "ucFoundActsControl_LinkButton1" not in page:
            break
        data = {
            "__EVENTTARGET": "ucFoundActsControl$LinkButton1",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": _hidden(page, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": _hidden(page, "__VIEWSTATEGENERATOR"),
        }
        if _hidden(page, "__EVENTVALIDATION"):
            data["__EVENTVALIDATION"] = _hidden(page, "__EVENTVALIDATION")
        page = fetch(url, "lexuz", key=f"{slug}/p{n + 1}.html", data=data).decode("utf-8", "replace")
    return total, hits


def parse_doc(page: str) -> dict:
    flat = _text(re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page))
    header = re.search(
        r"([^|]{3,160}?(?:qarori|farmoyishi|qarorlari|қарори|фармойиши)\s*,\s*(\d{2}\.\d{2}\.\d{4})"
        r"\s*yildagi\s+(\S+?)-son)",
        flat,
    )
    entry = re.search(r"Kuchga kirish sanasi\s+(\d{2}\.\d{2}\.\d{4})", flat)
    lost = re.search(r"Hujjat kuchini yo.qotgan\s*(\d{2}\.\d{2}\.\d{4})", flat)
    title = re.search(r"<title>(.*?)</title>", page, re.DOTALL)
    sharhi = re.search(r'class="COMMENTLEXUZ">.*?</div>\s*<div[^>]*>(.*?)</div>', page, re.DOTALL)
    files = re.findall(r"/uz/files/(-?\d+)(\.zip)?", page)
    pdf_only = bool(re.search(r"matni\s+PDF\s+shakl\w*\s+berilgan", flat))
    inline = ""
    start = page.find('class="ACT_')
    if start != -1:
        end = page.find('class="FOOTNOTE', start)
        inline = UI_NOISE.sub(" ", _text(page[start - 5 : end if end != -1 else len(page)]))
        inline = re.sub(r'^class="[^"]*"[^>]*>', "", inline).strip()
    return {
        "header": header.group(1).split("TRANSLATE")[-1].strip() if header else None,
        "date": header.group(2) if header else None,
        "number": header.group(3) if header else None,
        "entry_into_force": entry.group(1) if entry else None,
        "lost_force": lost.group(1) if lost else None,
        "title": _text(title.group(1)).split(". ", 1)[-1].strip() if title else None,
        "sharhi": _text(sharhi.group(1)) if sharhi else None,
        "file_ids": [f for f, _ in files],
        "pdf_only": pdf_only,
        "inline_text": inline
        if len(inline) > 300 and not pdf_only and re.search(r"qaror qil|\b1\.\s", inline, re.IGNORECASE)
        else "",
    }


def _pdf_bytes_to_text(data: bytes, txt: Path) -> str:
    """pdftotext through a temporary PDF that is deleted again: only the .txt is kept (disk space)."""
    if not txt.exists() or txt.stat().st_size == 0:
        txt.parent.mkdir(parents=True, exist_ok=True)
        tmp = txt.with_suffix(".tmp.pdf")
        tmp.write_bytes(data)
        try:
            subprocess.run(
                ["pdftotext", "-enc", "UTF-8", "-layout", str(tmp), str(txt)],
                check=False,
                capture_output=True,
            )
        finally:
            tmp.unlink(missing_ok=True)
    return txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else ""


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return _text(re.sub(r"</w:p>", " ", xml))


def zip_text(doc_id: str, file_id: str) -> str:
    key, file_id = doc_id.lstrip("-"), file_id.lstrip("-")
    raw = fetch(f"{BASE}/uz/files/{file_id}.zip", "lexuz", key=f"zip/{key}/{file_id}.zip")
    old = CACHE / "lexuz" / "zip" / key
    folder = old if old.exists() else WRITE_CACHE / "lexuz" / "zip" / key
    if raw[:4] == b"%PDF":
        return _pdf_bytes_to_text(raw, folder / f"{file_id}.txt")
    if not raw or raw[:2] != b"PK":
        return ""
    texts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for i, name in enumerate(z.namelist()):
            suffix = Path(name).suffix.lower()
            if suffix == ".pdf":
                # ASCII names: the Windows pdftotext build cannot open paths with Cyrillic characters.
                legacy = folder / f"{Path(name).stem}.txt"
                txt = legacy if legacy.exists() and legacy.stat().st_size else folder / f"{file_id}_{i}.txt"
                texts.append(_pdf_bytes_to_text(z.read(name), txt))
            elif suffix == ".docx":
                texts.append(_docx_text(z.read(name)))
    return "\n".join(t for t in texts if t.strip())


def _text_path(doc_id: str) -> Path:
    name = f"{str(doc_id).lstrip('-')}.txt"
    old = TEXTS / name
    return old if old.exists() else WRITE_CACHE / "lexuz" / "text" / name


def fetch_doc(doc_id: str, twin: bool = True) -> dict:
    """Metadata + text for one lex.uz doc id (the sign marks the language version: Latin or Cyrillic)."""
    page = fetch(f"{BASE}/uz/docs/{doc_id}", "lexuz", key=f"docs/{doc_id.lstrip('-')}.html").decode(
        "utf-8", "replace"
    )
    meta = {"id": doc_id, "url": f"{BASE}/uz/docs/{doc_id}"}
    if not page:
        return meta | {"error": "404", "text_source": None}
    meta |= parse_doc(page)
    text_path = _text_path(doc_id)
    if text_path.exists() and text_path.stat().st_size > 0:
        text, source = text_path.read_text(encoding="utf-8"), "cached"
    elif meta["inline_text"]:
        text, source = meta["inline_text"], "html"
    else:
        text, source = "", None
        for fid in meta["file_ids"]:
            text = zip_text(doc_id, fid)
            if text.strip():
                source = "zip"
                break
    if not text.strip() and twin:
        other = fetch_doc(doc_id[1:] if doc_id.startswith("-") else f"-{doc_id}", twin=False)
        if other.get("text_source"):
            return meta | {
                "text_source": f"twin:{other['text_source']}",
                "text_chars": other["text_chars"],
                "text_path": other["text_path"],
            }
    if text.strip() and not text_path.exists():
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text, encoding="utf-8")
    meta.pop("inline_text")
    return meta | {
        "text_source": source,
        "text_chars": len(text),
        "text_path": str(text_path) if text else None,
    }


def load_text(doc_id: str) -> str:
    p = _text_path(doc_id)
    if p.exists() and p.stat().st_size:
        return p.read_text(encoding="utf-8")
    for folder in (CACHE / "lexuz" / "zip" / str(doc_id).lstrip("-"),):
        txts = sorted(folder.glob("*.txt")) if folder.exists() else []
        if txts:
            return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in txts)
    return ""


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    titles: dict[str, dict] = {}
    for phrase in PHRASES:
        total, hits = search(phrase)
        local = [h for h in hits if LOCAL_RE.search(h["body"])]
        print(f"{phrase!r}: total {total}, got {len(hits)}, local {len(local)}", flush=True)
        for h in local:
            # The id sign marks the language version of one act (Latin vs Cyrillic): keep one, prefer Latin.
            key = h["id"].lstrip("-")
            latin = not re.search(r"[Ѐ-ӿ]", h["badge"])
            cur = titles.get(key)
            if cur is None or (latin and not cur["latin"]):
                titles[key] = h | {"latin": latin, "phrases": (cur or {}).get("phrases", [])}
            titles[key]["phrases"].append(phrase)
    rows = list(titles.values())
    (INTERIM / "cancel_titles.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"unique local cancellation titles: {len(rows)}", flush=True)

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(rows)
    metas = []
    for i, h in enumerate(rows[:limit], 1):
        try:
            metas.append(fetch_doc(h["id"]))
        except RuntimeError as e:
            metas.append({"id": h["id"], "error": str(e), "text_source": None})
        if i % 25 == 0:
            print(f"  docs {i}/{limit}", flush=True)
    (INTERIM / "cancel_docs.json").write_text(
        json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    ok = sum(1 for m in metas if m.get("text_source"))
    print(f"texts extracted: {ok}/{len(metas)} = {ok / max(len(metas), 1):.1%}", flush=True)


if __name__ == "__main__":
    main()
