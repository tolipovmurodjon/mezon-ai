"""Read-only access to the crawl cache, the crawl catalog and the OCR folder. Nothing here touches the network.

Cache names: docs/{abs}_{p|m}.html (`_p` = id x, `_m` = id -x), editions/{abs}_{p|m}/{dd.mm.yyyy}_{NN}.html,
actinfo/{panel}/{abs}_{p|m}.html, files/{fileid}.zip. Until 20 Nov 2026 some names carried no sign, so x and -x
shared a file; such a legacy file is used only when its script agrees with the page it should belong to."""

import re
import sqlite3
from pathlib import Path

from mezon.lawstore.store import iso
from research.refinery import config
from research.refinery.normalize import script_share

_EXPECT_SCRIPT = {"uz_latn": "Latn", "uz_cyrl": "Cyrl", "ru": "Cyrl", "en": "Latn"}


def split_id(lex_id: str) -> tuple[str, str]:
    """('6986157', 'm') for '-6986157'."""
    return lex_id.lstrip("-"), "m" if lex_id.startswith("-") else "p"


def twin_of(lex_id: str) -> str:
    return lex_id[1:] if lex_id.startswith("-") else "-" + lex_id


def read_cache(rel: str, root: Path | None = None) -> str | None:
    p = (root or config.CACHE) / rel
    try:
        data = p.read_bytes()
    except OSError:
        return None
    return data.decode("utf-8", "replace") if data else None


def visible_script(page: str) -> str:
    """'Latn' or 'Cyrl' by the letters of the main container (page chrome and scripts removed)."""
    i = page.find("main_container1")
    body = page[i:] if i >= 0 else page
    body = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", body, flags=re.DOTALL | re.IGNORECASE)
    lat, cyr = script_share(body)
    return "Cyrl" if cyr > lat else "Latn"


def script_share_cyr(page: str) -> float:
    i = page.find("main_container1")
    body = page[i:] if i >= 0 else page
    body = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", body, flags=re.DOTALL | re.IGNORECASE)
    return script_share(body)[1]


def doc_page(lex_id: str, expect: str | None = None, root: Path | None = None) -> tuple[str | None, str]:
    """(page, cache key). A legacy unsigned file is accepted only if its script matches `expect` (Latn/Cyrl)."""
    a, s = split_id(lex_id)
    key = f"docs/{a}_{s}.html"
    page = read_cache(key, root)
    if page:
        return page, key
    legacy = read_cache(f"docs/{a}.html", root)
    if legacy and (expect is None or visible_script(legacy) == expect):
        return legacy, f"docs/{a}.html"
    return None, key


def edition_files(lex_id: str, doc: str | None, root: Path | None = None) -> list[tuple[str, Path]]:
    """[(ondate 'dd.mm.yyyy NN', path)] in time order. The sign-keyed folder is preferred; a legacy folder is used
    only when the script share of an edition is within 0.2 of the act's own page (design finding 5)."""
    a, s = split_id(lex_id)
    base = (root or config.CACHE) / "editions"
    folders = [base / f"{a}_{s}"]
    if not folders[0].is_dir():
        folders = [base / a]
    out = []
    ref = script_share_cyr(doc) if doc else None
    for f in folders:
        if not f.is_dir():
            continue
        legacy = f.name == a
        for p in sorted(f.glob("*.html")):
            m = re.match(r"^(\d{2}\.\d{2}\.\d{4})_(\d{2})\.html$", p.name)
            if not m or p.stat().st_size == 0:
                continue
            if legacy and ref is not None:
                page = p.read_bytes()[:400000].decode("utf-8", "replace")
                if abs(script_share_cyr(page) - ref) > 0.2:
                    continue
            out.append((f"{m[1]} {m[2]}", p))
    return sorted(out, key=lambda t: (iso(t[0]), t[0]))


def file_ids(page: str) -> list[str]:
    return sorted(set(re.findall(r"/uz/files/(\d+)\.(?:zip|pdf)", page)))


def panel(lex_id: str, name: str, root: Path | None = None) -> str | None:
    a, s = split_id(lex_id)
    return read_cache(f"actinfo/{name}/{a}_{s}.html", root)


def panel_ids(page: str | None) -> list[str]:
    if not page:
        return []
    return sorted(set(re.findall(r'href="/uz/docs/(-?\d+)"', page)))


class Catalog:
    """Crawl catalog (state.sqlite): lex_id -> lang, title, badge, body, adopted, number, status. Optional."""

    def __init__(self, path: Path = config.STATE_DB):
        self.rows: dict[str, dict] = {}
        if Path(path).exists():
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            for r in con.execute(
                "SELECT lex_id, lang, title, badge, body, adopted, number, status FROM catalog"
            ):
                self.rows[r["lex_id"]] = dict(r)
            con.close()

    def get(self, lex_id: str) -> dict:
        return self.rows.get(lex_id, {})

    def expect_script(self, lex_id: str) -> str | None:
        return _EXPECT_SCRIPT.get(self.get(lex_id).get("lang", ""))
