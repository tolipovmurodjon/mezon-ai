"""MezonBench with tools: the model may call the date-aware law tools (mezon/tools.py) before answering.

    python -X utf8 research/bench_tools_run.py --model ~/models/Qwen3.8-27B --out data/bench/preds_base_tools.jsonl \
        [--adapter data/models/cpt_v11/final] [--per-family 30]

The real competitor of a fine-tuned model is the base model WITH tools (the product always has them), so this
answers "is training worth it?". Qwen's own tool-calling chat template (tools=TOOLS); each <tool_call> is run against
the local law store (data/store/laws.sqlite) and returned as a tool message; at most 4 tool rounds, then the answer.
Writes one line per item: answer, the tool calls made, seconds. Resumable. Score with research.mezonbench score.
Nothing leaves the machine.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _decision_store():
    try:
        from mezon.decisions.store import DecisionStore
        return DecisionStore()
    except (ImportError, OSError, RuntimeError):  # no decision store on this machine
        return None


DEC = _decision_store()
BENCH = ROOT / "data" / "bench" / "mezonbench_v1.jsonl"
CALL = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
FUNC = re.compile(r"<function=([\w-]+)>(.*?)</function>", re.DOTALL)
PARAM = re.compile(r"<parameter=([\w-]+)>\s*(.*?)\s*</parameter>", re.DOTALL)
HINT = ("\nSizda qonun bazasi vositalari bor (law_as_of: modda matni berilgan sanada; list_editions; search_law; "
        "verify_quote). Kerak bo'lsa ulardan foydalaning, so'ng faqat so'ralgan shaklda javob bering.")


def parse_call(body: str) -> tuple[str, dict]:
    """One tool call: Qwen3.5-style XML (<function=name><parameter=k>v</parameter>) or JSON {"name", "arguments"}."""
    m = FUNC.search(body)
    if m:
        return m.group(1), dict(PARAM.findall(m.group(2)))
    try:
        c = json.loads(body.strip())
        return c.get("name", ""), c.get("arguments", {}) or {}
    except json.JSONDecodeError:
        return "bad_json", {}


def load_model(model_path: str, adapter: str = ""):
    """(tok, model) on GPU 0, bf16, optional LoRA adapter."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_path)
    kw = {"torch_dtype": torch.bfloat16, "device_map": {"": 0}}
    try:
        model = AutoModelForCausalLM.from_pretrained(model_path, **kw)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(model_path, **kw)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tok, model


def make_generate(model, tok, sample: bool = False, temperature: float = 1.0, top_p: float = 0.95, max_new: int = 320):
    """generate(texts) -> raw completions (cut at <|im_end|>). Left-padded batch; greedy unless sample=True."""
    import torch

    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    def generate(texts: list[str]) -> list[str]:
        ids = tok(texts, return_tensors="pt", padding=True).to(model.device)
        kw = {"do_sample": True, "temperature": temperature, "top_p": top_p} if sample else {"do_sample": False}
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=max_new, pad_token_id=tok.pad_token_id, **kw)
        n = ids["input_ids"].shape[1]
        out = []
        for row in gen:
            raw = tok.decode(row[n:], skip_special_tokens=False).split("<|im_end|>")[0]
            out.append(raw.replace(tok.pad_token, "") if tok.pad_token else raw)
        return out

    return generate


def run_tool_loops(msgs_list: list[list[dict]], generate, tok, law, rounds: int = 4) -> list[dict]:
    """The tool loop of this benchmark for a batch of conversations, stepped in lockstep.

    Each round every unfinished conversation is rendered with the Qwen tool template (tools=TOOLS), generated, and its
    <tool_call>s (at most 2) are run against the law store. After `rounds` tool rounds one more turn may still call
    tools; the last turn has no tools and asks for the answer only (`forced` = True). Returns, per conversation:
    {"answer", "calls", "messages" (input + tool calls/responses + final assistant answer), "forced"}.
    """
    from mezon import tools

    msgs_list = [list(m) for m in msgs_list]
    n = len(msgs_list)
    calls: list[list[dict]] = [[] for _ in range(n)]
    answers = [""] * n
    forced = [False] * n
    done = [False] * n
    for rnd in range(rounds + 2):
        last = rnd == rounds + 1
        act = [i for i in range(n) if not done[i]]
        if not act:
            break
        texts = []
        for i in act:
            if last:
                forced[i] = True
                msgs_list[i].append({"role": "user", "content": "Endi vositalarsiz, faqat so'ralgan shaklda yakuniy javobni yozing."})
            texts.append(tok.apply_chat_template(msgs_list[i], tools=None if last else tools.TOOLS, tokenize=False,
                                                 add_generation_prompt=True, enable_thinking=False))
        raws = generate(texts)
        for i, raw in zip(act, raws):
            found = [] if last else CALL.findall(raw)
            if not found:
                answers[i] = re.sub(r"<[^>]+>", "", raw.split("</think>")[-1]).strip()
                msgs_list[i].append({"role": "assistant", "content": answers[i]})
                done[i] = True
                continue
            tcs, results = [], []
            for js in found[:2]:
                name, args = parse_call(js)
                res = tools.call(name, args, law, DEC) if name != "bad_json" else {"error": "tool call was not JSON"}
                calls[i].append({"name": name, "args": args, "ok": "error" not in res})
                tcs.append({"type": "function", "function": {"name": name, "arguments": args}})
                results.append(json.dumps(res, ensure_ascii=False)[:4000])
            msgs_list[i].append({"role": "assistant", "content": "", "tool_calls": tcs})
            msgs_list[i].extend({"role": "tool", "content": r} for r in results)
    return [{"answer": answers[i], "calls": calls[i], "messages": msgs_list[i], "forced": forced[i]} for i in range(n)]


def balanced_subset(items: list[dict], per_family: int) -> list[dict]:
    """Seeded, balanced by gold answer (the first N of a family can be all "ha": 21 Nov)."""
    import random
    rng = random.Random(5)
    by: dict[tuple[str, str], list] = {}
    for it in items:
        by.setdefault((it["family"], str(it["answer"])[:4] if it["family"] != "lookup" else ""), []).append(it)
    keep: list[dict] = []
    for fam in dict.fromkeys(it["family"] for it in items):
        groups = [g for (f, _), g in by.items() if f == fam]
        for g in groups:
            rng.shuffle(g)
        k = 0
        while sum(1 for x in keep if x["family"] == fam) < per_family and any(len(g) > k for g in groups):
            for g in groups:
                if len(g) > k and sum(1 for x in keep if x["family"] == fam) < per_family:
                    keep.append(g[k])
            k += 1
    return keep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bench", default=str(BENCH), help="items file (default MezonBench v1)")
    ap.add_argument("--per-family", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=4)
    a = ap.parse_args()

    from mezon.lawstore.store import LawStore

    law = LawStore()
    tok, model = load_model(a.model, a.adapter)
    generate = make_generate(model, tok)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").split("\n") if x.strip()} if out.exists() else set()
    items = [json.loads(x) for x in Path(a.bench).read_text(encoding="utf-8").split("\n") if x.strip()]
    if a.per_family:
        items = balanced_subset(items, a.per_family)
    t_all = time.time()
    with out.open("a", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            if it["id"] in done:
                continue
            msgs = [{"role": "system", "content": it["system"] + HINT}, {"role": "user", "content": it["prompt"]}]
            t0 = time.time()
            r = run_tool_loops([msgs], generate, tok, law, a.rounds)[0]
            f.write(json.dumps({"id": it["id"], "answer": r["answer"], "calls": r["calls"],
                                "seconds": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
            f.flush()
            if n % 20 == 0:
                print(f"{n}/{len(items)} done, {time.time() - t_all:.0f}s", flush=True)
    print(f"TOOLS BENCH DONE {out} in {time.time() - t_all:.0f}s", flush=True)


if __name__ == "__main__":
    main()
