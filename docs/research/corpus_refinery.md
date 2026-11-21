# Corpus refinery: from the raw lex.uz crawl to a clean, dated training corpus (design, 20 Nov 2026)

Public sources only. No Mezon data was sent anywhere. Local checks ran on the laptop cache (149 act pages, 40 PDFs, 2 edition files), not on the box.

Tags: **[full]** I read the paper text (PDF to text, targeted sections). **[abstract]** abstract page only. **[snippet]** search-result summary only. **[ours]** measured on our own code or cache today. **[estimate]** my arithmetic or judgment, with the assumption written next to it. "not found" means I looked and the source did not say.

## 0. Findings that change the design (read this first)

1. **The crawl already contains a better edition format than "one file per edition".** `mezon/lawstore/build.py::_store_editions` turns editions into *unit intervals*: a unit whose text did not change is stored once with `valid_from`/`valid_to` (half-open: `valid_to` = start of the next edition). The refinery should reuse that logic as a pure function (no SQLite), not MinHash the editions. [ours]
2. **`parse_units` is built for lookup, not for training text.** It (a) drops `ACT_TITLE`, `ACT_FORM`, `SIGNATURE`, `TEXT_HEADER_DEFAULT` (chapter headings), `ACT_ESSENTIAL_ELEMENTS`, so title, preamble form and chapter structure are lost; (b) writes the same sentences twice, once in `art:N` (it appends every part to the article text) and again in `art:N/part:K`; (c) returns zero units for 13 of 149 cached pages (8.7%) [ours]. A training document must be assembled in document order by a second function, while `parse_units` keeps feeding the unit table. Never sum article and part units when counting size.
3. **`textnorm.normalize` and `fold` are for matching only.** They transliterate to Latin and delete apostrophes. Training text must keep the original script and the official apostrophe forms. Today's pages use U+02BB for o' and g' ("Oʻzbekiston", "toʻgʻrisidagi") and U+02BC for the separator ("maʼlumotlari"); the bench answers use the same forms [ours]. Do not collapse them.
4. **Latin pages carry Cyrillic homoglyphs.** A Latin-script title on a cached page reads "3966-сон 31.10.2026. Tovarlarni import qilishda..." [ours]. Without a homoglyph pass this creates mixed-script words and splits tokens.
5. **Legacy cache keys can point a twin at the wrong file.** Until 20.11 editions and panels were cached without the sign, so x and -x shared a file. `fetch._legacy_reuse` decides by title similarity or Cyrillic share. The refinery must repeat that check (script share of an edition vs. its own doc page, difference > 0.2 = reject) before using any `editions/{id}/...` file without `_m`/`_p`. [ours]
6. **Corpus size is not the bottleneck; GPU time is.** The refinery will likely produce about 1 to 2B tokens [estimate, section 7], while the recipe's one-card budget is 0.5 to 1B CPT tokens (`docs/research/law_school_recipe.md`). So quality tiers and sampling weights matter more than keeping everything.
7. **Raw 120 GB is mostly not text.** In our sample the extracted text is 11.9% of the HTML bytes (149 pages) [ours], and the crawl also holds PDFs, ZIPs, images. Final text is a few GB at most [estimate].

## 1. How experts build these corpora (numbers and what we take)

| Work | What they do | Numbers | Take for us |
|---|---|---|---|
| FineWeb (Penedo et al. 2024) [full] | trafilatura on WARC beat default WET text ("WET retained too much boilerplate and menu text"); URL blocklist; fastText language ID, keep English score >= 0.65; MassiveText repetition/quality filters at original thresholds; MinHash on 5-grams, 112 hashes as 14 buckets x 8; cluster transitively, keep one per cluster; C4-style filters; custom filters; PII: anonymise emails and public IPs | match probability at n-gram Jaccard 0.7 / 0.75 / 0.8 / 0.85 = 56% / 77% / 92% / 98.8%; global dedup over 96 snapshots removed up to 90% of the oldest crawls and gave little gain, per-snapshot dedup was better; 15T tokens | Extraction quality matters more than people expect. Dedup **within strata**, not globally. Use 14x8 as our default and compute the match curve before trusting it |
| FineWeb-2 [full, via `law_school_recipe.md`] | per-language MinHash 14x8, duplicate count kept and used for upsampling ("rehydration") | 1,868 language-script pairs, ODC-By | Keep `dup_count` on the survivor instead of silently deleting |
| RefinedWeb, Pile-CC, SlimPajama, RedPajama-v2, Dolma [full, FineWeb related-work paragraph] | RefinedWeb: trafilatura + MinHash + ExactSubstr; Pile-CC: jusText + MinHash; SlimPajama: removes short docs then MinHash; RedPajama-v2: 84 snapshots released with quality and dedup labels, nothing deleted; Dolma: Bloom filter dedup at URL, document and paragraph level | | Label first, delete later: store every signal as a column so thresholds can move without re-extracting |
| Lee et al. 2021 [snippet] | NearDup = MinHash match plus edit similarity > 0.8; ExactSubstr removes shared substrings (50 tokens per a secondary source) | 1.68% of C4 near-duplicate; models emit memorised text about 10x less after dedup | Dedup is also a privacy tool: repeated strings are the ones a model memorises |
| MultiLegalPile (Niklaus et al. 2023) [full] | four subsets; EUR-Lex via the `eurlex` R package (SPARQL), converted to jsonl; legal mC4 found by citation regexes, precision hand-checked on n=20 per language, regexes tightened once | 689 GB, 24 languages, 17 jurisdictions; native 112 GB, EUR-Lex 179 GB, legal mC4 106 GB (133 GB before the second regex round), Pile of Law 292 GB; **no deduplication performed**, they cite that repetition up to four epochs does not hurt | Even the big legal corpus did not dedup. Our reason to dedup is narrower: template decisions copied across 200 districts |
| Pile of Law (Henderson et al. 2022) [full, targeted] | collects public legal text; **does not redact further**: each source already follows its own jurisdiction's privacy norms; says plainly that the data contains PII | about 256 GB; across jurisdictions the baseline everyone protects is minors, account numbers and ID numbers | Our sources are not a court with redaction rules, so we mask. The baseline list (minors, ID numbers, account numbers) is the minimum |
| SaulLM-7B / 54B / 141B [full, via `law_school_recipe.md`] | NFKC, regex removal of page and line numbers, KenLM perplexity filter trained on a small clean legal set | similarity threshold 0.5 in their dedup tool; normalised perplexity cut 1500; >30B legal tokens after dedup from a 500B crawl (54B/141B) | Page-number regexes and an in-domain perplexity filter. A 0.5 threshold would delete our legitimately similar editions |
| EUR-Lex derivatives [snippet] | Chat-EUR-Lex keeps the original text of never-amended acts and the latest consolidated text of amended acts; Super_EURLEX has 4.6M documents, with consolidated acts as their own sector | one source says consolidated texts "have no legal value" (reference only) | Their choice is one version per act. We need dates, so we keep intervals (section 3). The legal-value point matches our `provisional` flag |
| Common Corpus [snippet] | open and public-domain data incl. government and legal documents | 1,998,647,168,282 tokens, over 40% non-English; OCR correction method: not found | Nothing to copy on OCR; use our own dictionary-hit check |
| FreeLaw in The Pile | not fetched | not found | no claim |
| Any paper training on all editions of a statute | looked; **none found** | | Our edition policy is a judgment call (section 3), to be tested by the in_force and flip families of MezonBench |

## 2. Layout on the box

Everything under `D:\10_projects\mezon\data\refinery\` (box: `~/mezon/data/refinery/`). Every stage writes shards `part-00000.jsonl.zst` (about 50 MB each), a `_DONE` marker per shard, and is resumable and deterministic (sorted inputs, fixed seeds). A stage never edits the previous stage's files. `config.yaml` holds every threshold below; `manifest.json` records config hash, input counts, output counts, drop counts per reason.

```
data/refinery/
  config.yaml                  thresholds, regexes, cutoffs (one place)
  manifest.json                per stage: counts in/out, drops by reason, seconds
  00_census/census.parquet     one row per cache file: kind, key, bytes, lex_id, sign, edition date
  01_extract/
    acts/part-*.jsonl.zst      one raw extraction per (lex_id, source): text in doc order, tables, metadata blobs
    pdf/part-*.jsonl.zst       local decisions from files/*.zip|pdf (pdftotext)
    ocr/part-*.jsonl.zst       data/ocr/<key>.md cleaned
    unit_versions/part-*.parquet   unit intervals (the store logic, no SQLite)
  02_meta/acts.parquet         one row per lex_id (schema 4a)
  03_norm/docs/part-*.jsonl.zst    normalised text (script kept, apostrophes canonical, homoglyphs fixed)
  04_dedup/
    twins.parquet              lex_id, twin_id, family_id, sim, verdict
    exact.parquet              sha1 groups
    minhash_clusters.parquet   cluster_id, member, keep, dup_count
  05_filter/
    signals.parquet            every quality signal per doc (nothing deleted yet)
    decisions.parquet          keep / drop / drop_reason per doc
  06_safe/
    pii_report.parquet         per doc: counts per category (never the strings)
    leak_report.parquet        per unit/chunk: bench overlap, golden-case membership
    docs/part-*.jsonl.zst      masked, leak-cleaned documents
  07_train/
    cpt_docs/part-*.jsonl.zst  headered chunks <= 4096 tokens (+ 10% long chunks)
    lesson_inputs/part-*.parquet   input for research/law_school_data.py (schema 4c)
    amendment_docs/part-*.jsonl.zst   rule-made "article X changed" documents
    held_out/                  ids and hashes only (what was withheld and why)
  09_audit/pilot/              pilot sample, viewer HTML, reports (section 8)
```

## 3. Step 1: extraction per document type

Source keys come from `research/lexuz_full.py` and `mezon/lawstore/fetch.py`: `docs/{id}_{p|m}.html`, `editions/{id}_{p|m}/{dd.mm.yyyy}_{NN}.html`, `actinfo/{revhis,correspondents,respondents,card1,card2,basrev}/...`, `pdfs/{tag}.html`, `files/{fileid}.zip|pdf`, `pdf/{tag}.pdf` (skipped on the box), `img/...`, and `data/ocr/<key>.md`. Sign convention: `_p` = id x, `_m` = id -x.

**Stage 00, census.** Walk the cache once, write sizes and keys. Output also answers the unknowns this document cannot (counts by type, editions per act, PDFs per act, scanned share). Run this first; every estimate below is replaced by its numbers.

**1a. National act HTML (current page and edition pages).** Function `extract_html(page) -> ActText`:
- Root `#main_container1`. Walk `div.lx_elem` in document order; kind = the class next to `lx_elem`. Take text from the inner `div[id]` (it excludes the "Hujjatga taklif yuborish / Audioni tinglash / Hujjat elementidan havola olish" widget text that sits in the outer element) [ours].
- Keep, in order: `ACT_TITLE`, `ACT_FORM` ("Oʻzbekiston Respublikasining Qonuni" line), preamble (`ACT_TEXT`/default), `TEXT_HEADER_DEFAULT` (chapter and section headings, as lines), articles (`CLAUSE_DEFAULT` matching `N-modda`), numbered clauses and list items, annex banners (`ACT_TITLE_APPL`, `APPL_BANNER*` become an `[ILOVA n]` line), signature line (`SIGNATURE`; names handled in section 6).
- Move out of the text into metadata (never into the body): `ACCEPTING_BODY` (issuing body), `DEPARTMENTAL` registration line ("Adliya vazirligi tomonidan ... roʻyxatdan oʻtkazildi, roʻyxat raqami N"), `PUBLICATION_ORIGIN` ("Qonunchilik maʼlumotlari milliy bazasi, 02.11.2026 y., 10/26/3966/1089-son"), `INDEXES_ON_REF` (OKOZ and TSZ topic codes), `act_warning` ("Hujjat hali kuchga kirgan emas" gives status `not_yet_in_force`), the red amendment banner (`has_pending_banner` gives `provisional=true`), `<ins data-revive...>` ad elements (delete), images.
- Inline "(... tahririda)" notes (`CHANGES_ORIGINS`): remove from the body of the *training* text, store them as `amended_by` (date + act id parsed from the `?ONDATE=` link, as `parse.note_dates` does). Rationale: they are navigation, not law, and a model that reads them in the middle of a clause learns to produce them. Keep them in `unit_versions.notes` for lesson building.
- Tables (`TABLE_STD2` and any `<table>`): render rows as `cell | cell | cell`, one row per line, header row first, merged cells repeated. Flag `n_table_chars`, `table_numeric_share`.
- Fallback when `lx_elem` yields no units (13/149 pages [ours]): these are PDF-only local decisions or scan-only national acts; route to 1b/1d, or, if the page has body text without `lx_elem`, take `main_container1` text with a tag-stripping fallback and mark `source_kind=html_fallback` (lower tier).
- Document-order assembler is a new function; `parse_units` stays untouched and still builds `unit_versions` (article and part levels), because lessons need part-level units.

**1b. Editions.** One `ActText` per edition file, keyed `(lex_id, ondate)` where `ondate` = "dd.mm.yyyy NN" (NN = same-day sequence). Reject an edition file whose script share differs from its doc page by more than 0.2 (legacy shared-twin files, finding 5). Dedupe pages that are byte-identical after extraction (identical editions happen when an amending act changed only another act). Build `unit_versions` by the same interval merge as `_store_editions`, refactored as `unit_versions(editions: list[(iso_date, units)]) -> rows` with no database.

**1c. Local decisions, PDF/ZIP.** Function `extract_pdf(path) -> list[PdfText]`:
- `files/<fileid>.zip` holds one PDF; names inside can be Cyrillic ([ours]: `VI-40-46-4-56-K21 ?????.pdf`), so read bytes with `zipfile`, **write to an ASCII temp name** (`x.pdf` in a fresh temp dir), call `pdftotext -enc UTF-8 -layout x.pdf -`. A ZIP with several PDFs gives `key__i` as `ocr_scans.pdfs_in` does.
- Scanned test: fewer than 200 characters on pages 1 to 3 goes to OCR (the 12.7% rate in `ocr_scans.py` is from 45/355 [ours]; the 40-PDF local sample had 0 scanned). Otherwise keep the text.
- `-layout` keeps columns, which helps tables and hurts running text (hyphenated line breaks, column interleaving). Post-process: join hard-wrapped lines (a line not ending in `.;:!?` followed by a lowercase start), re-join words split by a trailing hyphen only when the joined form appears in the corpus vocabulary, drop page furniture (below).
- Page furniture: `textnorm._PAGE_ARTEFACTS` (the "e-qaror.gov.uz dd.mm.yyyy" header, bare page numbers), plus a generic rule: a line that, with digits removed, occurs on more than 30% of a document's pages is a header or footer and is dropped (also lines containing "lex.uz" or a URL). Saul does the same class of cleanup (page and line numbers by regex) [full].
- Structure: reuse `split_decision` only to *find* preamble, "QAROR QILAMAN/QILADI:" operative part, numbered clauses, annex, signature. Its output is folded (lowercase, no apostrophes), so never use its text, only its offsets: re-run the same regexes on the unfolded text to cut spans. Clause units get paths `cl:N`, annexes `annex:A/cl:N`, same grammar as `parse.py`, so lessons work unchanged.
- Registration number: `research/regnum.py::parse` on the PDF head and on the doc page metadata (two sources, they must agree; disagreement goes to `meta_conflict` for the report).

**1d. OCR markdown.** `data/ocr/<key>.md` from PaddleOCR-VL. Strip `<!-- page N -->`; any page with `<!-- OCR failed` marks the document `ocr_partial` (drop below 90% of pages good); convert HTML tables to the same pipe rows; strip image placeholders and markdown emphasis; reuse 1c page-furniture logic. Tier C by default (section 5).

**1e. Russian and English versions.** The crawler always asks `/uz/docs/<id>`; ids found in `/ru/` or `/en/` links are queued as is. Decide language **per document from the text**, not from the URL: Cyrillic share, then Uzbek-specific letters (ў қ ғ ҳ) present gives `uz-Cyrl`, absent gives `ru`; Latin text with Uzbek markers (`oʻ`, `gʻ`, `sh`, `ch`, high-frequency Uzbek stopwords) gives `uz-Latn`, with English stopwords `en`. Rules first (the sources are structured, so a statistical identifier is only a cross-check on the pilot: run fastText lid.176 on 2,000 docs and compare; FineWeb used fastText with a 0.65 cut for web pages [full]). Russian and English documents are kept as separate documents and linked to their Uzbek counterparts by `(act number, adopted date)` in `family_id`; they are never merged or deduped against the Uzbek text, because they share no tokens.

## 4. Record schemas

### 4a. `02_meta/acts.parquet`, one row per `lex_id` (signed string, as crawled)

| Field | Meaning and source |
|---|---|
| `lex_id`, `abs_id` | "-6986157" and 6986157 |
| `twin_id` | other-sign id if confirmed the same act (section 6), else null |
| `family_id` | min abs id of confirmed twins; Russian/English links join through number+date |
| `lang`, `script` | `uz`/`ru`/`en`, `Latn`/`Cyrl`; `lang_conf` = rule that fired |
| `act_type` | `constitution, law, code, chamber_resolution, pf, pq, f, vmq, ministry_order, local_hokim_qaror, local_kengash_qaror, local_farmoyish, court, other`. National types from title badge and number (`CORE` map in `build.py` is the seed list); local types from the registration number letter (Q, K, F) via `regnum.parse` |
| `level` | `national` / `local` (drives PII policy) |
| `number`, `reg_number` | act number from title; registration number (`231-4-59-Q/24`) |
| `body` | `ACCEPTING_BODY` text; `region_code`, `district_code` from `regnum` for local acts |
| `adopted` | ISO date from the title ("31.10.2026") |
| `in_force_from` | first edition's `valid_from`; null if `not_yet_in_force` |
| `editions` | list of `{ondate, valid_from, valid_to, provisional}` |
| `status` | `in_force`, `lost_force`, `not_yet_in_force`, `unknown` |
| `lost_force` | date + `cancelled_by` lex ids, from the LexUZ note, `actinfo/revhis`, `card1` (field names of card1 not yet checked: day 1 of the pilot) |
| `provisional` | red "HUJJATGA O'ZGARTIRISH KIRITILMOQDA" banner on the latest edition |
| `topics` | OKOZ and TSZ codes |
| `registration` | Ministry of Justice registration text and number |
| `source_url`, `source_kind` | `https://lex.uz/uz/docs/<id>`; `html`, `html_fallback`, `pdf_text`, `ocr` |
| `source_keys` | cache keys used (reproducibility) |
| `sha1_raw` | hash of the raw bytes |
| `cites`, `cited_by_n` | ids from correspondents panel; count from respondents |
| `eval_flag` | `none`, `golden`, `bench_family`, `cancelling_act`, `time_cut` (section 8b) |

### 4b. `01_extract/unit_versions`, one row per unit path per content interval

`lex_id, family_id, path` (`art:N`, `art:N/part:K`, `cl:N`, `annex:A/cl:N`, `pre:K`), `heading, text, valid_from, valid_to` (ISO, half-open, null = still current), `ondate_first`, `notes` (amendment notes with act ids), `text_sha1`, `prev_text_sha1`. Same columns as the store's `units` table so `research/mezonbench.py` and `law_school_data.py` keep working. Article rows contain their parts' text (parse.py behaviour): `is_container=true` marks them so size counts and CPT assembly skip them.

### 4c. `07_train/cpt_docs`, one row per training chunk

```
{ "doc_id": "<lex_id>:<chunk>", "lex_id": "-6986157", "family_id": 6986157, "twin_id": "6986157",
  "lang": "uz", "script": "Latn", "act_type": "local_kengash_qaror", "level": "local",
  "number": "...", "adopted": "2024-...", "valid_from": "...", "valid_to": null, "status": "lost_force",
  "tier": "A|B|C", "source_kind": "pdf_text", "source_url": "https://lex.uz/uz/docs/-6986157",
  "dup_count": 1, "pii": {"names": 3, "ids": 0}, "eval_flag": "none",
  "header_chars": 190, "text": "<header>\n<body>", "n_chars": 0, "n_words": 0 }
```

Header (constant Latin labels, values in the document's own script, ISO dates, same date format as MezonBench so the model sees one format):

```
[HUJJAT] <title> | tur: kodeks | raqam: ... | qabul: 2019-12-30 | tahrir: 2025-01-01 dan 2025-04-09 gacha | holat: amalda | til: uz-Latn | lex: 4674902
```

Long acts are split at article boundaries (never mid-article unless one article exceeds the limit), the header repeats on every chunk, with chapter headings carried as a second line. `header_chars` lets the trainer mask loss on the header for half of the samples (recipe section 6).

### 4d. `07_train/lesson_inputs`, input for `research/law_school_data.py`

Columns equal to what `lesson()` reads today: `act_key, path, heading, text, valid_from, valid_to`, plus `act_type`, `act_name`, `prev_text` (previous interval of the same path, replaces the in-memory `prev` dict). Needed code changes: read parquet instead of `LAW_DB`; extend `FORCE` (add the local types and `court`, `ministry_order`); `act_name` and `human_path` in `mezonbench.py` for local acts and `cl:N`/`annex` paths. Lessons only from documents that passed sections 5 to 8, never from `is_container` rows, never from held-out units. Lessons for local decisions use the clause-level kinds (`where`, `cloze`, `tf`, `since`, `force`); `heading` and `change` kinds apply only to national acts with editions.

## 5. Editions: what to keep, how to label dates

Decision [judgment, no paper trains on editions; the evidence is our own bench failure plus LegalSearch-R1's validity windows from `law_school_recipe.md`]:

| Tier | Training document | Why |
|---|---|---|
| **A** | latest edition of each act, full text in document order, header with `tahrir: valid_from dan hozirgacha` | the law as it stands; one copy per act |
| **A0** | the *original* (first) edition in full, only if its folded text differs from A by Jaccard (char 5-shingles, `textnorm.similarity`) < 0.97 | "as originally adopted"; skip when nearly equal |
| **B** | **amendment documents** generated by rule from `unit_versions`: "On `<date>`, article N of `<act>` was changed. Before (valid `<from>` to `<to>`): ... After: ...", with the amending act id from the note | teaches that text is dated, costs only the changed units, and builds the in_force/flip skill (35% and 21% base accuracy) |
| **B2** | selected intermediate editions in full: the edition in force on each bench date, plus 1 in 5 others (seeded) | keeps some full-text anchors per date without 5x the tokens |
| none | every other intermediate edition as a whole document | reconstructable from A + B; copying them is exactly what a 0.5 to 0.8 MinHash would flatten anyway |

Label rules:
- Dates are ISO in the header and in lessons. `valid_from` = the edition's start date from the `?ONDATE=` link; `valid_to` = next edition's start (half-open, as the store does), null for the current one. Same-day editions: the `NN` suffix orders them; only the last one of a day is "in force" at end of day.
- An edition with the red banner gets `provisional: true` in the header (`holat: oʻzgartirish kiritilmoqda`); the text is real but unmerged. Provisional editions are tier B2 at most.
- `lost_force` acts keep their text with `holat: kuchini yoʻqotgan` plus the date; they stay in training (the model must know repealed law exists and is dated), but the lesson kinds `force`/`since` use the date.
- `not_yet_in_force` acts: header `holat: kuchga kirmagan`, `valid_from` = scheduled date if parseable, else null.
- Never emit an edition body without its dates in the header (blending versions is the likely cause of in_force 35%, `law_school_recipe.md`).
- **Why not diff-only:** diffs alone lose the full article text on dates between changes; why not all editions: size grows as acts x editions (section 7) and the later copies add almost no new tokens.

## 6. Step 2: deduplication, quality filters

### 6a. Dedup, in this order

1. **Exact:** sha1 of `fold(text)` per document. Duplicate ids (same act reachable by two ids, same PDF in two ZIPs) collapse to the lowest-id survivor; `dup_count` kept.
2. **Twins (x and -x):** for each pair `(x, -x)` both crawled, compute `similarity(fold(a), fold(b))` on the first 3,000 and last 3,000 folded characters (transliteration inside `fold` makes the scripts comparable). Verdict `twin` if >= 0.90; `different_acts` if < 0.60; between: `review` (report 100 of them; the Law on Local State Power is a known case where Latin and Russian ids differ in sign logic, CLAUDE.md). **Twins are both kept**: different scripts give different tokens, and translation-style augmentation helps knowledge extraction (Allen-Zhu, summarised in `law_school_recipe.md`). They are linked by `twin_id` and `family_id`, and they stay in the same train/validation/held-out side (section 9). If budget forces a cut, cut the Cyrillic copy of local decisions first.
3. **Near-duplicates between different acts (the real target):** MinHash, 5-word shingles on `fold(text)`, 14 buckets x 8 hashes (FineWeb) [full], target at least 75% similar; at Jaccard 0.7/0.75/0.8/0.85 a pair is matched with probability 56/77/92/98.8% [full]. Cluster transitively, then **verify every cluster edge with exact Jaccard >= 0.80** before accepting it (the bucket step is a candidate generator; it also links some 0.70 pairs). Keep up to **3 members per cluster** (earliest, latest, and the one nearest the cluster median) and write `dup_count` = cluster size on each survivor, so the trainer can weight by it (FineWeb-2 duplicate-count idea [full]). Reason for 3 and not 1: copies in different districts differ in names, numbers and rates, which is exactly the signal a legal model should see; reason for a cap: one model decision adopted by 200 hokimliks would otherwise be 200 near copies.
   - Run **per stratum** `(act_type, adopted year, language-script)`, not globally (FineWeb: global dedup removed up to 90% of old crawls and did not help [full]).
   - Whole-document MinHash does not see copied *clauses* inside different decisions; for local decisions add a clause-level exact hash (`fold` of each `cl:N`, 20+ words): clauses seen in more than 50 documents are marked `boilerplate_clause` and kept in 3 documents each as examples, then dropped elsewhere (the standard closing formula "kuchga kiradi" is short and stays, below 20 words).
4. **Editions are not deduplicated by MinHash.** Consecutive editions of one act sit at Jaccard far above 0.9 by design: 1-(1-0.95^8)^14 = 99.99998%, so any threshold from 0.5 to 0.85 would merge them. They are handled by the unit-interval table (section 5).
5. **Cross-language:** no dedup. Parallel links only.
6. **Corpus-wide line frequency:** lines (digits removed) appearing in more than 1,000 documents and containing a URL, "lex.uz", "e-qaror", or a date template are removed (site furniture); legal formulas in prose are never removed.

### 6b. Quality filters: signals first, then thresholds (all in `signals.parquet`; the thresholds are starting values to be tuned on the pilot [estimate])

| Signal | Rule | Applies to |
|---|---|---|
| chars after cleaning | drop < 150; flag 150-400 as `stub` (kept at tier C) | all |
| script purity | letters in the document's script >= 0.95; mixed-script words (Latin and Cyrillic letters in one word) <= 0.5% of words **after** the homoglyph repair; repair maps Cyrillic look-alikes (а е о с р х у к) inside Latin words to Latin, and the reverse in Cyrillic text | all |
| apostrophes | canonicalise: after o/g (any case) before a letter = U+02BB; elsewhere inside a word = U+02BC; all of ‘ ’ ' ` ´ become one of those. NFKC first (Saul) [full]. Measure tokens per word for U+02BB vs ASCII `'` on 500 docs before freezing (alloma reports 1.7 vs 3.5 tokens per word and suggests an apostrophe workaround [full, model card]; the bench uses U+02BB so we stay with it unless the cost is large) | uz |
| glued tokens | letter-digit glue ("bo‘limining2022") repaired as `textnorm.normalize` does, but only on the digit/letter boundary, not by transliteration | all |
| repetition | share of duplicated lines > 0.30 or top 5-gram share > 0.15 flags (Gopher-style rules; FineWeb used the original MassiveText thresholds [full]; legal text legitimately repeats, so these only flag, and only OCR/PDF tier C docs are dropped on them) | pdf, ocr |
| OCR quality | out-of-vocabulary rate against a vocabulary built from the clean HTML acts (tokens with count >= 5 in >= 3 documents): drop OCR documents above 0.12; also non-alphanumeric character share > 0.25; any `OCR failed` page; the KenLM option (Saul: normalised perplexity cut 1500 [full]) can replace this once a 5-gram model is trained on tier-A text | ocr |
| tables | `table_numeric_share` > 0.70 and table chars > 20,000: replace the table with `[jadval: N qator, M ustun]`; below that keep as pipe rows | all |
| language | document language must match the expected one from section 3e; mismatch flags `lang_mismatch` | all |
| length | cap at 400,000 characters per document before chunking (the Tax Code class), chunk by article | all |
| fertility | tokens per word with the Qwen tokenizer > 6.5 flags (garbage or glued text) | all |

Tiers: **A** = national HTML acts, editions metadata complete, every filter green. **B** = local decisions from text PDFs, filters green; amendment documents. **C** = OCR, html_fallback, stubs, any flagged document that survived. Tier decides the sampling weight, not deletion.

## 7. Personal data

What the sources look like [ours, n=27 text PDFs, biased toward normative decisions]: 1 of 27 carries a patronymic ("... oʻgʻli", an official's name in a title line), 8 of 27 mention "fuqaro/pasport/telefon" words. The share in land, housing and guardianship decisions is **unknown**: measure it on the pilot with a stratified sample of those topics, because CLAUDE.md says the crawl uses only already-redacted public documents and we have not verified that for the individual decisions that do appear on lex.uz.

Principles: Pile of Law did not redact but said the data contains PII, and listed minors, account numbers and ID numbers as the baseline every jurisdiction protects [full]. Deduplication reduces what a model memorises [snippet, Lee et al.] but does not remove a name that occurs once. FineWeb's PII step was only emails and public IPs [full]. So we mask more, and we keep structure so the text still teaches the law.

Policy by document level (`level` field):
- **Local decisions, OCR documents, any document with `topics` on guardianship, social support, housing, land allocation:** full pipeline below.
- **National acts:** run the detectors, mask phones, emails, ID numbers; **do not mask** the names of the President or officials in signature lines (public office, signed law). Report counts.

Detector order (all rules, run on the unfolded text; both scripts; no cloud model, no external NER):
1. **Patronymic-anchored names:** two or three capitalised tokens followed by `oʻgʻli|qizi|ogli|ugli` (Latin) or `ўғли|қизи|угли|кизи` (Cyrillic), plus Russian forms `-ovich|-evich|-ovna|-evna`. Mask the whole span.
2. **Trigger words:** capitalised 2-3 token spans after `fuqaro|fuqarosi|fuqarolar|YaTT|tadbirkor|shaxsiy|jismoniy shaxs|oila aʼzolari` and before `ga|ning|dan|ni`; initials patterns ("A.B. Karimov", "Karimov A.B.").
3. **Low-document-frequency capitalised pairs:** a capitalised token that appears in fewer than 30 documents corpus-wide, adjacent to another such token, and carrying a surname suffix (`-ov, -ev, -ova, -eva, -yev, -zoda, -qulov, -boyev, -xonov, -ov` etc.): personal names are rare, places and bodies are frequent. [judgment; tune on pilot against the audit below]
4. **Numbers and strings:** PINFL (14 digits), passport `[A-Z]{2}\s?\d{7}`, phone numbers (with or without +998), email, 20-digit account numbers, individual STIR near "STIR|INN|JShShIR", cadastre numbers `\d\d:\d\d:\d\d:\d\d:\d\d:\d{4}` (they identify a person's plot), car plates, dates near "tugʻilgan".
5. **Addresses of individuals:** house and flat numbers within 80 characters of a name mask; keep region, district, mahalla.
6. **Minors and guardianship** (vasiylik, homiylik, voyaga yetmagan): if the topic matches and any detector fires after masking in a second pass, the document leaves the CPT set (kept only as a template-free statistics row).
7. **Local officials in signature blocks** ("tuman hokimi", "kengash raisi", `textnorm._SIGNATURE_RE`): mask names (CLAUDE.md hard rule 2: no named-hokim shaming); keep the role. Needs Boss's yes (open decision 3).

Replacement: stable tokens **within one document** (`[FUQARO_1]`, `[FUQARO_2]`, `[MANZIL]`, `[RAQAM]`, `[KADASTR]`), so the clause still reads. No mapping from token to original is ever written to disk, no hashes of names (re-identifiable). `pii_report.parquet` stores counts per category only. Raw cache is untouched (it is already public and stays on our machine); only the masked text leaves `06_safe`.

Audit: after masking, the **local** Qwen on the box (never a cloud model) lists any remaining personal names in 300 masked pilot documents (the prompt contains only the masked text, output goes to a local file). Target [estimate]: at most 1 residual name per 100 documents in the individual-decision stratum; every miss becomes a new rule. Mask false positives are cheap (a few tokens); misses are the risk, so recall wins over precision here.

## 8. Exam-leak control

Inputs: `data/bench/mezonbench_v1.jsonl` (400 items; fields `id, family, prompt, answer, date, recent, act, path, edition`; the `lookup` answers are verbatim quotes of at least 60 characters [ours]); the `unseen(act, path)` hash rule in `research/mezonbench.py` (half the exam articles are never taught); the golden cases in CLAUDE.md.

The existing policy: "seen" articles may be taught, never with the exam question; "unseen" ones must never appear. The refinery enforces it on *every* document, not only on the 38-act store, because the same article text lives in other editions, in the Cyrillic twin, and in local decisions that quote the law.

1. **Map** each bench `act` key to its lex ids through the store's `acts.lex_id`, then through `family_id` (so twins and all editions are covered).
2. **Unit blocklist:** every `(family_id, path)` with `unseen(act, path)` true is removed from the body of every document of that family (both scripts, all editions, all tiers) before chunking. The chunk then continues without that unit; the header gets no marker (a marker would teach the model to guess the gap).
3. **n-gram net:** hash all 13-word windows of `fold(answer)` of every `unseen` bench item (and of all `prompt` texts) into a set; scan every training chunk; any chunk sharing a 13-gram with an *unseen* answer loses the overlapping sentence (or unit), and the event is logged in `leak_report.parquet` with doc id and bench id (the 13-gram rule is from the recipe's leak plan; the window is a choice, tune against the canary test below). Overlaps with *seen* answers are logged, not removed (policy).
4. **Golden cases:** Qarshi 231-4-59-Q/24 (-6986157), 207-4-59-Q/24 (-6961952), 161-4-59-Q/23, 261-4-59-Q/24 (-7026714); Yangiyo'l VI-76-4-10-146-K/24, VI-76-21-10-146-K/24 (-6832596); Xatirchi VII-3-1-5-77-K/25 (-7326620), VII-4-12-5-77-K/25 (-7395552). All get `eval_flag=golden` and go to `held_out/`: not in CPT, not in lessons, not in amendment documents. Their cancelling acts and the adliya representation text (the labels) get `eval_flag=cancelling_act` and the same treatment. Any dedup cluster that contains one of them is withheld in full (copies of the Qarshi text would leak it).
5. **Time cut (open decision 1):** the recipe proposes a holdout of acts adopted after a cutoff date that no stage sees. Mark `time_cut` for documents adopted on or after the cutoff; the bench's `recent` flag uses 2025-07-01.
6. **Canary test (part of the pilot):** inject 20 synthetic documents that contain unseen-half bench quotes (some verbatim, some with one word changed, some inside a longer local decision); the refinery must remove all of them. Fail the build if any survives.
7. Dedup survivors: if the member kept is not the one flagged, the flag is propagated to the whole cluster before the keep decision.

## 9. Size estimates [estimate unless tagged]

Known: 166,155 ids queued (the figure in the task; includes both signs and missing pages); tokens per word 4.03 for Uzbek Latin (22 docs, 16,085 words) and 4.44 for Russian (1 doc) [ours, `law_school_recipe.md`]; Uzbek Cyrillic never measured, expect a higher number. Local sample: 40 PDFs, median 1,396 words, mean 2,325 words [ours]; 149 national pages: 275,881 words total, mean 1,852 words per page, but these are mostly core laws, so the mean is biased high and the tail is long [ours]. Text is 11.9% of HTML bytes [ours]. The census (Stage 00) replaces every row below.

| Quantity | Low | Mid | High | Assumption |
|---|---|---|---|---|
| ids with usable text | 120,000 | 140,000 | 155,000 | 7% to 28% of the queue is 404, empty or duplicate [estimate, no count yet] |
| documents after exact + near-dup (cap 3 per cluster) | 100,000 | 120,000 | 145,000 | local-decision templates collapse a further 5% to 20% |
| words per document | 1,500 | 2,000 | 2,500 | from the two local samples |
| tier A+B+C base text, words | 150 M | 240 M | 360 M | product |
| base text, characters (6.5 per word incl. spaces, as in `law_school_data.py`) | 1.0 GB | 1.6 GB | 2.3 GB | |
| base text, tokens (4.03 per word) | 0.6 B | 1.0 B | 1.5 B | Cyrillic and Russian cost more; both scripts are inside this |
| of which unique content (twins counted once) | 0.35 B | 0.55 B | 0.8 B | if about half the documents are second-script twins |
| tier B amendment documents, tokens | 0.05 B | 0.15 B | 0.4 B | depends on edition counts; **unknown until the census** |
| lesson inputs (unit-version rows, container rows excluded) | 1.0 M | 2.0 M | 3.5 M | a dated law is ~10 to 30 units per KB of articles [judgment]; census gives the exact number |
| lessons text if one lesson per unit-version | +25% to +40% chars over the unit text | | | `lesson()` adds about 5 to 8 question lines of 60 to 250 characters per unit |

Read against the budget: 0.5 to 1B CPT tokens (recipe section 5). The full refinery output is about 1 to 2 times the budget before lessons. So the trainer samples by tier and `dup_count`, and one pass over tier A + a weighted share of B and lessons is realistic. AdaptLLM's best raw-to-comprehension ratio for law was 1:1 [full, `law_school_recipe.md`], so lesson tokens should be capped near the raw tokens, not at the maximum possible.

## 10. Build order, functions, and timings (8 vCPU box) [estimate]

All Python, in `research/refinery/`, one module per stage, each with `run(shard)`, `status()`, and a `--limit N` for the pilot. Python orchestrated with `multiprocessing` (8 workers), shards of about 5,000 documents, `_DONE` markers.

| # | Module and key functions | Depends on | Wall time first full run |
|---|---|---|---|
| 0 | `census.py`: `walk_cache()`, `parse_key(key) -> kind, lex_id, sign, ondate` | none | 10 to 30 min (directory walk on 120 GB) |
| 1 | `extract_html.py`: `assemble_text(page)`, `strip_widgets()`, `render_table()`, `page_meta(page)`; refactor `unit_versions(editions)` out of `build._store_editions` | 0 | 2 to 3 h with bs4+lxml (about 12 pages/s/core at the 64 KB median page, 8 cores, 150K current + several 100K edition pages); about 30 to 40 min if selectolax replaces bs4 for the text walk |
| 2 | `extract_pdf.py`: `read_zip_pdf()`, `pdftotext_ascii_tmp()`, `rejoin_lines()`, `drop_page_furniture()`, `cut_clauses()` (offsets from `split_decision` regexes, unfolded text) | 0 | 40 min to 1.5 h (0.1 to 0.3 s per PDF, 8 cores) |
| 3 | `extract_ocr.py`: `clean_md()`, `ocr_quality()` | 0, OCR runs | 5 to 10 min |
| 4 | `meta.py`: `act_type()`, `number_date()`, `status_from_notes()` (reuse `regnum`, `fetch.has_pending_banner`), `edition_labels()` | 1, 2 | 20 to 30 min |
| 5 | `normalize.py`: `nfkc()`, `fix_homoglyphs()`, `canon_apostrophes()`, `repair_glue()`; `langid.py`: `script_share()`, `uz_markers()` | 4 | 15 to 30 min |
| 6 | `twins.py`: `confirm_twin()`; `dedup.py`: `exact_groups()`, `minhash_signatures()` (datasketch or own numpy, 112 perms), `lsh_candidates()`, `verify_jaccard()`, `pick_keepers()` | 5 | exact: 5 min; MinHash 20 to 60 min (about 200 docs/s/core) |
| 7 | `filters.py`: `signals()` (all columns of 6b), `decide()` from `config.yaml` | 5, 6 | 20 to 40 min (tokenizer pass included) |
| 8 | `pii.py`: `detect()`, `mask()`, `df_table()` (corpus document frequency of capitalised tokens), `second_pass()`; `audit_qwen.py` (local model, pilot only) | 7 | regex 10 min, df table 20 min, full masking 30 min |
| 9 | `leak.py`: `build_blocklist()`, `build_ngram_set()`, `scan()`, `canary_test()` | 6 | 30 to 60 min (about 300M window hashes) |
| 10 | `export.py`: `chunk_by_article()`, `header()`, `amendment_docs()`, `lesson_inputs()` | 8, 9 | 20 to 40 min |
| 11 | adapt `research/law_school_data.py` and `law_school_mix.py` to read `lesson_inputs/` and `cpt_docs/` (the mix already reads `law_school_pilot.jsonl`) | 10 | half a day of coding, not compute |

Total compute for the first full run: about **6 to 10 hours wall** [estimate], dominated by steps 1 and 2; later runs re-do only the stages whose config changed. Coding order: 0, 1, 2 (they unlock everything), then 5, 4, 7, then 6, 9, 8, then 10, 11. Steps 9 (leak) and 8 (PII) must exist before the first training document leaves `06_safe`.

## 11. Pilot: 2,000 documents before the full 166,155

Sampling (seeded, stratified, from the census, written to `09_audit/pilot/ids.txt`):

| Stratum | N | Why |
|---|---|---|
| national acts, all types (laws and codes, PF/PQ, VMQ, ministry), Latin and Cyrillic, >= 3 editions | 600 | edition logic, twins, tables |
| of those: the 38 acts in the current store | 38 | **parity test** (below) |
| local decisions, text PDF, 2021 to 2026, hokim and Kengash, incl. 60 suspected template copies and the Qarshi pair | 700 | PDF cleanup, near-dup, PII |
| local decisions on land, housing, guardianship, social support (by title keyword) | 200 | PII worst case |
| OCR documents | 200 | OCR filters |
| Russian and English versions | 100 | language rules |
| edge cases: zero-unit pages, provisional banner, `not_yet_in_force`, tiny stubs, huge acts, tables > 20K chars | 200 | filters |

Checks a human can eyeball (each produces one HTML page in `09_audit/pilot/`, no tool needed beyond a browser):
1. **Parity (automatic, strict):** for the 38 store acts, refinery `unit_versions` equal the store's `units` (path, text, `valid_from`, `valid_to`) in 100% of rows; any difference is a bug in one of the two.
2. **Side by side, 40 random documents:** original page or PDF image on the left, cleaned text on the right; look for lost headings, leftover widget text ("Audioni tinglash"), glued words, broken tables, wrong order.
3. **Drop report:** table of drops by reason and by stratum, then 50 random dropped documents shown with the reason; the reviewer says "right" or "wrong". Target: at most 3 wrong drops in 50 [estimate].
4. **Twins:** 50 random pairs with verdict, similarity, first 300 characters of each; target 50/50 correct; the `review` band is read in full.
5. **Dup clusters:** 30 random clusters, members side by side with a word-level diff; confirm that survivors differ in real content (names, numbers) and that the cap of 3 is not hiding a unique variant.
6. **Editions:** 20 acts, with the unit-interval table, the tier-B amendment documents, and the header dates beside the lex.uz edition list; every date checked by eye against the page.
7. **PII:** 100 masked individual-decision documents, every mask printed with 40 characters of context (never the original string in the report), plus the local-Qwen residual list; count misses per category; the pilot ends when the miss rate is under target (section 7) on a fresh 100.
8. **Leak canary:** 20 injected documents all removed (section 8, 6); log of real overlaps with *seen* items listed for Boss.
9. **Numbers:** word and character histograms per stratum, tokens per word per script on 500 documents (also settles the apostrophe question and gives Uzbek Cyrillic its first measurement), and the extrapolation to all 166,155 ids replacing section 9.
10. **Determinism:** run the pilot twice; the output hashes must be identical.

Pilot cost: about 10 to 15 minutes of compute [estimate], 2 to 3 hours of human review. Gate to the full run: parity 100%, canary 100%, PII target met, no "wrong drop" pattern in item 3.

## 12. Open decisions for Boss

1. **Time cut:** which adoption date is held out entirely (for example 2026-07-01)? It decides how much of the newest law the model never sees, which is also what the briefing phase must cover with retrieval.
2. **Seen half of the exam articles in CPT:** the current policy teaches them as law (lessons without the exam question). That makes lookup scores a measure of memorised law, not of generalisation; the `unseen` half is the clean number. Keep reporting both (already so in the bench plan).
3. **Local officials' names in signature blocks:** mask (my default, matches hard rule 2) or keep.
4. **Both scripts of the same local decision:** keep both (default) or keep Latin only to save tokens.
5. **lex.uz terms for training use:** not checked anywhere in our docs; the legal text is public, but this should be a conscious decision before any model that leaves the machine is trained on it.

---

## Boss's decisions (21 Nov 2026, ~00:50 Tashkent)
1. **Editions: full + change notes.** Latest and original edition in full; one change document for every change in
   every edition. Change notes must also capture **renumbering, loss of force and moves** when lex.uz says so, e.g.
   "LSP art. 25 lost force on 19.10.2024 (O'RQ-976); the hokim's powers are now in art. 21-1". Sources: the
   inline "(... tahririda)" notes, "o'z kuchini yo'qotgan" notes, LexUZ sharhi notes, revhis panels.
2. **Personal data: mask citizens only.** Citizens' names, passport/ID, phones, addresses, cadastre and house
   numbers -> stable placeholders per document ([FUQARO_1]). Officials keep role + signature line (public office).
3. **Scripts: keep both** Latin and Cyrillic twins for local decisions, linked by twin_id; exam split covers both.
4. Defaults taken (Claude): the exam's "seen" half is taught (research/mezonbench.py unseen()); time-cut holdout =
   editions and decisions dated on or after 2026-10-01 kept out of training for a future post-cutoff exam.
5. Open: lex.uz terms of use for training (check before the full run is used for a released model).
