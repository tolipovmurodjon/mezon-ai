"""Run a model (or a baseline) over MezonAudit-bench and write predictions in the grader's JSON schema.

    # baselines, no model, no GPU (these are what the leaderboard prints first)
    .venv/Scripts/python.exe -X utf8 -m research.audit_bench.harness --mode oracle --out data/bench/audit_v1/runs/oracle.jsonl
    ... --mode empty | always-negative | always-positive | engine
    # local Qwen with the five law tools (GPU box only; imports research.bench_tools_run, nothing leaves the machine)
    python -X utf8 -m research.audit_bench.harness --mode local --model ~/models/Qwen3.8-27B --out ...runs/qwen_run1.jsonl
    # a frontier model through the Claude CLI: DISABLED. Decision texts would leave the machine.
    python -X utf8 -m research.audit_bench.harness --mode cloud --allow-cloud --out ...     # only with Boss's explicit yes

The prediction schema is defined in research/audit_bench/grade.py. Every run file is resumable (finished ids are
skipped). Splits: public and private are both run by default (--public-only to skip the private 30 %).
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mezon.report import verdict_for
from mezon.rules import basis, business, form
from mezon.rules.common import SafeLaw, cite, clip, operative_clauses, preamble
from mezon.verify import verify_flag
from research.audit_bench.grade import SPLITS, TYPES
from research.audit_bench.instances import load

RUNS = ROOT / "data" / "bench" / "audit_v1" / "runs"
MAX_CHARS = 30000
BASELINES = ("oracle", "empty", "always-negative", "always-positive", "engine")

SYSTEM = """You are a legal reviewer at the Ministry of Justice (Adliya) of Uzbekistan. You review one local decision (hokim or
Kengash) and write the Adliya conclusion: exactly one of
  positive                        - no defect found
  positive_with_fixable_defects   - defects that can be fixed before or after adoption
  negative                        - a defect that makes the decision unlawful to adopt as written
You say "possible violation, for expert review", never "illegal". Decide from the decision text and the law as it read ON THE
DECISION DATE. Use the law tools (law_as_of, list_editions, search_law, verify_quote, get_decision) before you cite anything.
Never cite an act, article or quote you did not read through a tool: a wrong citation fails the whole review.

Defect types (use only these):
  form_farmoyish     a normative act issued as a farmoyish (NLA art. 16): binding norms must be a qaror
  business_3m        a burden on business takes effect less than 3 months after publication (NLA art. 40)
  dead_citation      the preamble rests on an article or act that was no longer in force on the decision date
  duplicate_clause   a clause copied from an earlier decision of the same body that is still in force (NLA art. 46)
  retroactive        the decision takes effect before its adoption date and adds a burden (NLA art. 41)
  double_repeal      it repeals a decision that was already repealed
  other              any other possible violation (say which in evidence_quote's clause)
A decision can also be fine. Do not invent defects: a false alarm costs as much as a miss.

Answer with ONE JSON object and nothing else:
{"verdict": "...", "defects": [{"type": "...", "clause": <number or null>,
  "evidence_quote": "<word for word from the decision>",
  "citations": [{"act": "<number or title>", "article": "<e.g. 40 or art:40/part:2>",
                 "quote": "<word for word from that article's text>", "on_date": "<decision date>"}]}]}
Every defect needs at least one citation. For "positive", defects is []."""


# ---------------------------------------------------------------- prompts and parsing


def build_prompt(ins: dict) -> tuple[str, bool]:
    text = ins["text"]
    cut = len(text) > MAX_CHARS
    if cut:
        text = text[: MAX_CHARS // 2] + "\n[... text cut ...]\n" + text[-MAX_CHARS // 2 :]
    return (
        f"Decision {ins['reg_number']} dated {ins['date']}. Title: {ins['title']}\n"
        f"Review it as the law read on {ins['date']}.\n\n--- DECISION TEXT ---\n{text}\n--- END ---"
    ), cut


def extract_json(answer: str) -> dict | None:
    """The last top-level JSON object in the model's answer (it may think aloud or fence the JSON)."""
    s = re.sub(r"```(?:json)?", "", answer)
    best = None
    for m in re.finditer(r"\{", s):
        depth, i = 0, m.start()
        while i < len(s):
            depth += {"{": 1, "}": -1}.get(s[i], 0)
            if depth == 0:
                break
            i += 1
        if depth == 0:
            try:
                obj = json.loads(s[m.start() : i + 1])
                if isinstance(obj, dict) and "verdict" in obj:
                    best = obj
            except json.JSONDecodeError:
                pass
    return best


class BenchDecisions:
    """get_decision for the tool loop: the instance's own text (mutated for SMITH) and earlier ADOPTED decisions only.
    Cancelling acts are never served, so a model can't read its way to the answer."""

    def __init__(self, instances: list[dict]):
        from mezon.decisions.store import DecisionStore

        self.ds = DecisionStore()
        self.own = {i["reg_number"]: i for i in instances}

    def get(self, reg: str) -> dict | None:
        i = self.own.get(reg)
        if i:
            d = {"reg": reg, "date": i["date"], "title": i["title"], "text": i["text"], "url": ""}
        else:
            ids = [x for x in self.ds.by_reg(reg) if x.startswith("lex:")]
            row = self.ds.get(ids[0]) if ids else None
            if not row or row["role"] != "adopted":
                return None
            d = {
                "reg": reg,
                "date": row["adopted"],
                "title": row["title"],
                "text": row["text"] or "",
                "url": row["url"] or "",
            }
        return {
            "reg": d["reg"],
            "date": d["date"],
            "title": d["title"],
            "url": d["url"],
            "preamble": clip(preamble(d["text"]), 2500),
            "clauses": [[n, clip(c, 700)] for n, c in operative_clauses(d["text"])[:30]],
        }


# ---------------------------------------------------------------- baselines

ORACLE_CITE = {  # defect type -> (law ref in mezon.rules.common.LAW, unit, quote needle)
    "form_farmoyish": ("nla", "art:16", None),
    "business_3m": ("nla", "art:40/part:2", "uch oy"),
    "retroactive": ("nla", "art:41/part:1", "orqaga"),
    "dead_citation": ("nla", "art:18/part:3", None),
    "duplicate_clause": ("nla", "art:46/part:1", None),
    "double_repeal": ("o3333", "annex:1/cl:51", "kuchini"),
    "any": ("nla", "art:18/part:3", None),
}


def _cit(law: SafeLaw, ref: str, unit: str, needle, on: str) -> dict:
    c = cite(law, ref, unit, on, needle)
    return {"act": c.act_id, "article": c.article, "quote": c.quote, "on_date": on}


def cheap_defect(ins: dict, law: SafeLaw, typ: str) -> dict:
    """The cheapest well-formed defect: a verbatim quote from the first clause and one valid generic citation."""
    cl = operative_clauses(ins["text"])
    quote = clip(cl[0][1], 160) if cl else clip(ins["text"][:160])
    ref, unit, needle = ORACLE_CITE.get(typ, ORACLE_CITE["any"])
    return {
        "type": typ,
        "clause": cl[0][0] if cl else None,
        "evidence_quote": quote,
        "citations": [_cit(law, ref, unit, needle, ins["date"])],
    }


def predict_baseline(mode: str, ins: dict, gold: dict, law: SafeLaw) -> dict | None:
    if mode == "empty":
        return None
    if mode == "always-positive":
        return {"id": ins["id"], "verdict": "positive", "defects": []}
    if mode == "always-negative":
        return {"id": ins["id"], "verdict": "negative", "defects": [cheap_defect(ins, law, "other")]}
    if mode == "oracle":
        if gold["verdict"] == "positive":
            return {"id": ins["id"], "verdict": "positive", "defects": []}
        typ = gold["defect_types"][0]
        d = cheap_defect(ins, law, "other" if typ == "any" else typ)
        if typ == "any":
            d["type"] = "other"
        elif gold.get("span"):
            d["evidence_quote"] = clip(gold["span"], 240)
        return {"id": ins["id"], "verdict": "negative", "defects": [d]}
    if mode == "engine":
        return engine_prediction(ins, law)
    raise ValueError(mode)


ENGINE_TYPE = {
    "R_form": "form_farmoyish",
    "R_business_3m": "business_3m",
    "R_retroactive": "retroactive",
    "R_basis": "dead_citation",
}


def engine_prediction(ins: dict, law: SafeLaw) -> dict:
    """The offline rule engine's own answer: business, form and basis rules on the text (duplicate / double-repeal rules
    need the store's same-body index and are not run here, so SMITH duplicate_clause / double_repeal are out of its reach)."""
    d = {
        "id": ins["id"],
        "text": ins["text"],
        "type": ins["type"],
        "adopted": ins["date"],
        "reg_number": ins["reg_number"],
        "title": ins["title"],
        "role": "adopted",
        "source": "lex.uz",
        "url": "",
        "stages": {},
        "is_normative": None,
    }
    flags = []
    for fn in (business.check, form.check, basis.check):
        for f in fn(d, law):
            kept, _ = verify_flag(f, d, law, None)
            if kept:
                flags.append(kept)
    defects = []
    for f in flags:
        quote = f.evidence[0].quote if f.evidence else ""
        defects.append(
            {
                "type": ENGINE_TYPE.get(f.check, "other"),
                "clause": None,
                "evidence_quote": quote,
                "citations": [
                    {"act": c.act_id, "article": c.article, "quote": c.quote, "on_date": c.on_date}
                    for c in f.citations
                ],
            }
        )
    return {"id": ins["id"], "verdict": verdict_for(flags), "defects": defects}


# ---------------------------------------------------------------- local model (GPU box)


def to_prediction(iid: str, answer: str, calls: list, cut: bool) -> dict | None:
    obj = extract_json(answer)
    if obj is None:
        return None
    for d in obj.get("defects") or []:
        if isinstance(d, dict) and str(d.get("type", "")).lower() not in TYPES:
            d["type"] = "other"
    return {
        "id": iid,
        "verdict": obj.get("verdict"),
        "defects": obj.get("defects") or [],
        "calls": calls,
        "truncated": cut,
    }


def run_local(
    items: list[tuple[dict, dict]], model: str, adapter: str, out: Path, rounds: int, batch: int
) -> None:
    from mezon import tools
    from mezon.lawstore.store import LawStore
    from research.bench_tools_run import load_model, make_generate, run_tool_loops

    law = LawStore()
    tok, mdl = load_model(model, adapter)
    generate = make_generate(mdl, tok, max_new=900)
    bd = BenchDecisions([i for i, _ in items])
    orig = tools.call
    tools.call = lambda name, args, law_, decisions=None: orig(
        name, args, law_, decisions or bd
    )  # decision lookups
    try:
        _drive(items, lambda msgs: run_tool_loops(msgs, generate, tok, law, rounds), out, batch)
    finally:
        tools.call = orig


def _drive(items, loop, out: Path, batch: int) -> None:
    done = (
        {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
        if out.exists()
        else set()
    )
    todo = [(i, g) for i, g in items if i["id"] not in done]
    t0 = time.time()
    with out.open("a", encoding="utf-8") as f:
        for b in range(0, len(todo), batch):
            chunk = todo[b : b + batch]
            prompts = [build_prompt(i) for i, _ in chunk]
            msgs = [
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": p}] for p, _ in prompts
            ]
            for (ins, _), (_, cut), r in zip(chunk, prompts, loop(msgs)):
                pred = to_prediction(ins["id"], r["answer"], r["calls"], cut) or {
                    "id": ins["id"],
                    "verdict": "",
                    "defects": [],
                    "raw": r["answer"][:500],
                }
                f.write(json.dumps(pred, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{min(b + batch, len(todo))}/{len(todo)} done, {time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- frontier model through the Claude CLI (disabled)


def run_cloud(items: list[tuple[dict, dict]], out: Path, allow: bool, model: str = "") -> None:
    if not allow:
        raise SystemExit(
            "cloud mode is disabled: decision texts would leave this machine. It needs Boss's explicit yes "
            "and the --allow-cloud flag. Nothing was sent."
        )
    from research.frontier_cli import EFFORT, EMPTY, MCP, MODEL

    EMPTY.mkdir(exist_ok=True)
    (EMPTY / "mcp.json").write_text(json.dumps(MCP), encoding="utf-8")
    done = (
        {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
        if out.exists()
        else set()
    )
    with out.open("a", encoding="utf-8") as f:
        for ins, _ in items:
            if ins["id"] in done:
                continue
            prompt, cut = build_prompt(ins)
            cmd = [
                "claude",
                "-p",
                "--model",
                model or MODEL,
                "--effort",
                EFFORT,
                "--tools",
                "",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--no-session-persistence",
                "--output-format",
                "json",
                "--max-turns",
                "12",
                "--system-prompt",
                SYSTEM,
                "--mcp-config",
                str(EMPTY / "mcp.json"),
                "--allowedTools",
                "mcp__mezon__law_as_of,mcp__mezon__list_editions,mcp__mezon__search_law,mcp__mezon__verify_quote",
            ]
            try:
                p = subprocess.run(
                    cmd,
                    input=prompt,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    cwd=tempfile.gettempdir(),
                    timeout=900,
                )
                answer = json.loads(p.stdout).get("result") or ""
            except Exception as e:  # noqa: BLE001 - recorded in the run file, never dropped silently
                answer = f"ERROR {type(e).__name__}: {e}"
            pred = to_prediction(ins["id"], answer, [], cut) or {
                "id": ins["id"],
                "verdict": "",
                "defects": [],
                "raw": answer[:500],
            }
            f.write(json.dumps(pred, ensure_ascii=False) + "\n")
            f.flush()


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=[*BASELINES, "local", "cloud"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="")
    ap.add_argument("--public-only", action="store_true")
    ap.add_argument("--model", default="")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--allow-cloud", action="store_true", help="REQUIRED for --mode cloud; needs Boss's explicit yes"
    )
    a = ap.parse_args()
    if a.mode == "cloud" and not a.allow_cloud:
        raise SystemExit(
            "cloud mode is disabled: decision texts would leave this machine. It needs Boss's explicit yes "
            "and the --allow-cloud flag. Nothing was sent."
        )
    splits = (a.split,) if a.split else SPLITS
    items = []
    for s in splits:
        items += load(s)
        if not a.public_only:
            items += load(s, private=True)
    if a.limit:
        items = items[: a.limit]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.mode in BASELINES:
        from mezon.lawstore.store import LawStore

        law = SafeLaw(LawStore())
        n = 0
        with out.open("w", encoding="utf-8") as f:
            for ins, gold in items:
                pred = predict_baseline(a.mode, ins, gold, law)
                if pred is not None:
                    f.write(json.dumps(pred, ensure_ascii=False) + "\n")
                    n += 1
        print(f"{a.mode}: {n} predictions for {len(items)} instances -> {out}")
    elif a.mode == "local":
        run_local(items, a.model, a.adapter, out, a.rounds, a.batch)
    else:
        run_cloud(items, out, a.allow_cloud)


if __name__ == "__main__":
    main()
