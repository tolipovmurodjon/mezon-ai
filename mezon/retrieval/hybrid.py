"""Hybrid retrieval over the full law store: FTS5 + bge-m3 dense (faiss) fused by reciprocal rank, optional reranker.

Runs on the box (needs the GPU libs); the laptop reaches it through service.py. Date-aware: only units whose
valid_from <= date < valid_to are returned, for every leg.
"""
import os, re, sqlite3, time
import numpy as np

from research.textnorm import fold

RRF_K = 60
CLEAN = re.compile(r'["*]')


class Hybrid:
    def __init__(self, db: str, dense_dir: str, device: str = "cuda", rerank: bool = True, model_path: str | None = None):
        import faiss, torch
        from transformers import AutoModel, AutoTokenizer, AutoModelForSequenceClassification
        self.torch, self.device = torch, device
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        self.enc = AutoModel.from_pretrained("BAAI/bge-m3" if model_path is None else model_path, torch_dtype=torch.float16).to(device).eval()
        vec = np.memmap(os.path.join(dense_dir, "vecs.f16"), dtype=np.float16, mode="r").reshape(-1, 1024)
        self.ids = np.fromfile(os.path.join(dense_dir, "ids.i64"), dtype=np.int64)
        assert len(self.ids) == len(vec), (len(self.ids), len(vec))
        self.index = faiss.IndexScalarQuantizer(1024, faiss.ScalarQuantizer.QT_fp16, faiss.METRIC_INNER_PRODUCT)
        for i in range(0, len(vec), 200000):
            self.index.add(np.asarray(vec[i:i + 200000], dtype=np.float32))
        self.rr = None
        if rerank:
            self.rtok = AutoTokenizer.from_pretrained("BAAI/bge-reranker-v2-m3")
            self.rr = AutoModelForSequenceClassification.from_pretrained("BAAI/bge-reranker-v2-m3", torch_dtype=torch.float16).to(device).eval()

    # ---- legs
    def fts(self, query: str, on: str, k: int = 50, act_key: str | None = None) -> list[int]:
        terms = [t for t in fold(query).split() if len(t) > 2][:24]
        if not terms:
            return []
        out: list[int] = []
        for joiner in (" AND ", " OR "):
            match = joiner.join(f'"{t}"*' for t in terms)
            rows = self.con.execute(
                """SELECT f.unit_id FROM units_fts f JOIN units u ON u.id=f.unit_id
                   WHERE units_fts MATCH ? AND u.valid_from<=? AND (u.valid_to IS NULL OR u.valid_to>?)
                   AND (? IS NULL OR u.act_key=?) ORDER BY bm25(units_fts,5.0,1.0) LIMIT ?""",
                (match, on, on, act_key, act_key, k)).fetchall()
            seen = set(out)
            out += [r[0] for r in rows if r[0] not in seen]
            if len(out) >= k:
                break
        return out[:k]

    def embed(self, texts: list[str], max_len: int = 512) -> np.ndarray:
        torch = self.torch
        b = self.tok(texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(self.device)
        with torch.no_grad():
            h = self.enc(**b).last_hidden_state[:, 0]
            return torch.nn.functional.normalize(h.float(), dim=-1).cpu().numpy()

    def dense(self, query: str, on: str, k: int = 50, act_key: str | None = None, over: int = 400) -> list[int]:
        q = self.embed([query])
        sc, ix = self.index.search(q, over)
        uids, seen = [], set()
        for j in ix[0]:
            if j < 0:
                continue
            u = int(self.ids[j])
            if u not in seen:
                seen.add(u); uids.append(u)
        if not uids:
            return []
        ph = ",".join("?" * len(uids))
        ok = {r[0] for r in self.con.execute(
            f"SELECT id FROM units WHERE id IN ({ph}) AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)"
            + (" AND act_key=?" if act_key else ""), (*uids, on, on) + ((act_key,) if act_key else ()))}
        return [u for u in uids if u in ok][:k]

    def rerank(self, query: str, uids: list[int], top: int = 5, maxc: int = 1200) -> list[int]:
        torch = self.torch
        rows = {r["id"]: r for r in self.con.execute(
            f"SELECT id, heading, text FROM units WHERE id IN ({','.join('?' * len(uids))})", uids)}
        pairs = [(query, ((rows[u]["heading"] or "") + "\n" + (rows[u]["text"] or ""))[:maxc]) for u in uids]
        scores = []
        for i in range(0, len(pairs), 25):
            b = self.rtok(pairs[i:i + 25], padding=True, truncation=True, max_length=512, return_tensors="pt").to(self.device)
            with torch.no_grad():
                scores += self.rr(**b).logits.view(-1).float().cpu().tolist()
        order = sorted(range(len(uids)), key=lambda i: -scores[i])
        return [uids[i] for i in order[:top]]

    # ---- fusion
    def search(self, query: str, on: str, k: int = 5, mode: str = "hybrid", rerank: bool = True, act_key: str | None = None,
               pool: int = 50) -> list[dict]:
        if mode == "fts":
            ids = self.fts(query, on, pool, act_key)
        elif mode == "dense":
            ids = self.dense(query, on, pool, act_key)
        else:
            a, b = self.fts(query, on, pool, act_key), self.dense(query, on, pool, act_key)
            sc: dict[int, float] = {}
            for lst in (a, b):
                for r, u in enumerate(lst):
                    sc[u] = sc.get(u, 0.0) + 1.0 / (RRF_K + r + 1)
            ids = sorted(sc, key=lambda u: -sc[u])[:pool]
        if rerank and self.rr is not None and mode in ("hybrid", "dense", "fts") and len(ids) > 1:
            ids = self.rerank(query, ids, top=max(k, 1))
        return self.hydrate(ids[:k])

    def hydrate(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        rows = {r["id"]: r for r in self.con.execute(
            f"SELECT id, act_key, path, heading, text, ondate, valid_from, valid_to FROM units WHERE id IN ({','.join('?' * len(ids))})", ids)}
        return [{"id": u, "act_key": rows[u]["act_key"], "path": rows[u]["path"], "heading": rows[u]["heading"],
                 "edition": rows[u]["ondate"], "valid_from": rows[u]["valid_from"], "valid_to": rows[u]["valid_to"],
                 "text": rows[u]["text"]} for u in ids if u in rows]
