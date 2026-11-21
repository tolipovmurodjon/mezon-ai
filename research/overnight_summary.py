"""Exact counts after the overnight run -> logs/overnight_summary.md (numbers only from the files and databases)."""

import json
import sqlite3
import time
from pathlib import Path

from mezon.config import DECISIONS_DB, LAW_DB

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    law = sqlite3.connect(LAW_DB)
    dec = sqlite3.connect(DECISIONS_DB)
    lines = [f"# Overnight summary ({time.strftime('%Y-%m-%d %H:%M')})", "", "## Law store (editions by date)",
             "| act | editions | first | last | units |", "|---|---|---|---|---|"]
    for a, n, lo, hi in law.execute("SELECT act_key, count(*), min(valid_from), max(valid_from) FROM editions "
                                    "GROUP BY 1 ORDER BY 2 DESC"):
        u = law.execute("SELECT count(*) FROM units WHERE act_key=?", (a,)).fetchone()[0]
        lines.append(f"| {a} | {n} | {lo} | {hi} | {u} |")
    try:
        lines += ["", "## Change log", *[f"- {t}: {c}" for t, c in law.execute(
            "SELECT change_type, count(*) FROM change_log GROUP BY 1")]]
    except sqlite3.OperationalError:
        lines += ["", "## Change log", "- not built"]
    total, with_text = dec.execute("SELECT count(*), sum(length(coalesce(text,''))>0) FROM decisions").fetchone()
    lines += ["", "## Local decisions", f"- records: {total}", f"- with text: {with_text}"]
    man = ROOT / "data" / "raw" / "hf" / "manifest.json"
    lines += ["", "## Open corpora (Hugging Face)"]
    if man.exists():
        for ds, m in json.loads(man.read_text(encoding="utf-8")).items():
            lines.append(f"- {ds} ({m['license']}): rows {m['rows']}, files {m['files']}, {m['bytes'] / 1e6:.0f} MB")
    else:
        lines.append("- not downloaded")
    fails = [x for x in (ROOT / "logs" / "overnight.log").read_text(encoding="utf-8", errors="replace").splitlines()
             if x.startswith("!!! FAILED")] if (ROOT / "logs" / "overnight.log").exists() else []
    lines += ["", "## Failed steps", *(fails or ["- none"])]
    out = ROOT / "logs" / "overnight_summary.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
