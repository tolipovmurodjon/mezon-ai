"""Deterministic JSONL(.gz) shards: gzip header without a timestamp, sorted keys, so two runs give identical bytes."""

import gzip
import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def _lines(rows: Iterable[dict]) -> Iterator[bytes]:
    for r in rows:
        yield (json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "wb") as raw:
        if path.suffix == ".gz":
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
                for line in _lines(rows):
                    gz.write(line)
                    n += 1
        else:
            for line in _lines(rows):
                raw.write(line)
                n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def sha1_file(path: Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()
