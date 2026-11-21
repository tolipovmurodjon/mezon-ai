"""Append rows exported from the E-qaror page (tab-separated strings in a JSON list) to data/interim/eqaror_stages.csv."""

import csv
import json
import re
import sys
from pathlib import Path

from research import regnum, textnorm

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "interim" / "eqaror_stages.csv"
STAGES = ["Qoralama", "Idoraviy kelishuv", "Hokimiyat tarkibiy bo'linmalari", "Kengash kotibiyati",
          "Hokimlik yuriskonsulti", "Jamoatchilik muhokamasi", "Huquqiy ekspertiza", "E'lon qilish"]
IN_FIELDS = ["set", "reg_number", "type", "status", "asos", "asos_kind", "is_normative", "stages", "date", "body",
             "title", "id", "source_page"]
COLS = ["set", "reg_number", "type", "year", "region", "status", "asos", "asos_kind", "is_normative",
        "discussion_done", "expertise_done", "lawyer_done", "all_stages_json", "date", "body", "title", "url",
        "source_page"]
BIT = {"1": 1, "0": 0}

_COURT = re.compile(r"\bsud|суд|hal\s*qil|xal\s*qil|ҳал\s*қил|хал\s*кил|\b5-\d{4}-\d{4}", re.IGNORECASE)


def asos_kind(asos: str) -> str:
    """Who triggered the invalidation, read from E-qaror's free-text "Asos"."""
    a = textnorm.fold(asos)
    if not a:
        return ""
    if re.search(r"texnik|xatolik|imzo uchun|qaror loyiha|ikki mar[ao]t|tizimdagi kamchilik", a):
        return "clerical"
    if _COURT.search(asos) or "sud" in a.split():
        return "court"
    if re.search(r"prokur|protest", a):
        return "prosecutor"
    if re.search(r"adliya|taqdimnoma", a):
        return "adliya"
    if "kengash" in a or regnum.find_all(asos) and regnum.find_all(asos)[0]["type"] == "K":
        return "kengash"
    if "hokim" in a or regnum.find_all(asos):
        return "hokim"
    return "other"


def to_row(line: str) -> dict:
    f = dict(zip(IN_FIELDS, line.split("\t")))
    bits = f.get("stages", "")
    reg = regnum.parse(f["reg_number"]) or {}
    stages = [[n, BIT.get(b)] for n, b in zip(STAGES, bits)]
    return {
        "set": f["set"], "reg_number": f["reg_number"], "type": f["type"], "year": reg.get("year") or "",
        "region": reg.get("region_name") or "", "status": f["status"], "asos": f["asos"], "asos_kind": asos_kind(f["asos"]),
        "is_normative": f["is_normative"], "discussion_done": BIT.get(bits[5:6], ""),
        "expertise_done": BIT.get(bits[6:7], ""), "lawyer_done": BIT.get(bits[4:5], ""),
        "all_stages_json": json.dumps(stages, ensure_ascii=False) if len(bits) == 8 else "",
        "date": f["date"].replace("/", "."), "body": f["body"], "title": f["title"],
        "url": f"https://e-qaror.gov.uz/doc/{f['id']}", "source_page": f["source_page"],
    }


def main(path: str) -> None:
    lines = json.loads(Path(path).read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as fh:
            seen = {(r["set"], r["url"]) for r in csv.DictReader(fh)}
    new = [r for r in map(to_row, lines) if (r["set"], r["url"]) not in seen]
    write_header = not OUT.exists()
    with OUT.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    print(f"appended {len(new)} rows (skipped {len(lines) - len(new)} already present) -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
