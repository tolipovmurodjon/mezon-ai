# Collecting E-qaror adoption stages

1. In Chrome, open any `https://e-qaror.gov.uz/search` page, paste `research/eqaror_stages.js` with the browser's javascript tool, then run `mzRun([{set:'bad', url:'/search?release=200&page=1', page:1}], 'list')`.
2. Turn list rows into doc jobs `{set, url:'/doc/<id>', id, reg, page, pos, title, body, date, is_normative}` and run `mzRun(jobs, 'doc')`; poll `window.__mz.done`.
3. Export in slices of ~50: `__mz.out.slice(a, b).map(mzLine)` and save the JSON array to a file, then `uv run python -X utf8 -m research.eqaror_save <file.json>` (appends to `data/interim/eqaror_stages.csv`, dedupes by set + url).
4. `uv run python -X utf8 -m research.stage_lift` prints skip rates and lift with 95% CIs.
5. Keep the tab in the foreground (background tabs are throttled), one page at a time; the site stopped answering after ~700 page loads in one session, so pause between big runs.
