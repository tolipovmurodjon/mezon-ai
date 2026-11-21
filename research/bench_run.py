"""Run a local Qwen (optionally with a LoRA adapter) on MezonBench, closed book, and write predictions.

    python -X utf8 research/bench_run.py --model ~/models/Qwen3.8-27B --out data/bench/preds_base.jsonl
    python -X utf8 research/bench_run.py --model ~/models/Qwen3.8-27B --adapter data/models/sft/final \
        --out data/bench/preds_sft1.jsonl
    python -X utf8 research/bench_run.py ... --think          # thinking mode on (slower; reasoning test)

Runs on the 6000 with the training venv. One item at a time (the hybrid linear-attention layers and left padding
are not worth the risk for 400 short answers). Resumable: items already in --out are skipped. Score on any machine
with `python -m research.mezonbench score <out>`. Nothing leaves the machine.
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # run as a file (python research/x.py) the research package must still import
BENCH = ROOT / "data" / "bench" / "mezonbench_v1.jsonl"
FORCE = ("\nJavob berish majburiy: \"noaniq\" deb yozmang. Bilmasangiz ham eng ehtimolli javobni "
         "so'ralgan shaklda bering.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bench", default=str(BENCH), help="items file (default MezonBench v1)")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--force", action="store_true", help="forbid 'noaniq': the model must answer (hallucination test)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--per-family", type=int, default=0, help="first N items of each family (balanced sample)")
    a = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.model)
    kw = {"torch_dtype": torch.bfloat16, "device_map": {"": 0}}
    try:
        model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(a.model, **kw)
    if a.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)["id"] for line in out.open(encoding="utf-8")} if out.exists() else set()
    items = [json.loads(line) for line in Path(a.bench).open(encoding="utf-8")]
    if a.per_family:  # the same seeded, answer-balanced sample as the tools exam and the frontier runs
        from research.bench_tools_run import balanced_subset
        items = balanced_subset(items, a.per_family)
    if a.limit:
        items = items[: a.limit]
    t_all = time.time()
    with out.open("a", encoding="utf-8") as f:
        for n, it in enumerate(items, 1):
            if it["id"] in done:
                continue
            msgs = [{"role": "system", "content": it["system"] + (FORCE if a.force else "")}, {"role": "user", "content": it["prompt"]}]
            text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=a.think)
            ids = tok(text, return_tensors="pt").to(model.device)
            # short budget only for one-word answers (v1 flip / in_force / hierarchy); quotes, act + article, letter +
            # article and dates need room: 24 tokens cut v2.1 chain quotes (60+ chars) mid-word (bug found 21 Nov)
            short = it["family"] in ("flip", "in_force", "hierarchy")
            budget = (3000 if a.think else 0) + (24 if short else 200)
            t0 = time.time()
            with torch.no_grad():
                gen = model.generate(**ids, max_new_tokens=budget, do_sample=False, pad_token_id=tok.eos_token_id)
            raw = tok.decode(gen[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
            answer = raw.split("</think>")[-1].strip()
            f.write(json.dumps({"id": it["id"], "answer": answer, "raw_len": len(raw),
                                "seconds": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
            f.flush()
            if n % 20 == 0:
                print(f"{n}/{len(items)} done, {time.time() - t_all:.0f}s", flush=True)
    print(f"BENCH DONE {out} in {time.time() - t_all:.0f}s", flush=True)


if __name__ == "__main__":
    main()
