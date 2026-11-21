"""OpenAI-compatible chat API for Mezon-LM (one GPU, one request at a time).

    python -m research.serve_api --adapter data/models/chain_v1/final --port 8000

model "mezon-lm": base + LoRA adapter, answers with the 5 law tools (mezon.tools); the tool calls come back in
`mezon_calls`. model "qwen-base": same weights, adapter disabled, no tools. "qwen-base-tools": adapter disabled, with the tools. Binds 127.0.0.1 by default.
"""

import argparse
import asyncio
import contextlib
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from research.bench_tools_run import HINT, load_model, make_generate, run_tool_loops

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("mezon-lm", "qwen-base", "qwen-base-tools")
S: dict = {}
LOCK = asyncio.Lock()
app = FastAPI(title="Mezon-LM API")


class Msg(BaseModel):
    role: str
    content: str | None = ""


class ChatReq(BaseModel):
    model: str = "mezon-lm"
    messages: list[Msg]
    max_tokens: int = 512
    temperature: float = 0.0
    tools: list[dict] | None = None  # accepted for OpenAI clients; mezon-lm always uses its own 5 law tools
    use_tools: bool = True  # False: mezon-lm answers without tools


def _answer(req: ChatReq) -> dict:
    import torch  # noqa: F401  (loaded with the model)

    tok, model, law = S["tok"], S["model"], S["law"]
    gen = make_generate(model, tok, sample=req.temperature > 0, temperature=max(req.temperature, 1e-3),
                        max_new=min(req.max_tokens, 2048))
    msgs = [{"role": m.role, "content": m.content or ""} for m in req.messages]
    if req.model == "qwen-base":
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        with model.disable_adapter() if S.get("adapter") else contextlib.nullcontext():
            raw = gen([text])[0]
        return {"answer": raw.split("</think>")[-1].strip(), "calls": [], "n_in": len(tok(text).input_ids)}
    if req.use_tools or req.model == "qwen-base-tools":
        if msgs and msgs[0]["role"] == "system":
            msgs[0]["content"] += HINT
        else:
            msgs.insert(0, {"role": "system", "content": HINT.strip()})
        with model.disable_adapter() if (req.model == "qwen-base-tools" and S.get("adapter")) else contextlib.nullcontext():
            r = run_tool_loops([msgs], gen, tok, law, rounds=4)[0]
        return {"answer": r["answer"], "calls": r["calls"], "n_in": 0}
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return {"answer": gen([text])[0].split("</think>")[-1].strip(), "calls": [], "n_in": len(tok(text).input_ids)}


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if "model" in S else "loading", "adapter": S.get("adapter"), "models": list(MODELS)}


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "mezon"} for m in MODELS]}


@app.post("/v1/chat/completions")
async def chat(req: ChatReq) -> dict:
    if req.model == "mezon-lm" and not S.get("adapter"):
        raise HTTPException(503, "mezon-lm: the LoRA adapter is not on this server yet (qwen-base works)")
    if req.model not in MODELS:
        raise HTTPException(404, f"unknown model {req.model!r}; use one of {list(MODELS)}")
    if "model" not in S:
        raise HTTPException(503, "model is still loading")
    async with LOCK:
        t0 = time.time()
        r = await asyncio.to_thread(_answer, req)
    n_out = len(S["tok"](r["answer"]).input_ids)
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12], "object": "chat.completion", "created": int(t0), "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": r["answer"]}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": r["n_in"], "completion_tokens": n_out, "total_tokens": r["n_in"] + n_out},
        "mezon_calls": r["calls"], "mezon_seconds": round(time.time() - t0, 1),
    }


def main() -> None:
    import uvicorn

    from mezon.lawstore.store import LawStore
    from research.bench_tools_run import DEC  # noqa: F401  (tools.call uses it through run_tool_loops)

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(Path.home() / "models" / "Qwen3.8-27B"))
    ap.add_argument("--adapter", default=str(ROOT / "data" / "models" / "chain_v1" / "final"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    S["law"] = LawStore()
    adapter = a.adapter if (Path(a.adapter) / "adapter_model.safetensors").exists() else ""
    if not adapter:
        print(f"WARNING: no adapter at {a.adapter}; serving qwen-base only", flush=True)
    S["tok"], S["model"] = load_model(a.model, adapter)
    S["adapter"] = adapter
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
