"""stat.sud.uz: official administrative-court statistics on claims to declare body decisions invalid."""

import csv
import re
import subprocess
from pathlib import Path

from research.polite_http import ROOT, fetch

BASE = "https://stat.sud.uz/assets/uploads/administrative/"
FILES = ["xls/adm-decision-2025-12.xlsx", "xls/adm-decision-2025-9.xlsx", "pdf/adm-decision-2024-full.pdf",
         "xls/adm-2026-6.xlsx"]
RAW = ROOT / "data" / "raw" / "statsud"
OUT = ROOT / "data" / "interim" / "statsud_rates.csv"


def download() -> list[Path]:
    RAW.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in FILES:
        name = f.split("/")[-1]
        body = fetch(BASE + f, source="statsud", key=name)
        if not body or body[:15].lower().startswith(b"<!doctype html"):
            raise RuntimeError(f"{name}: not a data file")
        p = RAW / name
        p.write_bytes(body)
        paths.append(p)
    return paths


def xlsx_rows(path: Path) -> dict[str, list[list]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    return {ws.title: [[c for c in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def pdf_text(path: Path) -> str:
    txt = path.with_suffix(".txt")
    if not txt.exists():
        subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(path), str(txt)], check=True)
    return txt.read_text(encoding="utf-8", errors="replace")


BODY_SHEETS = {
    "маъмурий орган карорлари": "administrative_body",
    "мансабдор шахс хатти-харакати": "official_action",
    "ҳоким қарорлари": "hokimlik",
    "хоким карорлари": "hokimlik",
    "тадбиркорлик": "business_disputes",
    "ер": "land_disputes",
}
FIELDS = ["heard", "satisfied", "rejected", "left_without_review", "terminated"]
_REGION_CELL = re.compile(r"viloyati|R\.$|shahri|^JAMI$")
_YEAR = re.compile(r"(20\d\d)(?:\D{0,12}?(1\s*-\s*yarmi))?")


def parse_sheet(rows: list[list]) -> list[dict]:
    """Rows of (region, year, 5 outcome counts) from one regional table; groups of 5 numbers per year."""
    years: list[str] = []
    out = []
    for r in rows:
        cells = ["" if c is None else str(c).strip() for c in r]
        if not years:
            found = [_YEAR.search(c) for c in cells if _YEAR.search(c) and ("y" in c or "йил" in c)]
            if len(found) >= 2:
                years = [m[1] + ("H1" if m[2] else "") for m in found]
            continue
        idx = next((i for i, c in enumerate(cells) if _REGION_CELL.search(c)), None)
        if idx is None:
            continue
        nums = [int(c) for c in cells[idx + 1:] if re.fullmatch(r"\d+", c)]
        for j, y in enumerate(years):
            group = nums[j * 5: j * 5 + 5]
            if len(group) == 5:
                out.append({"region": cells[idx], "year": y, **dict(zip(FIELDS, group))})
    return out


def build() -> list[dict]:
    rows = []
    for name in ["adm-decision-2025-9.xlsx", "adm-decision-2025-12.xlsx", "adm-2026-6.xlsx"]:
        for sheet, data in xlsx_rows(RAW / name).items():
            body = BODY_SHEETS.get(sheet.strip())
            if body:
                rows += [{"source": name, "body_type": body, **r} for r in parse_sheet(data)]
    return rows


def pdf_2024_hokimlik_total() -> list[int]:
    t = pdf_text(RAW / "adm-decision-2024-full.pdf")
    part = t[t.find("Mahalliy hokimlik qarorlarining"):]
    m = re.search(r"JAMI\s+([\d ]+)", part)
    return m[1].split() if m else []


if __name__ == "__main__":
    for p in download():
        print(p.name, p.stat().st_size)
    rows = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "body_type", "region", "year", *FIELDS])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}")
    latest = {}
    for r in rows:
        if r["body_type"] == "hokimlik" and r["region"] == "JAMI":
            latest[r["year"]] = r
    for y in sorted(latest):
        r = latest[y]
        print(f"hokimlik {y}: heard {r['heard']}, declared invalid {r['satisfied']} "
              f"({r['satisfied'] / r['heard']:.1%}), rejected {r['rejected']}  [{r['source']}]")
    print("2024 PDF hokimlik JAMI row:", pdf_2024_hokimlik_total())
