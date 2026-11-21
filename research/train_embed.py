"""Domain fine-tune of bge-m3 on law-store pairs: LoRA + InfoNCE (in-batch + hard negatives), merged and saved (box GPU).

    ~/retr-venv/bin/python -m research.train_embed --pairs data/train/embed_pairs.jsonl --out ~/models/bge-m3-law
Memory-lean on purpose (the L40S is shared with OCR): bf16 base, LoRA r=32, gradient checkpointing.
"""
import argparse, json, random, time
import torch, torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModel, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--bs", type=int, default=32); ap.add_argument("--steps", type=int, default=0)
    ap.add_argument("--lr", type=float, default=1e-4); ap.add_argument("--temp", type=float, default=0.02)
    ap.add_argument("--plen", type=int, default=256)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.pairs, encoding="utf8")]
    random.Random(3).shuffle(rows)
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    base = AutoModel.from_pretrained("BAAI/bge-m3", torch_dtype=torch.bfloat16).cuda()
    base.gradient_checkpointing_enable(); base.enable_input_require_grads()
    model = get_peft_model(base, LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05, target_modules=["query", "key", "value", "dense"]))
    model.print_trainable_parameters()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.01)
    nsteps = a.steps or len(rows) // a.bs
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / (0.05 * nsteps)) * max(0.0, 1 - s / nsteps))

    def enc(texts, ml):
        b = tok(texts, padding=True, truncation=True, max_length=ml, return_tensors="pt").to("cuda")
        h = model(**b).last_hidden_state[:, 0]
        return F.normalize(h.float(), dim=-1)

    model.train(); t0 = time.time(); rng = random.Random(5)
    for step in range(nsteps):
        batch = rows[step * a.bs:(step + 1) * a.bs]
        if len(batch) < a.bs: break
        qs = [r["q"] for r in batch]
        ps = [r["pos"] for r in batch] + [rng.choice(r["negs"]) if r["negs"] else rng.choice(rows)["pos"] for r in batch]
        q = enc(qs, 64); p = enc(ps, a.plen)
        logits = q @ p.T / a.temp
        # a candidate with the same text as the positive (duplicate article in another act) is not a negative
        same = torch.tensor([[ps[j] == batch[i]["pos"] and j != i for j in range(len(ps))] for i in range(len(batch))], device="cuda")
        logits = logits.masked_fill(same, -1e4)
        loss = F.cross_entropy(logits, torch.arange(len(batch), device="cuda"))
        loss.backward(); torch.nn.utils.clip_grad_norm_(params, 1.0); opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
        if step % 50 == 0:
            acc = (logits.argmax(1) == torch.arange(len(batch), device="cuda")).float().mean().item()
            print(f"step {step}/{nsteps} loss {loss.item():.4f} inbatch-acc {acc:.2f} mem {torch.cuda.max_memory_allocated()/1e9:.1f}GB {time.time()-t0:.0f}s", flush=True)
    merged = model.merge_and_unload()
    merged = merged.to(torch.float16)
    merged.save_pretrained(a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
