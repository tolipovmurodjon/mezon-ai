"""Polite, cache-first fetching of lex.uz act pages, their editions and relation panels."""

import html
import re

from research.polite_http import fetch

BASE = "https://lex.uz"
_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.DOTALL)
_ONDATE_RE = re.compile(r"\?ONDATE=(\d{2}\.\d{2}\.\d{4})(?:%20|\s)(\d{2})")


def _get(path: str, key: str) -> str:
    return fetch(BASE + path, "lexuz", key=key).decode("utf-8", "replace")


def doc_page(lex_id: str) -> str:
    """The current text of an act (Latin Uzbek where the id is the Latin one)."""
    return _get(f"/uz/docs/{lex_id}", f"docs/{lex_id.lstrip('-')}_{'m' if lex_id.startswith('-') else 'p'}.html")


def _tag(lex_id: str) -> str:
    """`x` and `-x` are different documents (usually the Latin and Cyrillic versions of one act, sometimes two acts),
    so every cache key keeps the sign: 123_p = id 123, 123_m = id -123."""
    return f"{lex_id.lstrip('-')}_{'m' if lex_id.startswith('-') else 'p'}"


def _legacy_reuse(lex_id: str, old_key: str, new_key: str) -> None:
    """Until 20.11.2026 editions and relation panels were cached without the sign, so the two twins shared one file
    and the second twin never got its own. Reuse an old file only if its title is closer to THIS twin's title than to
    the other twin's; otherwise leave it, and the page is fetched fresh under the new key."""
    from difflib import SequenceMatcher

    from research.polite_http import CACHE, WRITE_CACHE

    if any((r / "lexuz" / new_key).exists() for r in (CACHE, WRITE_CACHE)):
        return
    old = next((r / "lexuz" / old_key for r in (CACHE, WRITE_CACHE) if (r / "lexuz" / old_key).exists()), None)
    if old is None:
        return
    twin = lex_id[1:] if lex_id.startswith("-") else "-" + lex_id

    def doc_title(i: str) -> str:
        p = next((r / "lexuz" / f"docs/{_tag(i)}.html" for r in (CACHE, WRITE_CACHE)
                  if (r / "lexuz" / f"docs/{_tag(i)}.html").exists()), None)
        return page_title(p.read_bytes().decode("utf-8", "replace")) if p else ""

    def doc_text(i: str) -> str:
        p = next((r / "lexuz" / f"docs/{_tag(i)}.html" for r in (CACHE, WRITE_CACHE)
                  if (r / "lexuz" / f"docs/{_tag(i)}.html").exists()), None)
        return p.read_bytes().decode("utf-8", "replace") if p else ""

    def cyr(text: str) -> float:  # share of Cyrillic among letters, page chrome and scripts removed
        text = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        c = len(re.findall(r"[Ѐ-ӿ]", text))
        a = len(re.findall(r"[A-Za-z]", text))
        return c / (c + a) if c + a else 0.0

    def keep() -> None:
        dst = WRITE_CACHE / "lexuz" / new_key
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(old.read_bytes())

    body = old.read_bytes().decode("utf-8", "replace")
    if not doc_title(twin):
        # the twin was never crawled, so the shared file can only have been fetched for this id
        keep()
        return
    got = page_title(body)
    mine, theirs = doc_title(lex_id), doc_title(twin)
    if not mine:
        return
    s_mine = SequenceMatcher(None, got, mine).ratio()
    s_theirs = SequenceMatcher(None, got, theirs).ratio()
    if max(s_mine, s_theirs) >= 0.5 and abs(s_mine - s_theirs) > 0.05:
        if s_mine > s_theirs:  # edition pages carry the act title: decide by title
            keep()
        return
    # relation panels have a generic title: decide by script (Latin vs Cyrillic twin), only if clearly apart
    r_got, r_mine, r_theirs = cyr(body), cyr(doc_text(lex_id)), cyr(doc_text(twin))
    if abs(r_mine - r_theirs) > 0.2 and abs(r_got - r_mine) < abs(r_got - r_theirs):
        keep()


def edition_page(lex_id: str, ondate: str) -> str:
    """One edition: `ondate` is 'dd.mm.yyyy NN' exactly as the edition links spell it."""
    d, n = ondate.split()
    new_key = f"editions/{_tag(lex_id)}/{d}_{n}.html"
    _legacy_reuse(lex_id, f"editions/{lex_id.lstrip('-')}/{d}_{n}.html", new_key)
    return _get(f"/uz/docs/{lex_id}?ONDATE={d}%20{n}", new_key)


def relation_page(lex_id: str, panel: str) -> str:
    """`panel` is revhis (amending acts), correspondents (acts it cites) or respondents (acts citing it)."""
    new_key = f"actinfo/{panel}/{_tag(lex_id)}.html"
    _legacy_reuse(lex_id, f"actinfo/{panel}/{lex_id.lstrip('-')}.html", new_key)
    return _get(f"/uz/actinfo/{panel}/{lex_id}", new_key)


def page_title(page: str) -> str:
    m = _TITLE_RE.search(page)
    return html.unescape(m.group(1)).strip() if m else ""


def edition_dates(page: str, lex_id: str) -> set[str]:
    """Edition dates ('dd.mm.yyyy NN') linked from this page for the same act."""
    own = re.escape(lex_id.lstrip("-"))
    dates = set()
    for m in re.finditer(rf'href="/uz/docs/-?{own}\?ONDATE=(\d{{2}}\.\d{{2}}\.\d{{4}})(?:%20|\s)(\d{{2}})', page):
        dates.add(f"{m.group(1)} {m.group(2)}")
    return dates


def amendment_dates(page: str) -> set[str]:
    """Dates of the amending acts' editions linked inside the inline "…tahririda" notes."""
    dates = set()
    for block in re.findall(r'class="CHANGES_ORIGINS[^"]*">(.*?)</div></div>', page, re.DOTALL):
        dates.update(m.group(1) for m in _ONDATE_RE.finditer(block))
    return dates


def has_pending_banner(page: str) -> bool:
    low = page.lower()
    return "kiritilmoqda" in low or "киритилмоқда" in low
