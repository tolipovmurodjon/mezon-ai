"""The ONE number: share of E-qaror declared-invalid decisions (release=200) that the Mezon rules flag, on their real text.

    python -X utf8 -m research.declared_invalid_recall <dir with <code>.txt.gz files> <declared_invalid list dir>

Runs the same audit as the platform's tools/audit_text.py (raw text, no store row). Writes
data/interim/declared_invalid_recall.json (counts only, no decision text).
"""

import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, r"D:\10_projects\mezon_platform_original\tools")
from audit_text import audit_report  # noqa: E402


def main(txt_dir: Path, list_dir: Path) -> None:
    titles = {}
    for f in list_dir.glob("p*.json"):
        for r in json.loads(f.read_text(encoding="utf-8"))["data"]["list"]:
            titles[r["code"]] = r.get("title", "")
    files = sorted(txt_dir.rglob("*.txt.gz")) if txt_dir.exists() else []
    n = n_any = n_pv = errors = 0
    by_rule, by_rule_pv = Counter(), Counter()
    verdicts = Counter()
    for f in files:
        code = re.sub(r"\.txt\.gz$", "", f.name)
        if code not in titles:
            continue
        text = gzip.open(f, "rt", encoding="utf-8").read()
        n += 1
        try:
            rep = audit_report(text, titles[code])
        except Exception as e:  # noqa: BLE001
            errors += 1
            print("error", code, type(e).__name__, e)
            continue
        flags = rep.get("flags", [])
        verdicts[rep.get("verdict")] += 1
        if flags:
            n_any += 1
        pv = [x for x in flags if x.get("status") == "possible_violation"]
        if pv:
            n_pv += 1
        for c in {x["check"] for x in flags}:
            by_rule[c] += 1
        for c in {x["check"] for x in pv}:
            by_rule_pv[c] += 1
    out = {
        "n_with_text": n, "n_audit_errors": errors,
        "n_flagged_any": n_any, "share_flagged_any": round(n_any / n, 4) if n else None,
        "n_flagged_possible_violation": n_pv, "share_flagged_possible_violation": round(n_pv / n, 4) if n else None,
        "flags_by_rule_docs_any": dict(by_rule.most_common()), "flags_by_rule_docs_possible_violation": dict(by_rule_pv.most_common()),
        "verdicts": dict(verdicts),
        "note": "N = declared-invalid decisions (E-qaror release=200) with downloaded text; ~90% are individual decisions, so procedure rules cannot catch them.",
    }
    (ROOT / "data" / "interim" / "declared_invalid_recall.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
