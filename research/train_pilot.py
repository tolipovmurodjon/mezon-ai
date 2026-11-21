"""Karpathy's first check for Mezon-LM: can QLoRA overfit 50 SFT examples? (box only, GPU)

    python -X utf8 -m research.train_pilot --model /path/to/qwen --n 50 --epochs 8

What "pass" means: the training loss on the 50 examples falls below 30 % of its first value, the adapter saves and
loads, and one generated answer is valid JSON in our format. If this fails, nothing bigger is worth running.
Settings: 4-bit NF4 base, bf16 compute, LoRA r=16 alpha=32 dropout 0.05 on all linear layers, lr 1e-4, loss on the
assistant answer only (the prompt tokens are masked with -100). Hard stop if any exam decision is in the data.
Needs: torch, transformers, peft, bitsandbytes (uv add on the box). Never run while the owner needs the GPU.
"""

import argparse
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SFT = ROOT / "data" / "train" / "sft.jsonl"
BENCH = ROOT / "data" / "eval" / "mezon_bench_v0.jsonl"
OUT = ROOT / "data" / "models" / "pilot"


def exam_regs() -> set[str]:
    regs = set()
    for line in BENCH.open(encoding="utf-8"):
        g = json.loads(line)["gold"]
        regs.update(g.get("reg_numbers") or [])
        if g.get("reg_number"):
            regs.add(g["reg_number"])
    return regs


def load(n: int) -> list[dict]:
    rows = [json.loads(line) for line in SFT.open(encoding="utf-8")]
    exam = exam_regs()
    leaks = [r for r in rows if any(reg in r["messages"][1]["content"] for reg in exam)]
    assert not leaks, f"{len(leaks)} SFT examples mention an exam decision: fix data/train before training"
    flagged = [r for r in rows if json.loads(r["messages"][2]["content"])["kamchiliklar"]]
    clean = [r for r in rows if r not in flagged]
    rng = random.Random(0)
    return rng.sample(flagged, min(n // 2, len(flagged))) + rng.sample(clean, n - min(n // 2, len(flagged)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--max-chars", type=int, default=2500, help="cut the decision text in the question, never the answer")
    a = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(a.model)
    data = []
    for r in load(a.n):
        user = r["messages"][1]["content"]
        if len(user) > a.max_chars:  # keep the head of the decision and the closing instruction
            r["messages"][1]["content"] = user[: a.max_chars] + "\n[…]\n\nQarorni tekshiring."
        # Split the rendered chat at the LAST assistant header: everything before it is masked, the answer (incl. any
        # thinking block the template inserts) is learned. Robust to templates that render the answer differently.
        text = tok.apply_chat_template(r["messages"], tokenize=False)
        head = "<|im_start|>assistant\n"
        cut = text.rfind(head)
        if cut < 0:
            raise SystemExit("chat template has no assistant header")
        prompt = tok(text[: cut + len(head)], add_special_tokens=False)["input_ids"]
        answer = tok(text[cut + len(head):], add_special_tokens=False)["input_ids"]
        full = (prompt + answer)[: a.max_len]
        labels = ([-100] * len(prompt) + answer)[: a.max_len]
        if all(x == -100 for x in labels):
            continue  # prompt alone fills max_len: nothing to learn from this example
        data.append((torch.tensor([full]), torch.tensor([labels[: len(full)]])))
    print(f"{len(data)} examples, tokens: {sum(x.shape[1] for x, _ in data)}", flush=True)

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    try:  # Qwen3.8-27B ships as Qwen3_5ForConditionalGeneration (text + vision tower)
        model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb, torch_dtype=torch.bfloat16,
                                                     device_map={"": 0})
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(a.model, quantization_config=bnb,
                                                            torch_dtype=torch.bfloat16, device_map={"": 0})
    # Not prepare_model_for_kbit_training: it upcasts every non-quantized weight (incl. the ~248K-token embedding and
    # head) to fp32, which ran a 27B pilot out of the L40S's 44 GB. Keep bf16, checkpoint activations instead.
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear",
                                             exclude_modules=r".*(visual|vision).*", task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    model.train()  # from_pretrained returns eval mode, where checkpointing is skipped: 2,048 tokens ran out of 44 GB
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4, weight_decay=0.0)
    first, t0, history = None, time.time(), []
    for ep in range(a.epochs):
        random.Random(ep).shuffle(data)
        total = 0.0
        for ids, labels in data:
            loss = model(input_ids=ids.cuda(), labels=labels.cuda()).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            opt.zero_grad()
            total += loss.item()
        mean = total / len(data)
        first = first or mean
        history.append(round(mean, 4))
        print(f"epoch {ep + 1}: loss {mean:.4f}  ({mean / first:.0%} of first)  "
              f"vram {torch.cuda.max_memory_allocated() / 1e9:.1f} GB  {time.time() - t0:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT)
    ok = history[-1] < 0.3 * history[0]
    (OUT / "pilot_result.json").write_text(json.dumps({"loss_by_epoch": history, "pass": ok, "n": len(data)}),
                                           encoding="utf-8")
    print("PILOT", "PASS" if ok else "FAIL", history)


if __name__ == "__main__":
    main()
