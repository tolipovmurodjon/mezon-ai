"""Execution-based grader for MezonAudit-bench: the model writes an Adliya conclusion, code decides if it is right.

    .venv/Scripts/python.exe -X utf8 -m research.audit_bench.grade RUN.jsonl [RUN2.jsonl ...] [--split smith] [--public-only]

PREDICTION SCHEMA (one JSON object per line of a run file; the harness writes it, anything else may too):
  {"id": "a1-...",                                   # the instance id
   "verdict": "positive" | "positive_with_fixable_defects" | "negative",   # Adliya's own three conclusions
   "defects": [{"type": "form_farmoyish|business_3m|dead_citation|duplicate_clause|retroactive|double_repeal|other",
                "clause": 3,                          # optional number of the clause
                "evidence_quote": "...",              # word for word from the decision text
                "citations": [{"act": "O'RQ-682", "article": "40", "quote": "...", "on_date": "YYYY-MM-DD"}]}],
   "calls": [...], "truncated": false}                # optional: tool calls made, text cut for the prompt

GATES AND TESTS (SWE-bench vocabulary):
  CITATION gate  every citation names an act that exists, an article that exists in the edition in force on the
                 DECISION date (the model's own on_date is ignored), and a quote word for word in that edition; every
                 evidence_quote is word for word in the decision. Errors are counted like the Stanford legal RAG audit
                 (Magesh 2024): fabricated (the act, the article or the quote does not exist), misgrounded (it exists but
                 not in force on the date), ungrounded (a defect with no citation, or a citation with no quote).
                 One error of any kind fails the instance, whatever the verdict was.
  FAIL_TO_PASS   REAL / SMITH: verdict is not "positive" AND a reported defect matches the gold type (REAL gold type
                 is "any": the cancelling act names a trigger, not one of our families).
  PASS_TO_PASS   CLEAN: verdict "positive" AND no defect reported.
  resolved       gate AND the test of its split. A missing or malformed prediction is unresolved (a CLEAN instance too).
Numbers always come with N and a 95 % Wilson interval; pass^k (tau-bench) needs k run files.
Flagged means "possible violation, for expert review", never "illegal".
"""

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mezon.rules.common import squash
from mezon.tools import _path
from research.audit_bench.instances import FAMILIES, load

VERDICTS = ("positive", "positive_with_fixable_defects", "negative")
TYPES = set(FAMILIES) | {"other"}
SPLITS = ("real", "smith", "clean", "live")
RESULTS = ROOT / "data" / "bench" / "audit_v1" / "results"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - w), min(1.0, c + w)


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a (N=0)"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:5.1f}% [{100 * lo:.0f}-{100 * hi:.0f}] {k}/{n}"


def parse_prediction(obj) -> dict | None:
    """A normalised prediction, or None when it is malformed (then the instance is unresolved)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
        return None
    verdict = str(obj.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if verdict not in VERDICTS:
        return None
    defects = []
    for d in obj.get("defects") or []:
        if not isinstance(d, dict):
            return None
        typ = str(d.get("type", "other")).strip().lower()
        cits = [c for c in (d.get("citations") or []) if isinstance(c, dict)]
        defects.append(
            {
                "type": typ if typ in TYPES else "other",
                "evidence_quote": str(d.get("evidence_quote") or ""),
                "citations": cits,
                "clause": d.get("clause"),
            }
        )
    return {"id": obj["id"], "verdict": verdict, "defects": defects, "truncated": bool(obj.get("truncated"))}


def _ever_had(law, key: str, path: str) -> bool:
    con = getattr(law, "con", None)
    return (
        con is not None
        and con.execute("SELECT 1 FROM units WHERE act_key=? AND path=? LIMIT 1", (key, path)).fetchone()
        is not None
    )


def check_citation(law, c: dict, on: str) -> str:
    """'ok' | 'fabricated' | 'misgrounded' | 'ungrounded' for one citation, judged on the decision date `on`."""
    act, art, quote = str(c.get("act") or ""), str(c.get("article") or ""), str(c.get("quote") or "")
    if not squash(quote):
        return "ungrounded"
    key = law.find_act(act) if act else None
    if not key:
        return "fabricated"
    in_force, edition = law.in_force(key, on)
    if edition is None or not in_force:
        return "misgrounded"
    path = _path(art)
    unit = law.get_unit(key, path, on)
    if not unit or not unit.get("text"):
        return "misgrounded" if _ever_had(law, key, path) else "fabricated"
    return "ok" if squash(quote) in squash(unit["text"]) else "fabricated"


def citation_gate(law, pred: dict, instance: dict) -> dict:
    n = Counter()
    for d in pred["defects"]:
        if squash(d["evidence_quote"]) not in squash(instance["text"]) or not squash(d["evidence_quote"]):
            n["fabricated_evidence"] += 1
        if not d["citations"]:
            n["ungrounded"] += 1
        for c in d["citations"]:
            n["citations"] += 1
            r = check_citation(law, c, instance["date"])
            n[r] += 1
    bad = n["fabricated"] + n["misgrounded"] + n["ungrounded"] + n["fabricated_evidence"]
    return {"counts": dict(n), "pass": bad == 0}


def grade_one(law, instance: dict, gold: dict, raw) -> dict:
    split = gold["split"]
    base = {"id": instance["id"], "split": split, "family": gold["family"]}
    pred = parse_prediction(raw) if raw is not None else None
    if pred is None:
        return {
            **base,
            "resolved": False,
            "reason": "no prediction" if raw is None else "malformed",
            "gate": False,
            "counts": {},
            "has_pred": False,
            "false_alarm": False,
            "located": False,
        }
    gate = citation_gate(law, pred, instance)
    types = {d["type"] for d in pred["defects"]}
    if gold["verdict"] == "positive":  # CLEAN: PASS_TO_PASS
        test = pred["verdict"] == "positive" and not pred["defects"]
        false_alarm = not test
        located = False
    else:  # REAL / SMITH: FAIL_TO_PASS
        want = set(gold["defect_types"])
        match = bool(pred["defects"]) if "any" in want else bool(types & want)
        test = pred["verdict"] != "positive" and match
        false_alarm = False
        span = squash(gold.get("span") or "")
        located = bool(span) and any(
            squash(d["evidence_quote"])
            and (squash(d["evidence_quote"]) in span or span in squash(d["evidence_quote"]))
            for d in pred["defects"]
        )
    resolved = test and gate["pass"]
    reason = (
        "ok" if resolved else ("citation gate" if test else ("false alarm" if false_alarm else "test failed"))
    )
    return {
        **base,
        "resolved": resolved,
        "reason": reason,
        "gate": gate["pass"],
        "test": test,
        "counts": gate["counts"],
        "has_pred": True,
        "false_alarm": false_alarm,
        "located": located,
        "n_defects": len(pred["defects"]),
    }


def read_run(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(o, dict) and isinstance(o.get("id"), str):
                out[o["id"]] = o
    return out


def collect(splits: tuple[str, ...], private: bool) -> list[tuple[dict, dict, str]]:
    items = []
    for s in splits:
        items += [(i, g, "public") for i, g in load(s)]
        if private:
            items += [(i, g, "private") for i, g in load(s, private=True)]
    return items


def grade_run(law, items, run: dict) -> list[dict]:
    rows = []
    for ins, gold, part in items:
        r = grade_one(law, ins, gold, run.get(ins["id"]))
        rows.append({**r, "part": part})
    return rows


def pass_hat_k(per_run: list[list[dict]]) -> dict[int, float]:
    """tau-bench pass^k: mean over instances of C(c, k) / C(n, k), c = runs that resolved it, n = number of runs."""
    n = len(per_run)
    ids = [r["id"] for r in per_run[0]]
    c = {i: sum(1 for run in per_run if next(x for x in run if x["id"] == i)["resolved"]) for i in ids}
    return (
        {k: sum(math.comb(c[i], k) / math.comb(n, k) for i in ids) / len(ids) for k in range(1, n + 1)}
        if ids
        else {}
    )


def summarise(rows: list[dict]) -> dict:
    """Per split and overall numbers for one run (see the module docstring for every definition)."""
    out: dict = {"splits": {}}
    for s in SPLITS:
        r = [x for x in rows if x["split"] == s]
        if not r:
            continue
        cc = Counter()
        for x in r:
            cc.update(x["counts"])
        n_pred = sum(1 for x in r if x["has_pred"])
        out["splits"][s] = {
            "n": len(r),
            "resolved": sum(x["resolved"] for x in r),
            "predicted": n_pred,
            "false_alarm": sum(x["false_alarm"] for x in r) if s == "clean" else None,
            "gate_pass": sum(x["gate"] for x in r if x["has_pred"]),
            "located": sum(x["located"] for x in r),
            "citations": cc["citations"],
            "cit_ok": cc["ok"],
            "fabricated": cc["fabricated"] + cc["fabricated_evidence"],
            "misgrounded": cc["misgrounded"],
            "ungrounded": cc["ungrounded"],
            "by_family": {
                f: [sum(x["resolved"] for x in r if x["family"] == f), sum(1 for x in r if x["family"] == f)]
                for f in sorted({x["family"] for x in r})
            },
        }
    sp = out["splits"]
    rates = [v["resolved"] / v["n"] for k, v in sp.items() if k in ("real", "smith", "clean") and v["n"]]
    out["macro_resolved"] = sum(rates) / len(rates) if rates else 0.0
    out["f2p"] = [
        sum(sp[k]["resolved"] for k in ("real", "smith") if k in sp),
        sum(sp[k]["n"] for k in ("real", "smith") if k in sp),
    ]
    return out


def report(name: str, summ: dict, extra: str = "") -> None:
    print(f"\n== {name} {extra}")
    for s, v in summ["splits"].items():
        line = f"  {s:6} resolved {pct(v['resolved'], v['n'])}"
        if v["false_alarm"] is not None:
            line += f" | false alarm {pct(v['false_alarm'], v['n'])}"
        print(line)
        cit = (
            f"citations {v['cit_ok']}/{v['citations']} valid, fabricated {v['fabricated']}, misgrounded {v['misgrounded']}, "
            f"ungrounded {v['ungrounded']}; instances passing the gate {v['gate_pass']}/{v['predicted']}"
        )
        print(f"         {cit}")
        if s == "smith":
            print(
                "         by family: "
                + ", ".join(f"{f} {a}/{b}" for f, (a, b) in v["by_family"].items())
                + f" | defect located in the injected span {v['located']}/{v['n']}"
            )
    k, n = summ["f2p"]
    print(
        f"  REAL+SMITH fail-to-pass {pct(k, n)} | macro over real/smith/clean {100 * summ['macro_resolved']:.1f}%"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="run files (one or more; k files give pass^k)")
    ap.add_argument("--split", default="")
    ap.add_argument("--public-only", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument(
        "--save",
        action="store_true",
        help="write data/bench/audit_v1/results/<name>.json for the leaderboard",
    )
    a = ap.parse_args()
    from mezon.lawstore.store import LawStore

    law = LawStore()
    splits = (a.split,) if a.split else SPLITS
    items = collect(splits, private=not a.public_only)
    per_run = [grade_run(law, items, read_run(Path(p))) for p in a.runs]
    summs = [summarise(rows) for rows in per_run]
    name = a.name or Path(a.runs[0]).stem
    for p, s in zip(a.runs, summs):
        report(
            Path(p).name,
            s,
            f"(public {sum(1 for _, _, x in items if x == 'public')} + private "
            f"{sum(1 for _, _, x in items if x == 'private')})",
        )
    ph = (
        pass_hat_k(per_run)
        if len(per_run) > 1
        else {1: sum(x["resolved"] for x in per_run[0]) / max(len(items), 1)}
    )
    print("\npass^k over all instances: " + ", ".join(f"k={k} {100 * v:.1f}%" for k, v in ph.items()))
    if a.save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{name}.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "runs": len(per_run),
                    "summary": summs[0],
                    "pass_hat_k": ph,
                    "n_items": len(items),
                },
                indent=1,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
