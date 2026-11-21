"""bge-m3 dense vectors for the full law store (box GPU). Incremental: appends vectors for units with id above the watermark.

    python -m mezon.retrieval.embed_full --db data/store/laws_full.sqlite --out data/store/dense --max-units 0

Units embedded: article-level containers plus standalone units (a part of a container is inside the container's text).
Long units are cut into <=510-token windows (at most MAXCH per unit), each window one vector; the id map says which unit.
Files: vecs.f16 (raw float16 rows of 1024, np.memmap-able), ids.i64 (unit id per row), wm.txt (watermark).
"""
import argparse, os, sqlite3, time
import numpy as np

MAXCH = 6
WIN = 510
TOK_BUDGET = int(os.environ.get("EMB_TOK_BUDGET", 12000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--max-units", type=int, default=0); ap.add_argument("--shard", type=int, default=100000)
    a = ap.parse_args()
    import torch
    from transformers import AutoModel, AutoTokenizer
    os.makedirs(a.out, exist_ok=True)
    wmf = os.path.join(a.out, "wm.txt")
    wm = int(open(wmf).read()) if os.path.exists(wmf) else 0
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
    model = AutoModel.from_pretrained("BAAI/bge-m3", torch_dtype=torch.float16).cuda().eval()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    q = """SELECT u.id, u.heading, u.text FROM units u JOIN unit_meta m ON m.id=u.id
           WHERE u.id>? AND (m.is_container=1 OR instr(u.path,'/')=0) ORDER BY u.id LIMIT ?"""
    vf = open(os.path.join(a.out, "vecs.f16"), "ab"); idf = open(os.path.join(a.out, "ids.i64"), "ab")
    total_units = total_chunks = 0; t0 = time.time(); toks = 0
    while True:
        lim = a.shard if not a.max_units else min(a.shard, a.max_units - total_units)
        if lim <= 0: break
        rows = con.execute(q, (wm, lim)).fetchall()
        if not rows: break
        seqs, owner = [], []
        for uid, h, t in rows:
            txt = ((h or "") + "\n" + (t or ""))[:24000]
            ids = tok(txt, add_special_tokens=False)["input_ids"]
            for k in range(0, max(len(ids), 1), WIN)[:MAXCH]:
                seqs.append([tok.cls_token_id] + ids[k:k + WIN] + [tok.sep_token_id]); owner.append(uid)
        order = np.argsort([len(s) for s in seqs])
        out = np.zeros((len(seqs), 1024), dtype=np.float16)
        i = 0
        while i < len(order):
            j = i; mx = 0
            while j < len(order) and max(mx, len(seqs[order[j]])) * (j - i + 1) <= TOK_BUDGET:
                mx = max(mx, len(seqs[order[j]])); j += 1
            j = max(j, i + 1)
            b = [seqs[x] for x in order[i:j]]; L = max(len(s) for s in b)
            ids_t = torch.full((len(b), L), tok.pad_token_id); att = torch.zeros((len(b), L), dtype=torch.long)
            for r, s in enumerate(b): ids_t[r, :len(s)] = torch.tensor(s); att[r, :len(s)] = 1
            with torch.no_grad():
                h = model(input_ids=ids_t.cuda(), attention_mask=att.cuda()).last_hidden_state[:, 0]
                h = torch.nn.functional.normalize(h.float(), dim=-1).half().cpu().numpy()
            out[order[i:j]] = h; toks += sum(len(s) for s in b); i = j
        vf.write(out.tobytes()); idf.write(np.array(owner, dtype=np.int64).tobytes()); vf.flush(); idf.flush()
        wm = rows[-1][0]; open(wmf, "w").write(str(wm))
        total_units += len(rows); total_chunks += len(seqs)
        print(f"units {total_units} chunks {total_chunks} wm {wm} tok/s {toks/(time.time()-t0):.0f} elapsed {time.time()-t0:.0f}s", flush=True)
        if len(rows) < lim: break


if __name__ == "__main__":
    main()
