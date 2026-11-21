# Applying Mezon UI kit 2.0 to the platform

Target: `D:\10_projects\mezon_platform_original\static\mezon-ui\` (Django). The platform uses the v1.0 kit and the v2 kit keeps the same class names, so this is a swap, not a rewrite. Do it after the other agent finishes editing the platform.

## 1. Files (in this order)

| From `docs\ui-kit\` | To `static\mezon-ui\` | Notes |
|---|---|---|
| `css\tokens.css` | `tokens.css` | Superset of the v1.0 variable names. Safe to overwrite. |
| `css\components.css` | new file `components-v2.css`, loaded AFTER `components.css` | Override layer. Every selector keeps its v1.0 name, so nothing breaks. When the pages look right, delete the overlap from the old file. |
| `js\kit.js` | not needed | It drives the kit page demos. The platform's own `kit.js` stays. Copy only `initComposer` (drop and paste) and `replaySteps` if the chat should use them. |
| `assets\icons.svg` | already in `templates\includes\sprite.html` | Same sprite as v1.0. Nothing to do. |

In `templates\base.html`, add one line after the `components.css` link:

`<link rel="stylesheet" href="{% static 'mezon-ui/components-v2.css' %}">`

Dark theme: the kit applies dark only through `[data-theme="dark"]` (no `prefers-color-scheme` block). The platform's `base.html` head script already sets `data-theme` from `localStorage('mezon-theme')`. Keep it, and keep light as the default (no matchMedia fallback).

## 2. Tokens that change value

| Token | v1.0 | v2.0 | Why |
|---|---|---|---|
| `--flag`, `--flag-ink`, `--flag-soft`, `--flag-line`, `--on-flag` | missing | `#e8590c`, `#b3410a`, `#fdefe6`, `#f4c3a6`, `#0b0b0b` | The one accent. Text on white uses `--flag-ink` (5.7:1). `--flag` alone is 3.6:1, so only for fills, dots and rules. |
| `--warning*`, `--serious*`, `--critical*` | amber / orange / red | aliases of `--flag*` | Removes three competing alert colours. Old templates keep working and turn orange. |
| `--good`, `--good-ink`, `--good-soft` | `#0c8a0c`, `#17621a`, `#e8f3e5` | `#2d8a4e`, `#1d6b34`, `#e9f4ec` | Quieter green, status only (kuchda, ijobiy). |
| `--radius-xs/sm/md/lg/xl` | 6 / 8 / 12 / 16 / 22 | 4 / 6 / 8 / 12 / 16 | Tighter. Buttons and inputs use `--radius-md` (8). |
| `--text-display/h1/h2/h3` | 44 / 32 / 24 / 18 | 40 / 28 / 20 / 16 | Calmer scale. |
| `--ground`, `--canvas`, `--surface-sunken`, `--line`, `--ink-2` | `#ecece8`, `#fbfbfa`, `#f4f4f1`, `#e6e5e0`, `#4c4b47` | `#efefec`, `#fafaf9`, `#f5f5f3`, `#e7e6e2`, `#4a4944` | Marginal. |
| dark `--flag*`, `--good*` | n/a | `#ff8a4c`, `#ffa270`, `#2a1a10`, `#4fbf74`, `#7fd49a`, `#122219` | Re-picked for the dark surface `#171716`, all 4.5:1 or better. |
| `--focus-ring` | missing | `0 0 0 2px surface, 0 0 0 4px focus` | New. |

Spacing, motion, shadows, `--data-*`, `--seq-*`, `--tint-*` and `--on-*` are carried over unchanged.

## 3. Classes restyled in place (same name, new look)

- Buttons: `.btn .btn-primary .btn-secondary .btn-ghost .btn-sm .btn-lg .btn-icon .btn-block .kbd`. Primary stays black. `.btn-danger*` is gone in v2: use `.btn-secondary`; the alert colour belongs to status, not to actions.
- Forms: `.input .select .select-wrap .textarea .check .radio .switch .segmented .field .field-label .field-help .input-wrap .input-sm`.
- `.badge[data-tone]`: v2 has `good`, `flag`, `outline` and the neutral default. Map `warning`, `serious`, `critical` to `data-tone="flag"` (the aliases already make them orange; rename in templates when convenient).
- Layout and data: `.count .chip .tabs .tab .panel .panel-head .panel-title .panel-body .panel-foot .panel-actions .kpi-row .kpi .kpi-label .kpi-value .kpi-foot .table .table-wrap .td-main .td-sub .legend .legend-item .legend-sw`.
- Feedback: `.alert .toast .toast-host .tooltip .menu .menu-item .skeleton .spinner`.
- Chat: `.msg .msg-user .msg-ai .msg-main .msg-text .msg-meta .msg-actions .msg-error .bubble .caret .composer .composer-input .composer-bar .attach .send .cite .model-select`.
- Widgets: `.widget .widget-head .widget-title .widget-body .widget-foot`.

## 4. Classes that are NEW in v2 (templates must adopt them)

| Class | Use | Platform template |
|---|---|---|
| `.kpi[data-tone="flag"]` | orange rule on the ehtimoliy buzilish KPI | `dashboard.html` |
| `.compbar` with `<i data-k="flag\|ok\|none">` | 446,859 = 326 + 884 + 445,649 composition bar | `dashboard.html` |
| `.minibar` | inline bar in a table cell | `dashboard.html`, `eqaror.html` |
| `.filterbar` | filter row above lists | `request_list.html`, `eqaror.html` |
| `.case-list .case-row[data-state="flag\|ok"] .rule .case-title .case-meta .case-end` | flagged-decision rows; the whole row is clickable through `a::after` | `request_list.html`, `eqaror.html` (replace `.req-table` rows) |
| `.src-badge` (`data-src="ai"` for dashed) | source badge "Qoidalar mexanizmi (AI emas)" | `_check_card.html`, `review.html` |
| `.law-card[data-status="weak"] .law-head .law-title .law-ref .law-dates .law-note` | kuchda / kuchsiz law card | `review.html`, `eqaror_detail.html` |
| `.flag-card .flag-top .flag-title .flag-why .flag-foot` | flag card (replaces `.finding`) | `_check_card.html` (replace `.finding`, `.cause`) |
| `.pdf-panel .pdf-bar .pdf-stage .pdf-page` | original PDF panel | `eqaror_detail.html` |
| `.state[data-kind="error"] .state-icon .state-title .state-text` | empty and error states (replace `.empty`, `.empty-title`) | all list templates |
| `.skel-row` | loading rows | list templates |
| `.chat .chat-head .chat-log .chat-foot .msg-avatar` | chat shell | `ai_chat.html`, `review.html` (`.review-chat`) |
| `.steps .step[data-state="wait\|run\|done"] .step-mark .step-time` | live agent step list | `ai_chat.html` |
| `.trace .trace-row[data-res="ok\|weak"]` | `law_as_of(...) -> kuchda` rows | `ai_chat.html` |
| `.gpu-badge` | orange "Mezon-LM · GPU · 14 s" | `ai_chat.html` (replaces the model text in `.msg-meta`) |
| `.model-menu .model-opt` | model selector menu (replaces the native `.model-select`) | `ai_chat.html` |
| `.dropzone`, `.composer[data-drag]`, `.composer-attach` | file drop and paste | `ai_chat.html`, `review.html` |
| `.facts`, `.found .found-head .found-foot` | "Aniqlangan ma'lumot" box and summary facts | widgets in `partials\` |
| `.verdict[data-verdict="ok\|fix\|neg"] .verdict-head .verdict-mark .verdict-list .verdict-scale` | 3333-format conclusion card | `review.html` |
| `.quote` with `<mark>` | article quote with the article highlighted | `review.html`, `_check_card.html` |
| `.suggest` | suggestion chips (replace `.chip-q`) | `ai_chat.html` |
| `.mismatch .pair` | answer-versus-tool mismatch warning | `ai_chat.html` |

## 5. Platform classes v2 does not provide

Leave their existing CSS in `components.css` / `app.css`: `.mz-matrix .mz-tile`, `.req-table`, `.td-cta .td-when .td-from .td-num .td-title`, `.hide-sm .hide-md .hide-xs`, `.widget-stack`, `.meta-list`, `.title-link`, `.cta-label`, `.nav-item`, `.sidebar`, `.topbar`, `.pager`. They only need the new tokens, which they get automatically.

## 6. Content rules to carry into templates

- Never "noqonuniy" or "Qonunga zid". Write: **ehtimoliy buzilish, ekspert ko'rib chiqadi**.
- Show the source on every flag: `.src-badge` "Qoidalar mexanizmi (AI emas)" for rule flags, dashed `data-src="ai"` for Mezon-LM output.
- Orange only for ehtimoliy buzilish and alerts. If a template uses `--flag` for a chart series, nav item or button, change it to `--ink` or `--ink-3`.
- Ordinary buttons are black. No orange buttons.
- The kit's region table is the 2026-11-19 snapshot (`data\interim\snapshots\2026-11-19.json`, 277 flagged). Replace it with the live query in the Django view.

## 7. Check after the swap

1. `python manage.py collectstatic`, hard reload, toggle light and dark with the theme button.
2. Tab through `dashboard.html` and `ai_chat.html`: every control shows a 2 px ring (black in light, off-white in dark).
3. Search the templates for `critical`, `serious`, `warning`: all now render orange, and each must mean ehtimoliy buzilish or an error.
