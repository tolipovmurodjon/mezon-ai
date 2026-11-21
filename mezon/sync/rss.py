"""lex.uz RSS watcher: new acts within hours, local decisions tagged for audit."""

import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime

from defusedxml import ElementTree as ET

from mezon.config import STORE
from research.polite_http import fetch
from research.textnorm import fold

RSS_URL = "https://lex.uz/uz/rss"
FEED_DB = STORE / "feed.sqlite"
_DATE = r"(\d{2}\.\d{2}\.\d{4})"
_LOCAL = re.compile(r"\b(hokim\w*|kengash\w*|xalq deputatlari)\b")


@dataclass
class FeedItem:
    lex_id: str
    title: str
    issuer: str
    adopted: str
    in_force: str
    is_local: bool
    url: str

    @property
    def days_to_force(self) -> int | None:
        if not (self.adopted and self.in_force):
            return None
        return (_d(self.in_force) - _d(self.adopted)).days


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _iso(s: str) -> str:
    return datetime.strptime(s, "%d.%m.%Y").date().isoformat() if s else ""


def parse(xml_bytes: bytes) -> list[FeedItem]:
    root = ET.fromstring(xml_bytes.decode("utf-8-sig"))
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        adopted = re.search(r"Qabul qilingan sana " + _DATE, desc)
        in_force = re.search(r"Kuchga kirish sanasi " + _DATE, desc)
        issuer = desc.split("Qabul qilingan sana")[0].strip().rstrip(".")
        items.append(FeedItem(
            lex_id=link.rsplit("/", 1)[-1],
            title=(it.findtext("title") or "").strip(),
            issuer=issuer,
            adopted=_iso(adopted[1]) if adopted else "",
            in_force=_iso(in_force[1]) if in_force else "",
            is_local=bool(_LOCAL.search(fold(issuer))),
            url="https://lex.uz" + link,
        ))
    return items


def _db() -> sqlite3.Connection:
    FEED_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(FEED_DB)
    con.execute("""create table if not exists feed(lex_id text primary key, title text, issuer text, adopted text,
                   in_force text, is_local int, url text, first_seen text)""")
    return con


def poll(today: str | None = None) -> list[FeedItem]:
    """Fetch the feed (one request, cached per day) and return the items not seen before."""
    today = today or date.today().isoformat()
    items = parse(fetch(RSS_URL, source="lexuz", key=f"rss_{today}.xml"))
    con = _db()
    seen = {r[0] for r in con.execute("select lex_id from feed")}
    new = [i for i in items if i.lex_id not in seen]
    con.executemany("insert into feed values(?,?,?,?,?,?,?,?)",
                    [(i.lex_id, i.title, i.issuer, i.adopted, i.in_force, int(i.is_local), i.url, today) for i in new])
    con.commit()
    return new


def main() -> None:
    new = poll(sys.argv[1] if len(sys.argv) > 1 else None)
    local = [i for i in new if i.is_local]
    print(f"{len(new)} new acts, {len(local)} local decisions")
    for i in local:
        print(f"  {i.adopted} -> in force {i.in_force} ({i.days_to_force} d)  {i.issuer[:60]} | {i.title[:80]}  {i.url}")
    for i in new:
        if not i.is_local:
            print(f"  national: {i.adopted} {i.issuer[:50]} | {i.title[:70]}")


if __name__ == "__main__":
    main()


__all__ = ["FeedItem", "asdict", "parse", "poll"]
