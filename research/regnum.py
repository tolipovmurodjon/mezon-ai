"""Parse E-qaror registration numbers of hokim and Kengash decisions."""

import re

REGIONS = {
    1: "Andijon", 2: "Buxoro", 3: "Jizzax", 4: "Qashqadaryo", 5: "Navoiy", 6: "Namangan", 7: "Samarqand",
    8: "Surxondaryo", 9: "Sirdaryo", 10: "Toshkent viloyati", 11: "Farg'ona", 12: "Xorazm",
    13: "Qoraqalpog'iston", 14: "Toshkent shahar",
}
TYPES = {"Q": "hokim qarori", "F": "hokim farmoyishi", "K": "kengash qarori"}

_HOKIM = re.compile(r"\b(\d{1,4})-(\d{1,2})-(\d{1,3})-([QF])/(\d{2})\b")
_HOKIM_OLD = re.compile(r"\b(\d{1,4})-(\d{1,2})-(\d{1,3})/([QF])\b")
_KENGASH = re.compile(r"\b([IVX]{1,4})-(\d{1,3})-(\d{1,4})-(\d{1,2})-(\d{1,3})-K/(\d{2})\b")


def _hokim(m: re.Match, has_year: bool) -> dict:
    num, reg, dist, typ = int(m[1]), int(m[2]), int(m[3]), m[4]
    return {"raw": m[0], "type": typ, "number": num, "region": reg, "region_name": REGIONS.get(reg),
            "district": dist, "year": 2000 + int(m[5]) if has_year else None}


def _kengash(m: re.Match) -> dict:
    reg = int(m[4])
    return {"raw": m[0], "type": "K", "convocation": m[1], "session": int(m[2]), "number": int(m[3]),
            "region": reg, "region_name": REGIONS.get(reg), "district": int(m[5]), "year": 2000 + int(m[6])}


def parse(s: str) -> dict | None:
    s = s.strip()
    for rx, fn in ((_KENGASH, _kengash), (_HOKIM, lambda m: _hokim(m, True)), (_HOKIM_OLD, lambda m: _hokim(m, False))):
        m = rx.fullmatch(s)
        if m:
            return fn(m)
    return None


def find_all(text: str) -> list[dict]:
    """Every registration number in a text, in order of appearance."""
    hits = [(m.start(), _kengash(m)) for m in _KENGASH.finditer(text)]
    hits += [(m.start(), _hokim(m, True)) for m in _HOKIM.finditer(text)]
    hits += [(m.start(), _hokim(m, False)) for m in _HOKIM_OLD.finditer(text)]
    return [h for _, h in sorted(hits, key=lambda x: x[0])]
