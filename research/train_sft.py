"""Mezon-LM SFT run on the RTX PRO 6000 (96 GB): LoRA on Qwen3.8-27B, resumable, checkpoints every N minutes.

    python -X utf8 -m research.train_sft --model ~/models/Qwen3.8-27B            # starts or resumes
    python -X utf8 -m research.train_sft --model ... --bits 4                     # QLoRA (fits a 48 GB card)

Built on research/train_pilot.py (the pilot passed 20.11: loss 0.2532 -> 0.0046 on 50 examples). Same rules: loss on
the assistant answer only, exam decisions must not appear in the data (hard stop), vision tower not trained.
New here: all of data/train/sft.jsonl with a fixed 10 % held-out split (validation loss = the honest number), bf16
LoRA by default (the 6000 has the memory), gradient accumulation, warmup + cosine learning rate, and a checkpoint
(adapter + optimizer + position) every --save-every-min minutes into data/models/sft/latest, so a spot interruption
loses at most that much. Results: data/models/sft/final + sft_result.json. Copy checkpoints off the machine
(scripts/sft_sync.sh) because a spot machine can be taken back.
"""

import argparse
import json
import math
import random
import shutil
import time
from pathlib import Path

from research.train_pilot import BENCH, SFT, exam_regs  # noqa: F401  (BENCH documents where the exam lives)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "models" / "sft"


def split_rows(val_share: float) -> tuple[list[dict], list[dict]]:
    rows = [json.loads(line) for line in SFT.open(encoding="utf-8")]
    exam = exam_regs()
    leaks = [r for r in rows if any(reg in r["messages"][1]["content"] for reg in exam)]
    assert not leaks, f"{len(leaks)} SFT examples mention an exam decision: fix data/train before training"
    flagged = [r for r in rows if json.loads(r["messages"][2]["content"])["kamchiliklar"]]
    clean = [r for r in rows if not json.loads(r["messages"][2]["content"])["kamchiliklar"]]
    rng = random.Random(0)
    rng.shuffle(flagged)
    rng.shuffle(clean)
    nf, nc = round(len(flagged) * val_share), round(len(clean) * val_share)  # same share of flagged and clean
    return flagged[nf:] + clean[nc:], flagged[:nf] + clean[:nc]


def encode(tok, rows: list[dict], max_len: int, max_chars: int):
    import torch

    out = []
    for r in rows:
        msgs = [dict(m) for m in r["messages"]]
        if len(msgs[1]["content"]) > max_chars:  # keep the head of the decision and the closing instruction
            msgs[1]["content"] = msgs[1]["content"][:max_chars] + "\n[…]\n\nQarorni tekshiring."
        text = tok.apply_chat_template(msgs, tokenize=False)
        head = "<|im_start|>assistant\n"
        cut = text.rfind(head)
        if cut < 0:
            raise SystemExit("chat template has no assistant header")
        prompt = tok(text[: cut + len(head)], add_special_tokens=False)["input_ids"]
        answer = tok(text[cut + len(head):], add_special_tokens=False)["input_ids"]
        full = (prompt + answer)[:max_len]
        labels = ([-100] * len(prompt) + answer)[:max_len]
        if all(x == -100 for x in labels):
            continue
        out.append((torch.tensor([full]), torch.tensor([labels[: len(full)]])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--bits", type=int, choices=(4, 16), default=16)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--accum", type=int, default=8, help="examples per optimizer step")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--max-chars", type=int, default=6000, help="cut the decision text in the question, never the answer")
    ap.add_argument("--val-share", type=float, default=0.10)
    ap.add_argument("--save-every-min", type=float, default=30.0)
    ap.add_argument("--limit", type=int, default=0, help="use only N training examples (smoke test)")
    ap.add_argument("--out", default=str(OUT), help="output folder (use a separate one for smoke tests)")
    a = ap.parse_args()
    out = Path(a.out)

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(a.model)
    train_rows, val_rows = split_rows(a.val_share)
    if a.limit:
        train_rows, val_rows = train_rows[: a.limit], val_rows[: max(2, a.limit // 5)]
    train = encode(tok, train_rows, a.max_len, a.max_chars)
    val = encode(tok, val_rows, a.max_len, a.max_chars)
    print(f"train {len(train)} examples / {sum(x.shape[1] for x, _ in train):,} tokens | "
          f"held-out {len(val)} examples", flush=True)

    kw = {"torch_dtype": torch.bfloat16, "device_map": {"": 0}}
    if a.bits == 4:
        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                       bnb_4bit_compute_dtype=torch.bfloat16,
                                                       bnb_4bit_use_double_quant=True)
    try:  # Qwen3.8-27B ships as Qwen3_5ForConditionalGeneration (text + vision tower)
        model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(a.model, **kw)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()

    latest = out / "latest"
    state = {"epoch": 0, "pos": 0, "step": 0, "history": [], "val": []}
    if (latest / "adapter_config.json").exists():
        model = PeftModel.from_pretrained(model, latest, is_trainable=True)
        state = json.loads((latest / "state.json").read_text(encoding="utf-8"))
        print(f"resuming from step {state['step']} (epoch {state['epoch'] + 1}, example {state['pos']})", flush=True)
    else:
        model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05,
                                                 target_modules="all-linear", exclude_modules=r".*(visual|vision).*",
                                                 task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    model.train()  # from_pretrained returns eval mode, where gradient checkpointing is skipped

    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    if (latest / "optimizer.pt").exists():
        opt.load_state_dict(torch.load(latest / "optimizer.pt", map_location="cuda", weights_only=True))
    total_steps = math.ceil(len(train) / a.accum) * a.epochs
    warm = max(1, total_steps // 20)

    def lr_at(step: int) -> float:
        if step < warm:
            return a.lr * (step + 1) / warm
        return a.lr * 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total_steps - warm)))

    def validate() -> float:
        model.eval()
        with torch.no_grad():
            losses = [model(input_ids=x.cuda(), labels=y.cuda()).loss.item() for x, y in val]
        model.train()
        return sum(losses) / max(1, len(losses))

    def save(path: Path) -> None:
        tmp = path.with_name(path.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        model.save_pretrained(tmp)
        torch.save(opt.state_dict(), tmp / "optimizer.pt")
        (tmp / "state.json").write_text(json.dumps(state), encoding="utf-8")
        shutil.rmtree(path, ignore_errors=True)
        tmp.rename(path)  # never leave a half-written checkpoint as "latest"

    out.mkdir(parents=True, exist_ok=True)
    if not state["val"]:
        state["val"].append({"step": 0, "val_loss": round(validate(), 4)})
        print(f"held-out loss before training: {state['val'][0]['val_loss']}", flush=True)
    t0 = last_save = time.time()
    for ep in range(state["epoch"], a.epochs):
        order = list(range(len(train)))
        random.Random(1000 + ep).shuffle(order)
        run, n = 0.0, 0
        for i in range(state["pos"], len(order)):
            x, y = train[order[i]]
            loss = model(input_ids=x.cuda(), labels=y.cuda()).loss / a.accum
            loss.backward()
            run += loss.item() * a.accum
            n += 1
            if (i + 1) % a.accum == 0 or i + 1 == len(order):
                for g in opt.param_groups:
                    g["lr"] = lr_at(state["step"])
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                opt.step()
                opt.zero_grad()
                state["step"] += 1
                if state["step"] % 10 == 0:
                    print(f"epoch {ep + 1} step {state['step']}/{total_steps} train loss {run / n:.4f} "
                          f"lr {lr_at(state['step']):.2e} vram {torch.cuda.max_memory_allocated() / 1e9:.1f} GB "
                          f"{(time.time() - t0) / 60:.0f} min", flush=True)
            state["pos"] = i + 1
            if time.time() - last_save > a.save_every_min * 60:
                save(latest)
                last_save = time.time()
                print(f"checkpoint saved at step {state['step']}", flush=True)
        state["history"].append(round(run / max(1, n), 4))
        state["epoch"], state["pos"] = ep + 1, 0
        v = validate()
        state["val"].append({"step": state["step"], "val_loss": round(v, 4)})
        print(f"epoch {ep + 1} done: train {state['history'][-1]} | held-out {v:.4f}", flush=True)
        save(latest)
        last_save = time.time()
    save(out / "final")
    result = {"train_loss_by_epoch": state["history"], "held_out": state["val"], "train_examples": len(train),
              "held_out_examples": len(val), "bits": a.bits, "rank": a.rank, "lr": a.lr, "epochs": a.epochs,
              "minutes": round((time.time() - t0) / 60, 1)}
    (out / "sft_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("SFT DONE", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
