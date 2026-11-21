"""Stage 01a/b: national act pages and editions -> text in document order, metadata, change notes, unit intervals.

`mezon.lawstore.parse.parse_units` stays untouched: it builds the lookup units. Here `assemble_text` walks the same
elements in document order, keeps title, form, preamble, chapter headings, signature and annex banners (which
`parse_units` drops), tags every block with the unit path `parse_units` would give it, and moves widget text,
registration lines, topic codes and inline amendment notes out of the body."""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from mezon.lawstore.parse import (
    _ANNEX_CLASSES,
    _ARTICLE_CYR_RE,
    _ARTICLE_RE,
    _CLAUSE_RE,
    _LIST_ITEM_RE,
    Unit,
    _elem_text,
)
from mezon.lawstore.store import iso
from research.textnorm import fold

_META_KINDS = {"ACCEPTING_BODY", "DEPARTMENTAL", "PUBLICATION_ORIGIN", "INDEXES_ON_REF"}
_PLAIN_KINDS = {
    "TEXT_HEADER_DEFAULT",
    "ACT_TITLE",
    "ACT_FORM",
    "SIGNATURE",
    "ACT_ESSENTIAL_ELEMENTS",
    "ACT_ESSENTIAL_ELEMENTS_NUM",
    "CLAUSE_DEFAULT",
}
_NOTE_HREF = re.compile(r"/uz/docs/(-?\d+)\?ONDATE=(\d{2}\.\d{2}\.\d{4})")
_TITLE = re.compile(r"<title>\s*(.*?)\s*</title>", re.DOTALL)
_TITLE_PARTS = re.compile(r"^\s*(.*?)-(?:сон|son)\s+(\d{2}\.\d{2}\.\d{4})\.?\s*(.*)$", re.DOTALL)
_LOST_WARN = re.compile(
    r"(?:kuchini yo[ʻ‘’'`]?qotgan|кучини йўқотган|утратил[аи]? силу)\s*(\d{2}\.\d{2}\.\d{4})?", re.IGNORECASE
)

# folded (Latin, no apostrophes) patterns; Cyrillic and Russian notes fold to the same shapes
_NOTE_KINDS = [
    ("lost_force", re.compile(r"kuchini yoqotgan|kuchini yoqotgan deb|utratil\w* silu|kuchini yoqotdi")),
    ("moved", re.compile(r"kochirilgan|otkazilgan|olib otilgan|perenes")),
    (
        "renumbered",
        re.compile(
            r"deb hisoblansin|tegishli ravishda .{0,40} hisoblansin|raqami .{0,30}ozgartirilgan|"
            r"schitat\w* sootvetstvenno|raqamlari ozgartirilgan"
        ),
    ),
    ("removed", re.compile(r"chiqarib tashlangan|chiqarilgan|isklyuchen")),
    ("replaced", re.compile(r"almashtirilgan|zamenen|bilan almashtirilgan")),
    ("inserted", re.compile(r"asosan kiritilgan|qoshilgan|kiritilgan|vvedene?n|dopolnen")),
    ("supplemented", re.compile(r"toldirilgan|dopolnen")),
    ("edited", re.compile(r"tahririda|v redaktsii|v redakcii")),
]


@dataclass
class Block:
    kind: str
    text: str
    eid: str = ""
    path: str | None = None  # the unit path parse_units gives this element (part level inside articles)
    art: str | None = None  # its article container path, if any


@dataclass
class Note:
    text: str
    kind: str
    target: str
    act_ids: list[str]
    dates: list[str]  # ISO dates from the ?ONDATE= links (the amending act's edition date)
    anchor_path: str | None
    anchor_block: int
    source: str = "changes_origins"  # or "lexuz_sharhi"


@dataclass
class ActText:
    title: str = ""
    blocks: list[Block] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    n_table_chars: int = 0
    table_numeric_share: float = 0.0

    @property
    def body(self) -> str:
        out: list[str] = []
        for b in self.blocks:
            if b.kind in {"article", "heading", "annex"} and out and out[-1] != "":
                out.append("")
            out.append(b.text)
        return "\n".join(out).strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def render_table(table: Tag) -> str:
    """Rows as `cell | cell | cell`, header first, merged cells repeated."""
    rows: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}  # column -> (rows still to fill, text) for rowspans
    for tr in table.find_all("tr"):
        cells: list[str] = []
        col = 0
        for td in tr.find_all(["td", "th"], recursive=False) or tr.find_all(["td", "th"]):
            while col in pending:
                left, txt = pending[col]
                cells.append(txt)
                pending[col] = (left - 1, txt)
                if left - 1 <= 0:
                    del pending[col]
                col += 1
            txt = _clean(td.get_text(" ", strip=True))
            span = int(td.get("colspan", 1) or 1) if str(td.get("colspan", "1")).isdigit() else 1
            rspan = int(td.get("rowspan", 1) or 1) if str(td.get("rowspan", "1")).isdigit() else 1
            for _ in range(span):
                cells.append(txt)
                if rspan > 1:
                    pending[col] = (rspan - 1, txt)
                col += 1
        while col in pending:
            left, txt = pending[col]
            cells.append(txt)
            pending[col] = (left - 1, txt)
            if left - 1 <= 0:
                del pending[col]
            col += 1
        if any(cells):
            rows.append(cells)
    return "\n".join(" | ".join(r) for r in rows)


def classify_note(text: str) -> dict:
    """What a '(... tahririda)' style note says: kind, the part of the act it concerns, the source line."""
    f = fold(text)
    kind = next((k for k, rx in _NOTE_KINDS if rx.search(f)), "other")
    m = re.match(
        r"^\(?\s*(.*?)\s*(?:Oʻzbekiston Respublikasining|Узбекистон|Ўзбекистон|Республики Узбекистан|"
        r"Prezidentining|Vazirlar Mahkamasining|\d{4}-yil|\d{4} йил|[A-Za-zʻ ]{0,30}\d{1,2}[ -]\w+ \d{4})",
        text,
    )
    target = _clean(m.group(1)) if m and m.group(1) else _clean(text[:60])
    return {"kind": kind, "target": target[:120]}


def _read_notes(div: Tag, source: str, anchor_block: int, anchor_path: str | None) -> Note | None:
    text = _clean(div.get_text(" ", strip=True))
    if not text:
        return None
    links = _NOTE_HREF.findall(str(div))
    c = classify_note(text)
    return Note(
        text=text,
        kind=c["kind"],
        target=c["target"],
        act_ids=sorted({a for a, _ in links}),
        dates=sorted({iso(d) for _, d in links}),
        anchor_path=anchor_path,
        anchor_block=anchor_block,
        source=source,
    )


def page_title(page: str) -> str:
    m = _TITLE.search(page)
    return _clean(re.sub(r"&nbsp;", " ", m.group(1))) if m else ""


def title_parts(title: str) -> dict:
    m = _TITLE_PARTS.match(title)
    if not m:
        d = re.match(r"^(\d{2}\.\d{2}\.\d{4})\.?\s+(.*)$", title)  # codes: "30.04.1998. <name>", no number
        if d:
            return {"number": "", "adopted": iso(d.group(1)), "name": _clean(d.group(2))}
        return {"number": "", "adopted": None, "name": title}
    return {"number": m.group(1).strip(), "adopted": iso(m.group(2)), "name": _clean(m.group(3))}


def page_meta(page: str, soup: BeautifulSoup | None = None) -> dict:
    """Status, registration, topics and pending-amendment info from the page (widgets removed)."""
    from mezon.lawstore.fetch import has_pending_banner

    soup = soup or BeautifulSoup(page, "lxml")
    warn = [_clean(d.get_text(" ", strip=True)) for d in soup.find_all("div", class_="act_warning")]
    for w in soup.find_all(class_="COMMENT_FOR_WARNING"):
        warn.append(_clean(w.get_text(" ", strip=True)))
    status, lost_on = "unknown", None
    joined = " ".join(warn)
    if re.search(
        r"hali kuchga kirgan emas|ҳали кучга кирган эмас|ещё не вступил|еще не вступил", joined, re.IGNORECASE
    ):
        status = "not_yet_in_force"
    m = _LOST_WARN.search(joined)
    if m:
        status = "lost_force"
        lost_on = iso(m.group(1)) if m.group(1) else None
    topics = [t.strip() for w in warn for t in re.findall(r"\[\s*OKOZ:\s*(.*?)\]", w)]
    strip = soup.find(class_="lx_strip-text")
    pending = None
    if strip is not None:
        a = strip.find("a", href=True)
        pending = a["href"].split("/")[-1] if a else None
    return {
        "status": status,
        "lost_force_on": lost_on,
        "topics": topics,
        "provisional": has_pending_banner(page),
        "pending_act": pending,
        "warnings": [w for w in warn if "PDF" not in w and "ПДФ" not in w],
        "pdf_only": any(re.search(r"PDF (?:shaklida|shaklda)|PDF шаклид|PDF шаклда", w) for w in warn),
    }


def assemble_text(page: str) -> ActText:
    """Document-order text of one act page plus its notes and metadata. Widget text and ads never reach the body."""
    soup = BeautifulSoup(page, "lxml")
    for t in soup.find_all(["script", "style", "ins", "noscript"]):
        t.decompose()
    root = soup.find(id="main_container1") or soup
    res = ActText(title=page_title(page))
    res.meta = page_meta(page, soup)
    blocks = res.blocks
    article: str | None = None
    part: str | None = None
    clause: str | None = None
    annex = part_no = pre_no = 0
    in_annex_header = False
    table_chars = table_num = 0
    meta_lines: dict[str, list[str]] = {}

    def last_path() -> str | None:
        return blocks[-1].path if blocks else None

    skip_out = False

    def emit(block: Block) -> None:
        if not skip_out:
            blocks.append(block)

    for div in root.find_all("div", class_=True):
        classes = set(div.get("class", []))
        if "CHANGES_ORIGINS" in classes or "COMMENTLEXUZ" in classes:
            src = "changes_origins" if "CHANGES_ORIGINS" in classes else "lexuz_sharhi"
            n = _read_notes(div, src, len(blocks) - 1, last_path())
            if n:
                if src == "lexuz_sharhi":
                    n.text = re.sub(r"^(?:LexUZ sharhi|LexUZ шарҳи|LexUZ комментарий)\s*", "", n.text)
                    f = fold(n.text)
                    n.kind = "lost_force" if re.search(r"kuchini yoqotgan|utratil", f) else "sharh"
                res.notes.append(n)
            continue
        if "lx_elem" not in classes:
            continue
        if any("lx_elem" in (p.get("class") or []) for p in div.parents if isinstance(p, Tag)):
            continue
        kind = next((c for c in classes if c != "lx_elem"), "")
        eid, flat = _elem_text(div)
        table = div.find("table")
        if not flat:
            continue
        skip_out = kind in _META_KINDS  # moved to metadata, but the path counters advance as in parse_units
        if skip_out:
            meta_lines.setdefault(kind, []).append(flat)
        shown = flat
        if table is not None:
            shown = render_table(table) or flat
            table_chars += len(shown)
            digits = sum(c.isdigit() for c in shown)
            table_num += digits
        if kind in _ANNEX_CLASSES:
            if not in_annex_header:
                annex += 1
                shown = f"[ILOVA {annex}] {flat}"
            in_annex_header = True
            article = part = clause = None
            emit(Block("annex", shown, eid))
            continue
        in_annex_header = False
        m = (_ARTICLE_RE.match(flat) or _ARTICLE_CYR_RE.match(flat)) if kind == "CLAUSE_DEFAULT" else None
        if m:
            article = f"art:{m.group(1)}"
            part = clause = None
            part_no = 0
            emit(Block("article", shown, eid, article, article))
            continue
        if kind in _PLAIN_KINDS:
            bk = {
                "TEXT_HEADER_DEFAULT": "heading",
                "ACT_TITLE": "title",
                "ACT_FORM": "form",
                "SIGNATURE": "signature",
            }.get(kind, "heading" if kind != "CLAUSE_DEFAULT" else "text")
            emit(Block(bk, shown, eid))
            continue
        cm = _CLAUSE_RE.match(flat)
        if article is not None and not annex:
            if part is not None and _LIST_ITEM_RE.match(flat):
                pass
            else:
                part_no += 1
                part = f"{article}/part:{part_no}"
            emit(Block("table" if table is not None else "text", shown, eid, part, article))
            continue
        if cm:
            prefix = f"annex:{annex}/" if annex else ""
            clause = f"{prefix}cl:{cm.group(1)}"
            emit(Block("table" if table is not None else "text", shown, eid, clause))
            continue
        if clause is not None:
            emit(Block("table" if table is not None else "text", shown, eid, clause))
            continue
        pre_no += 1
        emit(
            Block(
                "table" if table is not None else "text",
                shown,
                eid,
                f"{f'annex:{annex}/' if annex else ''}pre:{pre_no}",
            )
        )

    if not blocks:
        res.meta["no_lx_elem"] = True
    body_chars = sum(len(b.text) for b in blocks)
    res.n_table_chars = table_chars
    res.table_numeric_share = round(table_num / table_chars, 3) if table_chars else 0.0
    res.meta["registration"] = " ".join(meta_lines.get("DEPARTMENTAL", []))
    res.meta["body"] = " ".join(meta_lines.get("ACCEPTING_BODY", []))
    res.meta["publication_origin"] = " ".join(meta_lines.get("PUBLICATION_ORIGIN", []))
    res.meta["indexes"] = " ".join(meta_lines.get("INDEXES_ON_REF", []))
    res.meta["body_chars"] = body_chars
    return res


def fallback_text(page: str) -> str:
    """Pages with body text but no lx_elem: tag-stripped main container (lower tier, source_kind html_fallback)."""
    soup = BeautifulSoup(page, "lxml")
    for t in soup.find_all(["script", "style", "ins", "noscript"]):
        t.decompose()
    root = soup.find(id="main_container1") or soup
    for w in root.find_all(class_=["lx_elem2", "lx_elem3"]):
        w.decompose()
    return re.sub(
        r"\n{3,}", "\n\n", "\n".join(_clean(s) for s in root.get_text("\n").splitlines() if _clean(s))
    )


def card1_status(page: str) -> dict:
    """Status, termination date and reasons from the legal analysis card (the Russian field names)."""
    t = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", "|", t)
    parts = [p.strip() for p in re.split(r"\|", t) if p.strip()]

    def after(label: str) -> str:
        for i, p in enumerate(parts):
            if p.startswith(label):
                return parts[i + 1] if i + 1 < len(parts) else ""
        return ""

    status = after("Статус акта")
    end = after("Дата прекращения действия")
    reason = after("Причины прекращения действия")
    if reason.startswith(("Характер нормативности", "Официальный источник")):
        reason = ""
    start = after("Дата вступления в силу")
    d = lambda s: iso(s) if re.match(r"\d{2}\.\d{2}\.\d{4}", s or "") else None
    return {
        "card_status": status,
        "card_in_force_from": d(start),
        "card_lost_force": d(end),
        "card_reason": reason,
    }


def unit_versions(editions: list[tuple[str, list[Unit], bool]]) -> list[dict]:
    """Unit intervals from an ordered edition list [(ondate 'dd.mm.yyyy NN', units, provisional)], a pure copy of
    `mezon.lawstore.build._store_editions` without SQLite. A unit whose text did not change is stored once with
    valid_from / valid_to (half-open: valid_to = start of the next edition, null = still current)."""
    starts = [iso(s) for s, _, _ in editions]
    open_units: dict[str, list] = {}
    closed: list[list] = []
    for i, (s, units, _prov) in enumerate(editions):
        seen = set()
        for u in units:
            if u.path in seen:
                continue
            seen.add(u.path)
            cur = open_units.get(u.path)
            if cur and cur[2] == u.text and cur[1] == u.heading and cur[7] == i - 1:
                cur[7] = i
                continue
            if cur:
                closed.append(cur)
            open_units[u.path] = [u.path, u.heading, u.text, u.element_id, "\n".join(u.notes), s, i, i]
        for path in [p for p, row in open_units.items() if row[7] < i]:
            closed.append(open_units.pop(path))
    closed.extend(open_units.values())
    parents = {r[0].split("/part:")[0] for r in closed if "/part:" in r[0]}
    return [
        {
            "path": p,
            "heading": h,
            "text": t,
            "element_id": e,
            "notes": n,
            "ondate": s,
            "seq_from": a,
            "seq_to": b,
            "valid_from": starts[a],
            "valid_to": starts[b + 1] if b + 1 < len(starts) else None,
            "is_container": p in parents,
        }
        for p, h, t, e, n, s, a, b in closed
    ]
