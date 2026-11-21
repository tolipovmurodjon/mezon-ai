# Mezon platform (web app)

> Platform UI and Django app by **Zaynobiddin** ([Zaynobiddin33/Mezon_LLM](https://github.com/Zaynobiddin33/Mezon_LLM)), connected to the Mezon engine (law store, rules, Mezon-LM) in this repository. Live: [e-mezon.uz](https://e-mezon.uz).

## Mezon · hokimlik qarorlari ekspertizasi

A Django web app where legal experts review the draft regulations that hokims send in.
Mezon AI checks every draft against the law, the Constitution and basic ethics, then
recommends accepting or rejecting it. **The expert makes the final decision.** The UI is
built entirely from `../mezon-ui-kit` (tokens, components, `kit.js`).

## Run it

```bash
cd mezon-web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # synthetic data: 14 regions, ~530 requests, 180 days
python manage.py runserver 127.0.0.1:8040
```

Open http://127.0.0.1:8040 and sign in as **ekspert** with the password you set in `MEZON_DEMO_PASSWORD` (local demo user,
created by `seed_demo`). Admin: http://127.0.0.1:8040/admin/ with the same user.
Run `python manage.py seed_demo --reset` to start over (this wipes your changes). Tests: `python manage.py test regulations`.

## Screens

| Screen | URL | What it shows |
|---|---|---|
| Bosh sahifa | `/` | This week: received, accepted, rejected, in process (with change vs last week). Requests per day for 30 days as a pixel chart. AI verdict split. Latest requests. |
| So‘rovlar | `/sorovlar/` | All requests: from, hokim, draft title, number of documents, sent time, status, **Tekshirish**. Status tabs, search, region filter. |
| Tekshirish | `/sorovlar/<id>/` | Mezon AI reads all documents and streams its steps, then a verdict and the problems found (each with the draft's exact words, the law and a fix). Click a quote to see it in the document. Ask follow-up questions. On the right: request details, documents, and **Qabul qilish / Rad etish** (a reason is required to reject; a dialog confirms). |

## Plugging in your model

Set `MEZON_AI_BACKEND`. Nothing else changes. See **[docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md)**.

```bash
# fine-tuned model behind vLLM / Ollama (OpenAI-compatible API)
MEZON_AI_BACKEND=openai MEZON_AI_URL=http://127.0.0.1:8000/v1 MEZON_AI_MODEL=mezon-qonun python manage.py runserver 127.0.0.1:8040

# your own agent service (e.g. FastAPI on :8090) speaking the Mezon event contract
MEZON_AI_BACKEND=http MEZON_AI_URL=http://127.0.0.1:8090 python manage.py runserver 127.0.0.1:8040
```

Until then, the `demo` backend runs 14 real rule checks on the document text: legal basis,
articles that lost force, competence (hokim vs Kengash), document form, retroactivity,
the 3-month rule for business, public discussion (15 days), tax timing, duplicates,
citations, anti-corruption factors (O‘RQ-860), mixed Latin/Cyrillic text (VMQ-662),
rights and ethics, and funding source. Its answers are labelled **Demo analizator**.

## Adding real requests

Use the admin today: **So‘rovlar → Add**. Attach documents as files (`.txt`, `.docx`;
`.pdf` too if `pypdf` is installed) or paste the text. Text is extracted automatically.
An intake API for hokimliks is the natural next step.

## Layout

```
mezon/                 settings (all env-driven), urls
regulations/
  models.py            Region, RegulationRequest, Document, Analysis, Finding, Decision, ChatMessage, Event
  services.py          run_analysis / run_chat (stream + persist), decide, mark_opened
  stats.py             dashboard numbers
  ai/                  base contract, demo + rules, laws registry, http and openai adapters
  management/commands/seed_demo.py
templates/             layouts/app.html shell + pages + partials (AI widgets)
static/mezon-ui/       tokens.css, components.css, kit.js: unmodified copies from ../mezon-ui-kit
static/css/app.css     page layout only, on kit tokens
static/js/app.js       pixel chart, SSE streaming, chat, document viewer, decision dialog
```

If you change the kit, copy `css/tokens.css`, `css/components.css` and `js/kit.js` into `static/mezon-ui/` again.

## Production notes

Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
then run `collectstatic`. Streaming responses need a proxy with buffering off (`X-Accel-Buffering: no`
is already sent) and a threaded or async server, for example `gunicorn -k gthread --threads 8`.
Move from SQLite to PostgreSQL before real data. Delete the demo user and create real accounts.

All data from `seed_demo` is **synthetic**: hokim names are invented, and law references are
samples for the demo checks. The UI says "Namuna ma’lumotlar" while the demo backend is active.
