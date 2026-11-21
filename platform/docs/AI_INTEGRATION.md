# Connecting the Mezon model

The web app never talks to a model directly. It talks to an **analyzer**, a small
Python class with two methods: `analyze()` and `chat()`. Both are generators of
plain-dict events. Switching models is one environment variable; the UI does not
change.

| `MEZON_AI_BACKEND` | Use it when | Code |
|---|---|---|
| `demo` (default) | No model yet. 14 rule checks, template answers, labelled "Demo analizator". | `regulations/ai/demo.py` |
| `openai` | The fine-tuned model is served by vLLM, Ollama, LM Studio, TGI or llama.cpp. | `regulations/ai/openai_compat.py` |
| `http` | You have your own agent service (for example the FastAPI app on :8090). | `regulations/ai/remote.py` |
| `my_pkg.module.MyAnalyzer` | Anything else: subclass `BaseAnalyzer`. | `regulations/ai/base.py` |

Other settings: `MEZON_AI_URL`, `MEZON_AI_MODEL`, `MEZON_AI_API_KEY`, `MEZON_AI_TIMEOUT` (seconds).

---

## Option A: OpenAI-compatible server (fastest)

```bash
# serve the fine-tuned checkpoint
vllm serve /models/mezon-qonun --served-model-name mezon-qonun --port 8000

# point Mezon at it
export MEZON_AI_BACKEND=openai
export MEZON_AI_URL=http://127.0.0.1:8000/v1
export MEZON_AI_MODEL=mezon-qonun
python manage.py runserver
```

The 14 rule checks still run first, because they are deterministic. The model then
reads every document plus the check results and returns JSON (verdict,
recommendation, score, summary, findings). Two safeguards are built in:

* **Citation verifier.** A quote the model returns that is not verbatim in the
  documents is removed before the expert sees it.
* **Rule floor.** If a rule found a critical conflict, the verdict cannot come out as
  "compliant", whatever the model says.

## Option B: your own service (`http`)

Expose two endpoints. Each may stream **NDJSON** (one JSON event per line, which is
best because the expert watches the agent work), or return one JSON object.

### `POST {MEZON_AI_URL}/v1/analyze`

Request body:

```json
{
  "number": "SR-2026-00534",
  "draft_number": "475-9-96-Q/26",
  "title": "Hududda savdo shoxobchalari faoliyatini tartibga solish to‘g‘risida",
  "doc_type": "qaror",
  "category": "Savdo va xizmat ko‘rsatish",
  "region": "Qashqadaryo viloyati",
  "district": "Yakkabog‘ tumani",
  "issuer": {"name": "…", "title": "Yakkabog‘ tumani hokimi"},
  "submitted_at": "2026-11-21T11:04:00+05:00",
  "documents": [{"id": 1, "title": "Qaror loyihasi", "kind": "draft", "pages": 2, "text": "…"}]
}
```

Streamed events (`Content-Type: application/x-ndjson`), in any order, ending with `verdict`:

```json
{"type":"step","id":"read","label":"Hujjatlar o‘qildi","status":"done","detail":"3 ta hujjat","ms":640}
{"type":"check","id":"dead_article","label":"Kuchini yo‘qotgan norma","status":"fail","detail":"1 ta kuchsiz havola"}
{"type":"source","title":"“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun","meta":"qaror sanasidagi tahrir","kind":"law"}
{"type":"finding","code":"dead_article","category":"Kuchini yo‘qotgan norma","severity":"critical",
 "title":"…","explanation":"…","quote":"verbatim text from a document","quote_source":"Qaror loyihasi, preambula",
 "law_ref":"…, 25-modda","law_text":"…","suggestion":"…"}
{"type":"token","text":"Bu loyihani hozirgi ko‘rinishida "}
{"type":"token","text":"qabul qilib bo‘lmaydi…"}
{"type":"verdict","verdict":"conflict","recommendation":"reject","score":42}
```

* `step.status`: `run` (shows a spinner), then `done`, `warn` or `fail` for the same `id`.
* `severity`: `critical` (contradicts the law) · `serious` · `warning` · `info`.
* `verdict`: `compliant` · `minor` · `conflict`. `recommendation`: `accept` · `revise` · `reject`.
* `token` events are the summary. The first sentence should be one plain answer. `- ` lines become bullets and `**bold**` is bold.

Non-streaming alternative: return one object with the keys `steps`, `checks`,
`sources`, `findings`, `summary`, `verdict`, `recommendation` and `score`.

### `POST {MEZON_AI_URL}/v1/chat`

```json
{"request": {…same as above…}, "analysis": {"verdict":"conflict","summary":"…","findings":[…]},
 "history": [{"role":"user","content":"…"},{"role":"assistant","content":"…"}],
 "message": "Bandlarni qanday tuzatish kerak?"}
```

Stream `{"type":"token","text":"…"}` lines, or return `{"answer":"…"}`.

## What Mezon stores

Each run is an `Analysis` row with the steps, the checks, the sources, the summary,
the verdict, the backend and model name, the rules version, and a **SHA-256 fingerprint of
all document text**. A conclusion can therefore always be traced to the exact text
it was made on. Each finding is a `Finding` row. The human decision is stored
separately in `Decision`, together with the AI recommendation at that moment, which is
how the dashboard measures "AI bilan moslik" (how often experts agree with the AI).

If the model is unreachable or answers badly, the run is stored as `failed`. The expert
then sees the error and a "Qayta urinish" (retry) button. A half-made verdict is never shown.
