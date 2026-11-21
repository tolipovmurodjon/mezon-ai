# E-qaror decision text: how to get it (21.11.2026)

## Endpoint (the page's own XHR, public)
The doc page `https://e-qaror.gov.uz/doc/<code>` calls `api-eqaror.gov.uz/v2/doc/stages` and `/v2/doc/show` (XHR), then shows the result in a `blob:` iframe. The same call works from curl with no cookies, no login, no captcha:

    GET https://api-eqaror.gov.uz/v2/doc/show?code=<32-hex code>&lang=oz
    Header: Referer: https://e-qaror.gov.uz/        (code = the `code` field of /v2/doc/list rows)
    -> 200 application/pdf, Content-Disposition filename="355-4-68-Q_25.pdf", real text PDF (pdftotext works, no OCR)

Response headers: `X-RateLimit-Limit: 120` (per window, remaining counts down: 117 after 3 calls), `Access-Control-Allow-Origin: *`, `Cache-Control: public`. No challenge, PoW or Turnstile seen. (Param `code` found on first guess; `id=` and path forms were not used after that.)

## Proof it is the same document
Code 5d128f2a... = Yakkabog' 355-4-68-Q/25 (13.11.2025; the page title shows it amends No. 343). Our lex.uz text (decisions.sqlite, 1,186 chars, body only) vs the E-qaror PDF via `research.textnorm.split_decision` + `similarity`: clauses 1-3 = 1.000, clause 4 = 0.612 (signature/annex tail differs), head-vs-lex char similarity 0.79. The PDF also carries the annexes (89K normalized chars) that lex.uz text lacks.

## Samples (data/cache/eqaror_text/<code>.pdf/.hdr/.txt)
| code | doc | PDF | time | text chars |
|---|---|---|---|---|
| 5d128f2a... | 355-4-68-Q/25 | 998 KB | 2.7 s | 121,803 |
| 59ac22e3... | 645-1-26-Q/26 (21.11.2026, same-day, available) | 637 KB | 1.7 s | 2,145 |
| d89406ef... | normative sample | 394 KB | 1.6 s | 31,942 |
| 18c9a4ff... | normative sample | 3.33 MB | 3.7 s | 941,399 |
| 3b6664c4... | normative sample | 519 KB | 1.6 s | 30,141 |
Average 1.17 MB, 2.3 s per doc (N=5). PDFs are large for their text (embedded fonts/page stubs).

## Estimate for all 446,806
- Rate 1.2 s spacing = 0.83 doc/s -> 446,806 x 1.2 s = 536,000 s = **149 h (about 6.2 days)** non-stop. One request takes 2.3 s, so use 3 workers each spaced 3.6 s apart (global 1 request per 1.2 s). Never faster: the 120 limit would hit.
- Bandwidth ~1 MB/s, ~520 GB in total transferred. **Do not keep PDFs** (D: is nearly full): keep only the text.
- Text at ~40K chars average (skewed by few huge ones) = ~18 GB raw, ~3-4 GB gzipped.
- Priority order cuts the wait: declared_invalid + normative + kengash first (a few thousand docs, under an hour), then by year descending.

## Bulk plan (not started)
1. Input: codes from the list API output (`data/raw/eqaror_api/<slice>/p*.json`, `research/eqaror_api.py`); build `todo` in a sqlite.
2. State: `data/raw/eqaror_text/state.sqlite` table (code, status todo/ok/empty/fail, http, bytes, secs, chars, ts). Resumable: only `todo`/`fail` rows run; STOP file pauses.
3. Layout: `data/cache/eqaror_text/<code[:2]>/<code>.txt.gz` (pdftotext -enc UTF-8 -layout, via ASCII temp name in scratch), PDF deleted at once; optional PDF kept only for docs where text < 200 chars (scan -> later OCR). Cache root can be moved with `MEZON_CACHE`.
4. Rate: 3 workers, one shared 1.2 s token gate, brake 60 s on any 429/5xx/slow (copy `eqaror_api.py` BRAKE), backoff 30/60/120/240 s, watch `X-RateLimit-Remaining` and sleep when < 10. If a captcha/challenge/403 appears: stop and report, never solve.
5. Ingest: a second step writes text into decisions.sqlite (`text`, `clauses`) matched by E-qaror code; the 1,210 lex.uz texts stay as the cross-check.
6. Privacy: individual decisions contain citizens' names; mask before training (refinery rule in eqaror_api.py header).

7. **Masking required:** the texts under data/cache/eqaror_text/ hold citizens' names (individual decisions). Private cache only, never in git; mask them before any training or publishing.
