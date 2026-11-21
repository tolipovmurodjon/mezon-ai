"""Law-school pilot (phase 1): LoRA continued pre-training of Qwen3.8-27B on lessons + replay, on the RTX PRO 6000.

    python -X utf8 -m research.train_cpt --model ~/models/Qwen3.8-27B     # data/train/mix_pilot.jsonl, starts or resumes

Rows from research/law_school_mix.py: {"kind": "law"|"web", "text"} are learned whole (every token: reading the
law and Uzbek text); {"kind": "instr", "messages"} learn the assistant's last answer only (keeps the habit of
answering, Tulu 3 replay). LoRA rank 128 on all linear layers (research: low rank learns too little in continued
pre-training; full fine-tuning does not fit 96 GB), one pass, warmup + cosine, checkpoint every 30 min to
data/models/cpt_pilot/latest. Held-out loss per kind (law / web / instr) before and after: law should fall, web and
instr must not rise much (that would be forgetting). Then MezonBench decides (research/bench_run.py).
"""

import argparse
import json
import math
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # run as a file (python research/x.py) the research package must still import
DATA = ROOT / "data" / "train" / "mix_pilot.jsonl"
VAL = ROOT / "data" / "train" / "mix_pilot_val.jsonl"
OUT = ROOT / "data" / "models" / "cpt_pilot"


def encode(tok, row: dict, max_len: int):
    import torch

    if row.get("tools"):  # tool-use traces (internship, strict judge): train every assistant span, mask the rest
        from mezon.tools import TOOLS
        from research.internship_encode import encode_multi, to_tensors

        e = encode_multi(tok, row["messages"], TOOLS, max_len)
        return None if e is None else to_tensors(*e)
    if "text" in row:
        ids = tok(row["text"], add_special_tokens=False)["input_ids"][: max_len - 1] + [tok.eos_token_id]
        return torch.tensor([ids]), torch.tensor([ids])
    text = tok.apply_chat_template(row["messages"], tokenize=False)
    head = "<|im_start|>assistant\n"
    cut = text.rfind(head)
    if cut < 0:
        return None
    prompt = tok(text[: cut + len(head)], add_special_tokens=False)["input_ids"]
    answer = tok(text[cut + len(head):], add_special_tokens=False)["input_ids"]
    if len(prompt) >= max_len - 16:
        return None
    full = (prompt + answer)[:max_len]
    labels = ([-100] * len(prompt) + answer)[:max_len]
    return torch.tensor([full]), torch.tensor([labels])


def read_jsonl(path: str) -> list[dict]:
    """One JSON object per line. Split on newlines only: str.splitlines() also breaks on U+2028/U+0085 inside text."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [json.loads(line) for line in f.read().split("\n") if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--accum", type=int, default=16, help="rows per optimizer step")
    ap.add_argument("--rank", type=int, default=128)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--save-every-min", type=float, default=30.0)
    ap.add_argument("--limit", type=int, default=0, help="smoke test: first N rows")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--val", default=str(VAL))
    ap.add_argument("--init-adapter", default="", help="stack stages: keep training this earlier adapter (e.g. law school)")
    a = ap.parse_args()
    out, latest = Path(a.out), Path(a.out) / "latest"

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.model)
    rows = read_jsonl(a.data)
    if a.limit:
        rows = rows[: a.limit]
    t_enc = time.time()
    train = [e for e in (encode(tok, r, a.max_len) for r in rows) if e is not None]
    val = {}
    for r in read_jsonl(a.val):
        e = encode(tok, r, a.max_len)
        if e is not None:
            val.setdefault(r["kind"], []).append(e)
    if a.limit:
        val = {k: v[:5] for k, v in val.items()}
    ntok = sum(int((y != -100).sum()) for _, y in train)
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"train {len(train):,} rows {kinds} | {ntok:,} trained tokens | encoded in {time.time() - t_enc:.0f}s | "
          f"val {({k: len(v) for k, v in val.items()})}", flush=True)

    kw = {"torch_dtype": torch.bfloat16, "device_map": {"": 0}}
    try:
        model = AutoModelForCausalLM.from_pretrained(a.model, **kw)
    except (ValueError, KeyError):
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(a.model, **kw)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()

    state = {"pos": 0, "step": 0, "val": []}
    if (latest / "adapter_config.json").exists():
        model = PeftModel.from_pretrained(model, latest, is_trainable=True)
        state = json.loads((latest / "state.json").read_text(encoding="utf-8"))
        print(f"resuming from step {state['step']} (row {state['pos']})", flush=True)
    elif a.init_adapter:
        model = PeftModel.from_pretrained(model, a.init_adapter, is_trainable=True)
        print(f"stacking on {a.init_adapter} (fresh optimizer, step 0)", flush=True)
    else:
        model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=a.rank, lora_dropout=0.0,
                                                 target_modules="all-linear", exclude_modules=r".*(visual|vision).*",
                                                 task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    model.train()

    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    if (latest / "optimizer.pt").exists():
        opt.load_state_dict(torch.load(latest / "optimizer.pt", map_location="cuda", weights_only=True))
    total = math.ceil(len(train) / a.accum)
    warm = max(1, total // 20)

    def lr_at(step: int) -> float:
        if step < warm:
            return a.lr * (step + 1) / warm
        return a.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm))))

    def validate() -> dict:
        model.eval()
        res = {}
        with torch.no_grad():
            for k, v in val.items():
                res[k] = round(sum(model(input_ids=x.cuda(), labels=y.cuda()).loss.item() for x, y in v) / len(v), 4)
        model.train()
        return res

    def save(path: Path) -> None:
        tmp = path.with_name(path.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        model.save_pretrained(tmp)
        torch.save(opt.state_dict(), tmp / "optimizer.pt")
        (tmp / "state.json").write_text(json.dumps(state), encoding="utf-8")
        shutil.rmtree(path, ignore_errors=True)
        tmp.rename(path)

    out.mkdir(parents=True, exist_ok=True)
    if not state["val"]:
        state["val"].append({"step": 0, **validate()})
        print(f"held-out loss before: {state['val'][0]}", flush=True)
    order = list(range(len(train)))
    random.Random(5).shuffle(order)
    t0 = last = time.time()
    start_step = state["step"]
    run, n, seen_tok = 0.0, 0, 0
    for i in range(state["pos"], len(order)):
        x, y = train[order[i]]
        loss = model(input_ids=x.cuda(), labels=y.cuda()).loss
        (loss / a.accum).backward()
        run += loss.item()
        n += 1
        seen_tok += int((y != -100).sum())
        if (i + 1) % a.accum == 0 or i + 1 == len(order):
            for g in opt.param_groups:
                g["lr"] = lr_at(state["step"])
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad()
            state["step"] += 1
            if state["step"] % 10 == 0:
                el = time.time() - t0
                print(f"step {state['step']}/{total} loss {run / n:.4f} lr {lr_at(state['step']):.2e} "
                      f"{seen_tok / el:.0f} tok/s vram {torch.cuda.max_memory_allocated() / 1e9:.1f} GB "
                      f"{el / 60:.0f} min, ETA {(total - state['step']) * el / max(1, state['step'] - start_step) / 60:.0f} min",
                      flush=True)
                run, n = 0.0, 0
            if state["step"] % max(1, total // 4) == 0:
                v = validate()
                state["val"].append({"step": state["step"], **v})
                print(f"held-out loss at step {state['step']}: {v}", flush=True)
        state["pos"] = i + 1
        if time.time() - last > a.save_every_min * 60:
            save(latest)
            last = time.time()
            print(f"checkpoint saved at step {state['step']}", flush=True)
    v = validate()
    state["val"].append({"step": state["step"], **v})
    save(latest)
    save(out / "final")
    result = {"rows": len(train), "trained_tokens": ntok, "rank": a.rank, "lr": a.lr, "steps": state["step"],
              "held_out": state["val"], "minutes": round((time.time() - t0) / 60, 1)}
    (out / "cpt_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("CPT DONE", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
