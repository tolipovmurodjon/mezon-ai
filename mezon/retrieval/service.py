"""Tiny HTTP service on the box: POST /search {query, date, k, mode, rerank, act_key} -> hits.

    MEZON_DB=data/store/laws_full.sqlite MEZON_DENSE=data/store/dense .venv python -m uvicorn mezon.retrieval.service:app --port 8765
The laptop reaches it with `ssh -L 8765:127.0.0.1:8765 mezon-gpu` and MEZON_RETRIEVAL_URL=http://127.0.0.1:8765.
"""
import os
from fastapi import FastAPI
from pydantic import BaseModel

from mezon.retrieval.hybrid import Hybrid

app = FastAPI()
H = None


class Q(BaseModel):
    query: str
    date: str
    k: int = 5
    mode: str = "hybrid"
    rerank: bool = True
    act_key: str | None = None


@app.on_event("startup")
def _load():
    global H
    H = Hybrid(os.environ["MEZON_DB"], os.environ["MEZON_DENSE"], rerank=os.environ.get("MEZON_RERANK", "1") == "1",
               model_path=os.environ.get("MEZON_ENCODER") or None)


@app.post("/search")
def search(q: Q):
    return {"hits": H.search(q.query, q.date, q.k, q.mode, q.rerank, q.act_key)}


@app.get("/health")
def health():
    return {"ok": H is not None, "chunks": int(len(H.ids))}
