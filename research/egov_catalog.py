"""data.egov.uz (open data portal, CC BY-SA 4.0): the full dataset catalog via the page's own list endpoint.

    .venv/Scripts/python.exe -X utf8 -m research.egov_catalog      # LAPTOP (the site does not answer AWS) -> data/raw/egov/

GET apiClient/main/gettable?offset=N&limit=100 (what /datasets calls), one request every 1.5 s, then a short
report of datasets per organisation, with the legal ones (justice, courts, prosecutor, hokimliks, parliament) first.
"""

import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "egov"
URL = "https://data.egov.uz/apiClient/main/gettable?offset={o}&limit=100"
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)"}
LEGAL = ("adliya", "sud", "prokuratura", "hokimlig", "kengash", "oliy majlis", "senat", "ombudsman", "vakil",
         "yustitsiya", "huquq")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, o, total = [], 0, None
    while total is None or o < total:
        f = OUT / f"catalog_{o:06d}.json"
        if not f.exists():
            time.sleep(1.5)
            with urllib.request.urlopen(urllib.request.Request(URL.format(o=o), headers=UA), timeout=60) as r:
                f.write_bytes(r.read())
        d = json.loads(f.read_text(encoding="utf-8"))["result"]
        total = d["count"]
        rows += d["data"]
        o += 100
    (OUT / "catalog.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    orgs = Counter(r["orgName"]["uzbText"] for r in rows)
    legal = {k: v for k, v in orgs.items() if any(w in k.lower() for w in LEGAL)}
    print(f"catalog: {len(rows)} datasets of {total}, {len(orgs)} organisations")
    print("legal organisations:")
    for k, v in sorted(legal.items(), key=lambda x: -x[1]):
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()
