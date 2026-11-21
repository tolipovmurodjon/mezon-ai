# Mezon: how we get and use data (one page for the jury)

Every line below is how the code runs today (`research/polite_http.py`, `mezon/sync/*`); nothing is aspirational.

## Sources: public only

- **lex.uz**: published acts and their own notes ("LexUZ sharhi"), RSS, cites / cited-by pages.
- **regulation.gov.uz**: public draft pages and the drafts' own PDF links.
- **E-qaror**: public filter pages and stage trackers, read by hand in a browser; we stop when the site slows us down.
- **stat.sud.uz**: published statistics files (they count claims, not decisions, and we say so).

## How we fetch

- At most **one request per 1.2 seconds**, cache first: a page is fetched once and then read from disk.
- **No private or undocumented APIs**, no logins, no bot checks. Court ruling PDFs that sit behind a "not a robot"
  check are not downloaded by us; only an export or API access from the site owner, or a person, can provide them.
- Only documents that are already public and already redacted.

## How we process

- Decision texts are processed on **our own machines**; the language model runs locally. No decision text goes to a
  cloud AI service.
- **No citizen names** on any screen or in any output. We name bodies (a district hokimlik), never people.

## What the output is

- Every flag is a **possible violation for expert review**, never "illegal". Each carries the decision's exact words
  and the law's exact words as in force on the decision date; 354 of 354 citations are verified verbatim (19.11.2026; `python -m research.stage_numbers` prints the current figure)
  (`eval/report.md`).
- A human decides every flag (Adliya AI ethics rules No. 3787). Mezon never files, sends or publishes anything by
  itself; appeals are drafts the person sends themselves.
- Legality, not corruption: no rankings of officials, no accusations.
