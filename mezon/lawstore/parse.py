"""Split one lex.uz edition page into addressable units: articles, legal parts, clauses, annex clauses."""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from research.textnorm import fold

_ARTICLE_RE = re.compile(r"^(\d+(?:-\d+)?)\s*-\s*modda\b", re.IGNORECASE)
_ARTICLE_CYR_RE = re.compile(r"^(\d+(?:-\d+)?)\s*-\s*модда\b", re.IGNORECASE)
_CLAUSE_RE = re.compile(r"^(\d+(?:-\d+)?)\.(?:\s|$)")
_LIST_ITEM_RE = re.compile(r"^(?:\d+(?:-\d+)?\)|[a-zа-яёʻ]\)|[—–-]\s)", re.IGNORECASE)
_NOTE_DATE_RE = re.compile(r"\?ONDATE=(\d{2}\.\d{2}\.\d{4})")
_ANNEX_CLASSES = {"ACT_TITLE_APPL", "APPL_BANNER", "APPL_BANNER_LANDSCAPE_TITLE", "APPL_BANNER_TITLE"}


@dataclass
class Unit:
    path: str
    heading: str
    text: str
    element_id: str
    notes: list[str] = field(default_factory=list)

    @property
    def folded(self) -> str:
        return fold(f"{self.heading} {self.text}")


def _elem_text(div: Tag) -> tuple[str, str]:
    inner = div.find("div", id=True, recursive=False) or div
    for sup in inner.find_all("sup"):
        sup.replace_with(f"\x00{sup.get_text(strip=True)}\x00")
    text = re.sub(r"\s*\x00(\d+)\x00\s*", r"-\1", inner.get_text(" ", strip=True)).replace("\x00", "")
    return inner.get("id", ""), re.sub(r"\s+", " ", text).strip()


def parse_units(page: str) -> list[Unit]:
    """Ordered units of one edition. Paths: art:N, art:N/part:K, cl:N, annex:A/cl:N, pre:K."""
    soup = BeautifulSoup(page, "lxml")
    root = soup.find(id="main_container1") or soup
    units: list[Unit] = []
    article: Unit | None = None
    part: Unit | None = None
    clause: Unit | None = None
    annex = 0
    part_no = pre_no = 0
    in_annex_header = False

    def add(u: Unit) -> Unit:
        units.append(u)
        return u

    for div in root.find_all("div", class_=True):
        classes = set(div.get("class", []))
        if "CHANGES_ORIGINS" in classes:
            note = re.sub(r"\s+", " ", div.get_text(" ", strip=True))
            for u in (part, clause, article):
                if u is not None:
                    u.notes.append(note)
                    break
            continue
        if "lx_elem" not in classes:
            continue
        kind = next((c for c in classes if c != "lx_elem"), "")
        eid, text = _elem_text(div)
        if not text:
            continue
        if kind in _ANNEX_CLASSES:
            if not in_annex_header:
                annex += 1
            in_annex_header = True
            article = part = clause = None
            continue
        in_annex_header = False
        m = (_ARTICLE_RE.match(text) or _ARTICLE_CYR_RE.match(text)) if kind == "CLAUSE_DEFAULT" else None
        if m:
            article = add(Unit(f"art:{m.group(1)}", text, "", eid))
            part, clause, part_no = None, None, 0
            continue
        if kind in {"TEXT_HEADER_DEFAULT", "ACT_TITLE", "ACT_FORM", "SIGNATURE", "ACT_ESSENTIAL_ELEMENTS",
                    "ACT_ESSENTIAL_ELEMENTS_NUM", "CLAUSE_DEFAULT"}:
            continue
        cm = _CLAUSE_RE.match(text)
        if article is not None and not annex:
            article.text = f"{article.text} {text}".strip()
            if part is not None and _LIST_ITEM_RE.match(text):
                part.text = f"{part.text} {text}"
            else:
                part_no += 1
                part = add(Unit(f"{article.path}/part:{part_no}", article.heading, text, eid))
            continue
        if cm:
            prefix = f"annex:{annex}/" if annex else ""
            clause = add(Unit(f"{prefix}cl:{cm.group(1)}", "", text, eid))
            continue
        if clause is not None:
            clause.text = f"{clause.text} {text}"
            continue
        pre_no += 1
        add(Unit(f"{f'annex:{annex}/' if annex else ''}pre:{pre_no}", "", text, eid))
    return units


def note_dates(units: list[Unit]) -> set[str]:
    return {d for u in units for n in u.notes for d in _NOTE_DATE_RE.findall(n)}
