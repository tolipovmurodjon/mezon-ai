"""Contrastive training pairs from the full law store (box). Excludes every (act, article) used by the benches.

    python -m research.build_pairs --db data/store/laws_full.sqlite --out data/train/embed_pairs.jsonl --n 100000 --fts-neg 25000
query kinds: heading title, 3-8 content words from the text, a question template over the title.
positive = the article unit ("heading\ntext"); hard negatives = another article of the same act + top FTS5 hits that are not the positive.
Re-run before training: it re-reads data/bench/mezonbench_v2.jsonl (built by another agent).
"""
import argparse, glob, json, os, random, re, sqlite3
from multiprocessing import Pool
from research.textnorm import fold

STOP = set()
TEMPL = ["{t} haqida qaysi modda?", "{t}: qanday qoida belgilangan?", "{t} bo'yicha norma"]


def excluded() -> set:
    core = json.load(open("data/bench/core_absid.json"))
    ex, unmapped = set(), set()
    for f in glob.glob("data/bench/mezonbench*.jsonl"):
        for l in open(f, encoding="utf8"):
            d = json.loads(l)
            a = d.get("act")
            if not a or not d.get("path"):
                continue
            k = core.get(a, a if a.isdigit() else None)
            if k is None:
                unmapped.add(a); continue
            ex.add((k, d["path"].split("/")[0]))
    print("excluded (act, article):", len(ex), "unmapped acts:", sorted(unmapped)[:10], flush=True)
    return ex


def title_of(h: str) -> str:
    t = re.sub(r"^\s*[\w\-–]+\s*[-\s]*(modda|статья|моддa|модда|bob|боб|глава)\s*\.?\s*", "", h or "", flags=re.I)
    t = re.sub(r"^\s*(Статья|Модда|Modda)\s*\d+[\-\w]*\.?\s*", "", t, flags=re.I)
    return t.strip(" .")


def make_query(rng: random.Random, h: str, text: str) -> tuple[str, str] | None:
    r = rng.random()
    t = title_of(h)
    if r < 0.25 and len(t.split()) >= 2:
        return "heading", t
    if r < 0.45 and len(t.split()) >= 2:
        return "template", rng.choice(TEMPL).format(t=t)
    words = [w for w in re.findall(r"\w+", text) if len(w) > 3]
    if len(words) < 8:
        return None
    n = rng.randint(3, 8); i = rng.randrange(0, max(1, len(words) - 2 * n))
    win = words[i:i + 3 * n]
    pick = sorted(rng.sample(range(len(win)), min(n, len(win))))
    return "words", " ".join(win[j] for j in pick)


def fts_negs(args):
    db, rows = args
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = []
    for uid, act, path, q in rows:
        terms = [t for t in fold(q).split() if len(t) > 3][:6]
        if len(terms) < 2:
            out.append([]); continue
        m = " OR ".join(f'"{t}"' for t in terms)
        try:
            got = con.execute("""SELECT u.id FROM units_fts f JOIN units u ON u.id=f.unit_id JOIN unit_meta mm ON mm.id=u.id
               WHERE units_fts MATCH ? AND u.valid_to IS NULL AND (mm.is_container=1 OR instr(u.path,'/')=0)
               ORDER BY bm25(units_fts,5.0,1.0) LIMIT 6""", (m,)).fetchall()
        except sqlite3.Error:
            got = []
        out.append([g[0] for g in got if not (g[0] == uid)][:4])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=100000); ap.add_argument("--fts-neg", type=int, default=25000)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    ex = excluded()
    rng = random.Random(a.seed)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    ids = [r[0] for r in con.execute("""SELECT u.id FROM units u JOIN unit_meta m ON m.id=u.id
        WHERE u.valid_to IS NULL AND (m.is_container=1 OR instr(u.path,'/')=0) AND length(u.text) BETWEEN 200 AND 6000
        """)]
    print("candidate units:", len(ids), flush=True)
    rng.shuffle(ids)
    pairs, skipped = [], 0
    for uid in ids:
        if len(pairs) >= a.n: break
        act, path, h, t = con.execute("SELECT act_key, path, heading, text FROM units WHERE id=?", (uid,)).fetchone()
        if (act, path.split("/")[0]) in ex:
            skipped += 1; continue
        q = make_query(rng, h, t)
        if q is None: continue
        sib = con.execute("""SELECT u.id FROM units u JOIN unit_meta m ON m.id=u.id WHERE u.act_key=? AND u.id!=? AND u.valid_to IS NULL
                AND (m.is_container=1 OR instr(u.path,'/')=0) AND length(u.text)>100
                ORDER BY random() LIMIT 2""", (act, uid)).fetchall()
        pairs.append({"uid": uid, "act": act, "path": path, "kind": q[0], "q": q[1], "sib": [s[0] for s in sib], "fneg": []})
    print("pairs", len(pairs), "skipped by exclusion", skipped, flush=True)
    sub = pairs[:a.fts_neg]
    chunks = [(a.db, [(p["uid"], p["act"], p["path"], p["q"]) for p in sub[i::6]]) for i in range(6)]
    with Pool(6) as pool:
        res = pool.map(fts_negs, chunks)
    for i, r in enumerate(res):
        for p, g in zip(sub[i::6], r):
            p["fneg"] = g
    need = {u for p in pairs for u in [p["uid"], *p["sib"], *p["fneg"]]}
    txt = {}
    ids_l = list(need)
    for i in range(0, len(ids_l), 5000):
        part = ids_l[i:i + 5000]
        for uid, h, t in con.execute(f"SELECT id, heading, text FROM units WHERE id IN ({','.join('?' * len(part))})", part):
            txt[uid] = ((h or "") + "\n" + (t or ""))[:1800]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    nkinds = {}
    with open(a.out, "w", encoding="utf8") as f:
        for p in pairs:
            negs = [txt[u] for u in p["fneg"] if u in txt and u != p["uid"]] + [txt[u] for u in p["sib"] if u in txt]
            f.write(json.dumps({"q": p["q"], "pos": txt[p["uid"]], "negs": negs[:3], "act": p["act"], "path": p["path"], "kind": p["kind"]}, ensure_ascii=False) + "\n")
            nkinds[p["kind"]] = nkinds.get(p["kind"], 0) + 1
    print("written", len(pairs), nkinds, "with fts negs", sum(1 for p in pairs if p["fneg"]))


if __name__ == "__main__":
    main()
