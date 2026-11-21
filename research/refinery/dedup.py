"""Stage 06: exact duplicates, twins (x and -x), and near-duplicates between different acts (design section 6a).

MinHash runs only inside strata (act_type, adopted year, language-script) and never over editions: consecutive editions
of one act are far above any threshold by design and are handled by the unit-interval table. Twins are both kept, linked."""

import hashlib
import random
import zlib
from collections import defaultdict

import numpy as np

from research.refinery import config
from research.textnorm import fold, similarity

_P = (1 << 61) - 1


def exact_groups(docs: dict[str, str]) -> dict[str, list[str]]:
    """sha1 of fold(text) -> member ids (only groups with 2+ members)."""
    g: dict[str, list[str]] = defaultdict(list)
    for k in sorted(docs):
        g[hashlib.sha1(fold(docs[k]).encode()).hexdigest()].append(k)
    return {h: m for h, m in g.items() if len(m) > 1}


def twin_sample(text: str) -> str:
    """First and last 3,000 folded characters (fold transliterates, so both scripts compare)."""
    f = fold(text)
    return f[:3000] + " " + f[-3000:]


def twin_from_samples(sa: str, sb: str) -> tuple[str, float]:
    s = similarity(sa, sb)
    return ("twin" if s >= config.TWIN_YES else "different_acts" if s < config.TWIN_NO else "review"), round(
        s, 4
    )


def twin_verdict(a: str, b: str) -> tuple[str, float]:
    return twin_from_samples(twin_sample(a), twin_sample(b))


def shingle_set(text: str, k: int = 5) -> set[int]:
    w = fold(text).split()
    return (
        {zlib.crc32(" ".join(w[i : i + k]).encode()) for i in range(max(len(w) - k + 1, 1))} if w else set()
    )


_P31 = (1 << 31) - 1


class MinHasher:
    """112 permutations as 14 bands x 8 rows (FineWeb); deterministic from a fixed seed. h_i(x) = (a_i x + b_i) mod
    2^31-1 on the 32-bit shingle hash, vectorised with numpy (uint64 never overflows: a, x < 2^32), so the full corpus
    is signed in minutes instead of hours."""

    def __init__(self, seed: int = config.SEED):
        rng = random.Random(seed)
        self.a = np.array([rng.randrange(1, _P31) for _ in range(config.MINHASH_PERM)], dtype=np.uint64)
        self.b = np.array([rng.randrange(0, _P31) for _ in range(config.MINHASH_PERM)], dtype=np.uint64)

    def signature_np(self, shingles: set[int]) -> np.ndarray:
        sig = np.full(config.MINHASH_PERM, _P31, dtype=np.uint64)
        if not shingles:
            return np.zeros(config.MINHASH_PERM, dtype=np.uint64)
        xs = np.fromiter(shingles, dtype=np.uint64, count=len(shingles)) % np.uint64(_P31)
        for i in range(0, len(xs), 16384):
            chunk = xs[i : i + 16384]
            h = (chunk[:, None] * self.a[None, :] + self.b[None, :]) % np.uint64(_P31)
            sig = np.minimum(sig, h.min(axis=0))
        return sig

    def signature(self, shingles: set[int]) -> list[int]:
        return [int(v) for v in self.signature_np(shingles)]

    def bands(self, sig) -> list[bytes]:
        r = config.MINHASH_ROWS
        sig = [int(v) for v in sig]
        return [
            bytes([i]) + b"".join(v.to_bytes(8, "little") for v in sig[i * r : (i + 1) * r])
            for i in range(config.MINHASH_BANDS)
        ]


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def minhash_clusters(items: list[dict]) -> list[dict]:
    """items: {id, stratum, text, adopted}. Returns one row per clustered member:
    {cluster, id, keep, dup_count, jaccard_to_rep}. Candidates come from LSH buckets inside a stratum; every edge is
    verified with exact Jaccard >= 0.80; clusters are transitive (union-find); up to 3 members are kept per cluster
    (earliest, latest, nearest the median) and dup_count = cluster size."""
    mh = MinHasher()
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_stratum[it["stratum"]].append(it)
    rows = []
    cid = 0
    for stratum in sorted(by_stratum):
        members = sorted(by_stratum[stratum], key=lambda x: x["id"])
        if len(members) < 2:
            continue
        sets = {m["id"]: shingle_set(m["text"]) for m in members}
        buckets: dict[bytes, list[str]] = defaultdict(list)
        for m in members:
            for band in mh.bands(mh.signature(sets[m["id"]])):
                buckets[band].append(m["id"])
        parent = {m["id"]: m["id"] for m in members}

        def find(x: str, parent=parent) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        seen_pairs = set()
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    p = (ids[i], ids[j])
                    if p in seen_pairs:
                        continue
                    seen_pairs.add(p)
                    if jaccard(sets[p[0]], sets[p[1]]) >= config.NEAR_DUP_JACCARD:
                        parent[find(p[0])] = find(p[1])
        groups: dict[str, list[dict]] = defaultdict(list)
        for m in members:
            groups[find(m["id"])].append(m)
        for g in sorted(groups.values(), key=lambda g: g[0]["id"]):
            if len(g) < 2:
                continue
            cid += 1
            g = sorted(g, key=lambda m: (m.get("adopted") or "", m["id"]))
            keep = {g[0]["id"], g[-1]["id"], g[len(g) // 2]["id"]}
            for m in g:
                rows.append(
                    {
                        "cluster": f"c{cid:05d}",
                        "stratum": stratum,
                        "id": m["id"],
                        "keep": m["id"] in keep,
                        "dup_count": len(g),
                        "cluster_size": len(g),
                    }
                )
    # a cluster keeps at most config.CLUSTER_KEEP members (the set above has at most 3)
    return rows


def cluster_signatures(items: list[dict], all_pairs_up_to: int = 40) -> list[dict]:
    """Global near-duplicate clustering from signatures only (the full run keeps no text across batches).
    items: {id, stratum, sig (112 uint64 values), adopted}. Candidates come from LSH buckets inside a stratum; an
    edge needs an estimated Jaccard (share of equal signature rows) >= 0.80; clusters are transitive. A bucket of up
    to `all_pairs_up_to` members is compared pairwise, a larger one (template families) compares each member with
    the first `all_pairs_up_to` members of the bucket, so a stratum of 20,000 near-identical decisions stays linear.
    Same output rows and keep rule as `minhash_clusters`."""
    mh = MinHasher()
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_stratum[it["stratum"]].append(it)
    rows, cid = [], 0
    for stratum in sorted(by_stratum):
        members = sorted(by_stratum[stratum], key=lambda x: x["id"])
        if len(members) < 2:
            continue
        sigs = {m["id"]: np.asarray(m["sig"], dtype=np.uint64) for m in members}
        buckets: dict[bytes, list[str]] = defaultdict(list)
        for m in members:
            for band in mh.bands(sigs[m["id"]]):
                buckets[band].append(m["id"])
        parent = {m["id"]: m["id"] for m in members}

        def find(x: str, parent=parent) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        seen_pairs: set[tuple[str, str]] = set()
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            for j in range(1, len(ids)):
                for i in range(min(j, all_pairs_up_to)):
                    p = (ids[i], ids[j])
                    if p in seen_pairs:
                        continue
                    seen_pairs.add(p)
                    if find(p[0]) != find(p[1]) and float(np.mean(sigs[p[0]] == sigs[p[1]])) >= (
                        config.NEAR_DUP_JACCARD
                    ):
                        parent[find(p[0])] = find(p[1])
        groups: dict[str, list[dict]] = defaultdict(list)
        for m in members:
            groups[find(m["id"])].append(m)
        for g in sorted(groups.values(), key=lambda g: g[0]["id"]):
            if len(g) < 2:
                continue
            cid += 1
            g = sorted(g, key=lambda m: (m.get("adopted") or "", m["id"]))
            keep = {g[0]["id"], g[-1]["id"], g[len(g) // 2]["id"]}
            for m in g:
                rows.append(
                    {
                        "cluster": f"c{cid:05d}",
                        "stratum": stratum,
                        "id": m["id"],
                        "keep": m["id"] in keep,
                        "dup_count": len(g),
                        "cluster_size": len(g),
                    }
                )
    return rows


def boilerplate_clauses(
    units_by_doc: dict[str, list[dict]], df_limit: int = config.BOILERPLATE_DF
) -> dict[str, set[str]]:
    """Clause-level exact hash for local decisions: clauses of 20+ words seen in more than `df_limit` documents are
    boilerplate; they stay in 3 documents (the first by id) and are dropped elsewhere. Returns {doc: {unit paths}}."""
    seen: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for doc in sorted(units_by_doc):
        for u in units_by_doc[doc]:
            if len(u["text"].split()) >= config.BOILERPLATE_MIN_WORDS:
                seen[hashlib.sha1(fold(u["text"]).encode()).hexdigest()].append((doc, u["path"]))
    drop: dict[str, set[str]] = defaultdict(set)
    for occ in seen.values():
        docs = {d for d, _ in occ}
        if len(docs) > df_limit:
            keep_docs = sorted(docs)[:3]
            for d, p in occ:
                if d not in keep_docs:
                    drop[d].add(p)
    return dict(drop)
