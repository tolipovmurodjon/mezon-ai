# Mezon-LM chat API (for the dashboard / chatbot)

OpenAI-compatible, one request at a time. Runs on the Ohio GPU (`mezon-ohio1`), bound to `127.0.0.1:8000` only.
Nothing is open to the internet. Public exposure needs Boss's yes.

## Connect (tunnel)

    ssh -N -L 8000:127.0.0.1:8000 mezon-ohio1

Then use `http://127.0.0.1:8000/v1` as the OpenAI base URL (any API key string; none is checked).

## Endpoints

- `GET /health` -> `{"status":"ok","adapter":"<path or empty>","models":[...]}`
- `GET /v1/models`
- `POST /v1/chat/completions`: `model`, `messages`, `max_tokens` (default 512, max 2048), `temperature` (default 0 = greedy),
  optional `use_tools` (default true). A client `tools` field is accepted but ignored: Mezon-LM always uses its own 5 tools.

## Models

- `mezon-lm`: base Qwen3.8-27B + Mezon LoRA adapter, with the 5 law tools. Every tool call is returned in `mezon_calls`
  (name, args, ok). Answers after at most 4 tool rounds. Returns HTTP 503 if the adapter is not on the server yet.
- `qwen-base`: same weights, adapter disabled, no tools.
- `qwen-base-tools`: adapter disabled, with the tools (to separate the effect of tools from the effect of training).

## Tools (read-only, no network)

`law_as_of` (article text as it read on a date, with edition and lex.uz link), `list_editions` (stored editions and
when an act lost force), `search_law` (articles in force on a date matching words), `get_decision` (local decision by
registration number, e.g. 231-4-59-Q/24), `verify_quote` (is the quote word for word in the article on that date).

## Example

    curl -s http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{
      "model": "mezon-lm",
      "messages": [{"role":"user","content":"Milliy qonunchilik to'\''g'\''risidagi qonun 40-moddasi 2025-10-23 sanada qanday edi?"}],
      "max_tokens": 400}'

Response: standard `choices[0].message.content` and `usage`, plus `mezon_calls` and `mezon_seconds`.
Latency measured (27B bf16, HF generate): about 11 s for 200 tokens without tools; a tool answer took 30 s (4 tool calls).

## Notes

- Flagged is not illegal: answers are possible-violation hints for an expert, not legal rulings.
- Run on the box: `tmux new-session -d -s serve "cd ~/mezon && .venv-train/bin/python -m research.serve_api"`
  (flags: `--adapter`, `--port`, `--host`). Code: `research/serve_api.py`.
