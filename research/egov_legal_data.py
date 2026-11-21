"""data.egov.uz: full rows of the legal-sector datasets (Adliya, courts, prosecutor, ombudsman, judges' council, ...).

    .venv/Scripts/python.exe -X utf8 -m research.egov_legal_data          # LAPTOP (no answer from AWS) -> data/raw/egov/legal/

Uses the table endpoint the dataset page itself calls: POST apiClient/Main/GetMainData?GuidId=<id> with
{"guidId", "fields": {}, "limit", "offset"}; 100 rows per request, one request every 1.5 s, resumable (one JSON file
per page). Dataset list = catalog rows (research/egov_catalog.py) whose organisation is legal. Licence: CC BY-SA 4.0.
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "data" / "raw" / "egov" / "catalog.jsonl"
OUT = ROOT / "data" / "raw" / "egov" / "legal"
URL = "https://data.egov.uz/apiClient/Main/GetMainData?GuidId={g}"
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)", "Content-Type": "application/json"}
LEGAL = ("Adliya", "Oliy sud", "prokuratura", "Sudyalar oliy kengashi", "vakil", "Raqobatni", "Konstitutsiyaviy",
         "Oliy Majlis", "Senat")
LIMIT = 100


def page(g: str, offset: int) -> dict:
    body = json.dumps({"guidId": g, "fields": {}, "limit": LIMIT, "offset": offset}).encode()
    for attempt in range(4):
        try:
            time.sleep(1.5)
            req = urllib.request.Request(URL.format(g=g), data=body, headers=UA, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001 - retry, then give up on this page
            time.sleep(20 * (attempt + 1))
    return {}


def main() -> None:
    rows = [json.loads(line) for line in CAT.read_text(encoding="utf-8").split("\n") if line.strip()]
    sets = [r for r in rows if any(w.lower() in r["orgName"]["uzbText"].lower() for w in LEGAL)]
    print(f"legal datasets: {len(sets)}", flush=True)
    total_rows = 0
    for r in sets:
        g = r["structId"]
        d = OUT / f"{r['name']}_{g}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        offset, n = 0, None
        while n is None or offset < n:
            f = d / f"rows_{offset:07d}.json"
            if f.exists():
                res = json.loads(f.read_text(encoding="utf-8"))
            else:
                res = page(g, offset)
                if not res.get("result"):
                    break
                f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            result = res.get("result") or {}
            n = result.get("count") or 0
            got = len(result.get("data") or [])
            total_rows += got
            if not got:
                break
            offset += LIMIT
        print(f"{r['name']} {r['dataName']['uzbText'][:60]}: {n} rows", flush=True)
    print(f"EGOV LEGAL DONE: {len(sets)} datasets, {total_rows} rows", flush=True)


if __name__ == "__main__":
    main()
