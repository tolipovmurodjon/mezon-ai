"""Full law store from the refinery's extract output (every act on lex.uz), same schema as data/store/laws.sqlite.

    python -m mezon.lawstore.build_full --extract data/refinery/full/01_extract --out data/store/laws_full.sqlite

Incremental: only batches that the refinery's run.log marks finished are loaded, and a batch already in the
`build_batches` table is skipped, so the same command adds the rest when the refinery gets further.
One act per absolute lex.uz id (Latin version first, then Cyrillic, then the rest); act_key = the absolute id.
Linux box only (reads the refinery files, uses a process pool). Never writes to the old 38-act store.
"""

import argparse
import glob
import gzip
import json
import re
import sqlite3
import sys
import time
from multiprocessing import Pool
from pathlib import Path

from mezon.lawstore.store import SCHEMA
from research.textnorm import fold

LANG_RANK = {"uz_latn": 0, "uz_cyrl": 1, "ru": 2}
EXTRA = """
CREATE TABLE IF NOT EXISTS build_batches(batch TEXT PRIMARY KEY, acts INTEGER, units INTEGER, secs REAL);
CREATE TABLE IF NOT EXISTS act_lang(act_key TEXT PRIMARY KEY, rank INTEGER);
CREATE TABLE IF NOT EXISTS unit_meta(id INTEGER PRIMARY KEY, is_container INTEGER);
"""
_CHOSEN: set[str] = set()
_KEY: dict[str, str] = {}


def _s(v):
    return v if v is None or isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def finished_batches(extract: Path) -> list[str]:
    log = (extract.parent / "run.log").read_text(encoding="utf8", errors="replace")
    return sorted(set(re.findall(r"\bP1 (b\d{3}):", log)))


def _fold_rows(lines: list[str]) -> list[tuple]:
    out = []
    for ln in lines:
        d = json.loads(ln)
        lid = d["lex_id"]
        if lid not in _CHOSEN:
            continue
        out.append((_KEY[lid], d["path"], d["heading"], d["text"], d["element_id"], d["notes"], d["seq_from"],
                    d["seq_to"], d["valid_from"], d["valid_to"], d["ondate"], int(bool(d["is_container"])),
                    fold(d["heading"] or ""), fold(d["text"] or "")))
    return out


def _chunks(path: str, n: int = 1500):
    buf = []
    with gzip.open(path, "rt", encoding="utf8") as f:
        for ln in f:
            buf.append(ln)
            if len(buf) >= n:
                yield buf
                buf = []
    if buf:
        yield buf


def drop_act(con: sqlite3.Connection, key: str) -> None:
    ids = [r[0] for r in con.execute("SELECT id FROM units WHERE act_key=?", (key,))]
    con.executemany("DELETE FROM units_fts WHERE unit_id=?", [(i,) for i in ids])
    con.executemany("DELETE FROM unit_meta WHERE id=?", [(i,) for i in ids])
    for t in ("units", "editions", "acts"):
        con.execute(f"DELETE FROM {t} WHERE act_key=?", (key,))


def load_batch(con: sqlite3.Connection, extract: Path, batch: str, procs: int) -> tuple[int, int]:
    t0 = time.time()
    best: dict[str, tuple] = {}  # abs id -> (rank, lex_id, meta, editions)
    for fp in sorted(glob.glob(str(extract / "acts" / f"{batch}-*.jsonl.gz"))):
        with gzip.open(fp, "rt", encoding="utf8") as f:
            for ln in f:
                d = json.loads(ln)
                m = d["meta"]
                ab = str(m["abs_id"])
                rank = LANG_RANK.get(m.get("catalog_lang"), 3)
                if ab not in best or rank < best[ab][0]:
                    best[ab] = (rank, d["lex_id"], m, d["editions"])
    keep: dict[str, tuple] = {}
    for ab, rec in best.items():
        old = con.execute("SELECT rank FROM act_lang WHERE act_key=?", (ab,)).fetchone()
        if old is not None:
            # an act loaded earlier: replace only when this batch brings a better language version
            if old[0] <= rec[0]:
                continue
            drop_act(con, ab)
        keep[ab] = rec
    for ab, (rank, lid, m, eds) in keep.items():
        con.execute("INSERT OR REPLACE INTO act_lang VALUES(?,?)", (ab, rank))
        con.execute("INSERT INTO acts VALUES(?,?,?,?,?,?,?,?)",
                    (ab, lid, _s(m.get("title") or m.get("catalog_title")), _s(m.get("act_type")), _s(m.get("number")),
                     _s(m.get("adopted")), _s(m.get("lost_force")), f"https://lex.uz/uz/docs/{lid}"))
        for i, e in enumerate(eds):
            con.execute("INSERT OR REPLACE INTO editions VALUES(?,?,?,?,?,?)",
                        (ab, e["ondate"], e["valid_from"], i, e["valid_to"], int(bool(e.get("provisional")))))
    _CHOSEN.clear()
    _KEY.clear()
    for ab, rec in keep.items():
        _CHOSEN.add(rec[1])
        _KEY[rec[1]] = ab
    n_units = 0
    pool = Pool(procs)  # forked now, so the workers see this batch's chosen ids
    for fp in sorted(glob.glob(str(extract / "unit_versions" / f"{batch}-*.jsonl.gz"))):
        for rows in pool.imap(_fold_rows, _chunks(fp), chunksize=1):
            for r in rows:
                cur = con.execute(
                    """INSERT INTO units(act_key, path, heading, text, element_id, notes, seq_from, seq_to,
                       valid_from, valid_to, ondate) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", r[:11])
                uid = cur.lastrowid
                con.execute("INSERT INTO unit_meta VALUES(?,?)", (uid, r[11]))
                con.execute("INSERT INTO units_fts(heading, body, unit_id) VALUES(?,?,?)", (r[12], r[13], uid))
                n_units += 1
    pool.close()
    con.execute("INSERT OR REPLACE INTO build_batches VALUES(?,?,?,?)", (batch, len(keep), n_units, time.time() - t0))
    con.commit()
    return len(keep), n_units


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=6)
    a = ap.parse_args()
    if sys.platform == "win32":
        sys.exit("run this on the box (Linux): the full store is built there")
    extract, out = Path(a.extract), Path(a.out)
    if out.name == "laws.sqlite":
        sys.exit("refusing to touch the frozen 38-act store")
    out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=OFF")
    con.executescript(SCHEMA + EXTRA)
    done = {r[0] for r in con.execute("SELECT batch FROM build_batches")}
    todo = [b for b in finished_batches(extract) if b not in done]
    print("finished by the refinery:", finished_batches(extract), "| already loaded:", sorted(done), "| to load:", todo, flush=True)
    for b in todo:
        t = time.time()
        na, nu = load_batch(con, extract, b, a.procs)
        print(f"{b}: +{na} acts +{nu} units in {time.time() - t:.0f}s", flush=True)
    print("acts", con.execute("SELECT count(*) FROM acts").fetchone()[0], "editions",
          con.execute("SELECT count(*) FROM editions").fetchone()[0], "units",
          con.execute("SELECT count(*) FROM units").fetchone()[0], "size MB", round(out.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
