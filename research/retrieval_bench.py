"""Retrieval recall on MezonBench 'where' against the full store (box). Hit = right act and right article.

    python -m research.retrieval_bench --db data/store/laws_full.sqlite --dense data/store/dense --out data/eval/retrieval_base.json
Queries per item: the quoted norm (full sentence), 3 and 5 random content words (random.Random(7)).
"""
import argparse, json, random, re, time
from research.textnorm import fold
from mezon.retrieval.hybrid import Hybrid

ON = "2026-09-01"


def quote(prompt: str) -> str:
    m = re.search(r"«(.+?)»", prompt, re.S)
    return (m.group(1) if m else prompt).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--dense", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--encoder", default=None); ap.add_argument("--bench", default="data/bench/mezonbench_where_v1.jsonl")
    ap.add_argument("--no-rerank", action="store_true")
    a = ap.parse_args()
    core = json.load(open("data/bench/core_absid.json"))
    items = [json.loads(l) for l in open(a.bench, encoding="utf8")]
    H = Hybrid(a.db, a.dense, rerank=not a.no_rerank, model_path=a.encoder)
    have = {r[0] for r in H.con.execute("SELECT act_key FROM acts")}
    items = [i for i in items if core.get(i["act"]) in have]
    rng = random.Random(7)
    qs = []
    for it in items:
        s = quote(it["prompt"]); words = [w for w in dict.fromkeys(fold(s).split()) if len(w) > 3]
        gold = (core[it["act"]], it["path"].split("/")[0])
        qs.append((gold, "sentence", s))
        for n in (3, 5):
            pick = rng.sample(words, min(n, len(words)))
            qs.append((gold, f"{n}words", " ".join(pick)))
    modes = [("fts", "fts", False), ("dense", "dense", False), ("hybrid", "hybrid", False), ("hybrid+rerank", "hybrid", True)]
    res = {"N_items": len(items), "date": ON, "store_acts": len(have)}
    for name, mode, rr in modes:
        if rr and a.no_rerank: continue
        for kind in ("sentence", "3words", "5words"):
            hit = {1: 0, 5: 0, 20: 0}; n = 0; lat = []
            for gold, k, q in qs:
                if k != kind: continue
                t = time.time(); hits = H.search(q, ON, 20, mode, rr); lat.append(time.time() - t); n += 1
                ranks = [i for i, h in enumerate(hits) if (h["act_key"], h["path"].split("/")[0]) == gold]
                r = ranks[0] if ranks else 99
                for K in hit: hit[K] += r < K
            lat.sort()
            res[f"{name}/{kind}"] = {"n": n, **{f"r@{K}": hit[K] for K in hit}, "lat_ms_median": round(1000 * lat[len(lat) // 2]), "lat_ms_p95": round(1000 * lat[int(len(lat) * .95)])}
            print(name, kind, res[f"{name}/{kind}"], flush=True)
    json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
