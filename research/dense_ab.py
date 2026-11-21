"""Dense-only A/B on a subset corpus: base bge-m3 vs the fine-tuned encoder (box GPU, Linux only).

    ~/retr-venv/bin/python -u -m research.dense_ab 150000
Subset = every embedded chunk of the bench acts + N random other chunks; same subset and same queries for both encoders.
Queries as in research.retrieval_bench (sentence, 3 and 5 random content words, Random(7)); date 2026-09-01.
"""
import json, os, platform, random, sqlite3, sys, time
import numpy as np, torch
from transformers import AutoModel, AutoTokenizer
from research.textnorm import fold
from research.retrieval_bench import quote

assert platform.system() == "Linux"
DB, DENSE = "data/store/laws_full.sqlite", "data/store/dense"
TUNED = os.path.expanduser("~/models/bge-m3-law")
ON, EXTRA = "2026-09-01", int(sys.argv[1]) if len(sys.argv) > 1 else 150000
core = json.load(open("data/bench/core_absid.json"))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
have = {r[0] for r in con.execute("SELECT act_key FROM acts")}
items = [json.loads(l) for l in open("data/bench/mezonbench_where_v1.jsonl", encoding="utf8")]
items = [i for i in items if core.get(i["act"]) in have]
bench_acts = sorted({core[i["act"]] for i in items})
ids = np.fromfile(f"{DENSE}/ids.i64", dtype=np.int64)
vec = np.memmap(f"{DENSE}/vecs.f16", dtype=np.float16, mode="r").reshape(-1, 1024)
uact = np.zeros(int(ids.max()) + 1, dtype=np.int32)
akeys = {a: i + 1 for i, a in enumerate(bench_acts)}
for u, a in con.execute("SELECT id, act_key FROM units"):
    uact[u] = akeys.get(a, 0)
mine = uact[ids] > 0
rows_b = np.nonzero(mine)[0]
others = np.nonzero(~mine)[0]
rng = np.random.default_rng(1)
rows = np.sort(np.concatenate([rows_b, rng.choice(others, EXTRA, replace=False)]))
print("subset chunks", len(rows), "bench-act chunks", len(rows_b), flush=True)
uids = sorted({int(ids[j]) for j in rows})
valid = {}
for i in range(0, len(uids), 900):
    ch = uids[i:i + 900]
    for u, vf, vt in con.execute(f"SELECT id, valid_from, valid_to FROM units WHERE id IN ({','.join('?' * len(ch))})", ch):
        valid[u] = vf <= ON and (vt is None or vt > ON)
ok = torch.tensor([valid[int(ids[j])] for j in rows], device="cuda")
qs, r7 = [], random.Random(7)
for it in items:
    s = quote(it["prompt"]); words = [w for w in dict.fromkeys(fold(s).split()) if len(w) > 3]
    gold = (core[it["act"]], it["path"].split("/")[0])
    qs.append((gold, "sentence", s))
    for n in (3, 5):
        qs.append((gold, f"{n}words", " ".join(r7.sample(words, min(n, len(words))))))
up = {u: (a, p) for u, a, p in con.execute(
    f"SELECT id, act_key, path FROM units WHERE act_key IN ({','.join('?' * len(bench_acts))})", bench_acts)}
tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")


def evaluate(name, model_path, V):
    enc = AutoModel.from_pretrained(model_path, dtype=torch.float16).cuda().eval()
    Vt = torch.tensor(V, device="cuda", dtype=torch.float16)
    for kind in ("sentence", "3words", "5words"):
        hit = {1: 0, 5: 0, 20: 0}; n = 0
        for gold, k, q in qs:
            if k != kind: continue
            b = tok([q], truncation=True, max_length=512, return_tensors="pt").to("cuda")
            with torch.no_grad():
                qe = torch.nn.functional.normalize(enc(**b).last_hidden_state[:, 0].float(), dim=-1).half()
            sc = (Vt @ qe.T).squeeze(1).float().masked_fill(~ok, -9)
            seen, ranked = set(), []
            for j in torch.topk(sc, 400).indices.tolist():
                u = int(ids[rows[j]])
                if u not in seen: seen.add(u); ranked.append(u)
            r = next((i for i, u in enumerate(ranked[:20]) if u in up and (up[u][0], up[u][1].split("/")[0]) == gold), 99)
            n += 1
            for K in hit: hit[K] += r < K
        print(name, kind, {"n": n, **{f"r@{K}": hit[K] for K in hit}}, flush=True)
    del enc, Vt; torch.cuda.empty_cache()


evaluate("base", "BAAI/bge-m3", np.asarray(vec[rows]))
tm = AutoModel.from_pretrained(TUNED, dtype=torch.float16).cuda().eval()
text = {}
for i in range(0, len(uids), 900):
    ch = uids[i:i + 900]
    for u, h, t in con.execute(f"SELECT id, heading, text FROM units WHERE id IN ({','.join('?' * len(ch))})", ch):
        text[u] = ((h or "") + "\n" + (t or ""))[:24000]
rowsof = {}
for pos, j in enumerate(rows):
    rowsof.setdefault(int(ids[j]), []).append(pos)
chunks, owner = [], []
for u in uids:
    tid = tok(text[u], add_special_tokens=False)["input_ids"]
    wins = [tid[k:k + 510] for k in range(0, max(len(tid), 1), 510)][:6]
    for w, pos in zip(wins, rowsof[u]):
        chunks.append([tok.cls_token_id] + w + [tok.sep_token_id]); owner.append(pos)
out = np.zeros((len(rows), 1024), dtype=np.float16)
order = np.argsort([len(s) for s in chunks]); i = 0; t0 = time.time()
while i < len(order):
    j = i; mx = 0
    while j < len(order) and max(mx, len(chunks[order[j]])) * (j - i + 1) <= 8000:
        mx = max(mx, len(chunks[order[j]])); j += 1
    j = max(j, i + 1); b = [chunks[x] for x in order[i:j]]; L = max(map(len, b))
    it_ = torch.full((len(b), L), tok.pad_token_id); at = torch.zeros((len(b), L), dtype=torch.long)
    for r, s in enumerate(b): it_[r, :len(s)] = torch.tensor(s); at[r, :len(s)] = 1
    with torch.no_grad():
        h = torch.nn.functional.normalize(tm(input_ids=it_.cuda(), attention_mask=at.cuda()).last_hidden_state[:, 0].float(), dim=-1).half().cpu().numpy()
    for r, x in enumerate(order[i:j]): out[owner[x]] = h[r]
    i = j
print("tuned embed seconds", round(time.time() - t0), flush=True)
del tm; torch.cuda.empty_cache()
evaluate("tuned", TUNED, out)
