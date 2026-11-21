# Deeper audit: what a top professional would do (21 Nov 2026, 03:20 Tashkent)

Asked every 30 min ("a deeper version, not a bigger one"). Newest entry on top.

## 21 Nov 07:55

1. A top pro distrusts the 14/14 lookup with tools: the question names act, article and date, so it tests plumbing.
   The expert's real job is the reverse: from a sentence (or a situation), find the governing act and article.
2. Rawest material: article text without its address, from the UNSEEN half only (never in a training lesson).
3. Methods: research/mezonbench_where.py: 60 items from 14 acts (max 6 per act), a sentence that belongs to exactly
   one article; grade = right article number (on the raw answer; 16 vs 16-1 told apart) AND the act (number or
   distinctive title words). Grader validation: correct answers 60/60, wrong article 0, neighbour article 0, wrong
   act 0.
4. External proof: the store's own article addresses.

Rewritten prompt: "Measure whether the model can FIND the governing act and article for an unaddressed sentence,
closed book and with tools, before any claim about legal skill."

Acted: runners take --bench; the closed-book budget for "where" raised to 200 tokens (24 was too short); queued on
the 6000 after the tools exam (tmux wherebench): base closed book, base + tools, v1.1 + tools.

## 21 Nov 07:15

1. A top pro has the decision statistics written and tested before the numbers land (the rule needs a paired McNemar
   test; none existed).
2. Rawest material: per-item right/wrong for two models on the same CLEAN items.
3. Methods: research/bench_compare.py: exact McNemar (binomial on discordant pairs), per family and overall.
   Unit checks: (0,0) -> 1.0; (10,0) -> 0.00195; (5,5) -> 1.0.
4. External proof: a standard test, fixed before use.

Acted, and a warning learned: base vs pilot v1 gives McNemar p = 0.0000 overall (+12.4 points), flip p = 0.0002,
in_force p = 0.03, although v1 COLLAPSED (always A / always ha). Reason: base abstains on most items, so "always A"
beats "noaniq". So a significant McNemar against base proves nothing alone; Gate 1 correctly also requires no
collapse flag and > 55 % per binary family. Keep all Gate 1 conditions together.

## 21 Nov 06:45

1. A top pro pre-registers the scale-up decision before the results land (v1.1 exam and the tools exam ~07:00).
2. Rawest material: per-item predictions paired with gold, the same items across B0 / V1 / BT / VT.
3. Methods: paired McNemar test, Wilson CIs, trivial and majority baselines, the collapse flag, fixed thresholds.
4. External proof: a dated rule file written before the numbers exist.

Rewritten prompt: "Before reading tonight's results, write the decision table (scale law school / fix recipe /
invest in tools) and apply it mechanically."

Acted: docs/research/v2_decision_rule.md (Gate 1 real learning, Gate 2 training vs tools, Gate 3 no forgetting).

## 21 Nov 06:15

1. A top pro finishes validating the exam before reading tonight's v1.1 score: in_force keys were never checked.
2. Rawest material: lex.uz's own page for the edition in force on the item's date (is "N-modda" there, and is it
   marked lost force?).
3. Method: research/bench_key_check.py in_force (whole-article items). Lessons from building it: fold() drops
   punctuation ("57-modda." -> "57 modda"); a lost-force note can sit 10+ words after the heading ("...O'RQ-708-sonli
   qonuniga asosan o'z kuchini yo'qotgan"); a heading can itself contain the phrase ("...o'z kuchini yo'qotgan deb
   topish"), so "yo'qotgan deb" is not a lost-force note.
4. External proof: the official page.

Rewritten prompt: "Before the v1.1 exam result is read, verify the in_force keys against lex.uz's own edition pages
and fix or exclude every disagreement."

Acted: whole-article in_force items: agree 4, disagree 0, undecidable 2; 114 items are parts/clauses (not covered
yet: needs clause ids from the page). Both checker disagreements on the way were checker bugs, not key errors.

## 21 Nov 05:30

1. A top pro asks whether fine-tuning beats the cheap alternative at all: the base model WITH our date-aware law tools
   is the real competitor (the product always has the tools). Closed-book gains mean little if base+tools already wins.
2. Rawest material: the official edition text the tools return (law store built from lex.uz editions).
3. Methods: research/bench_tools_run.py: Qwen's own tool-calling template (tools=mezon.tools.TOOLS), calls parsed from
   Qwen3.5 XML (<function=..><parameter=..>) or JSON, run against data/store/laws.sqlite, at most 4 rounds; same
   scorer (CLEAN + ALL + baselines).
4. External proof: the exam key (official texts) and the tools-on vs closed-book gap measured on the same items.

Rewritten prompt: "Before scaling training, measure base + tools vs fine-tuned (closed book and + tools) on the same
MezonBench items; scale only the variant that beats base + tools."

Acted: runner written and tested (template renders tool calls; a real call: LSP art. 25 on 2025-03-01 -> not found,
edition 19.10.2024, correct). Law store moved to the 6000 via the L40S and R2 (laptop link dropped big uploads).
Queued in tmux toolsbench on the 6000: after V11_ALL_DONE, base + tools then v1.1 + tools, 30 items per family.

## 21 Nov 04:50

1. A top pro asks the data owner for the gold early and formally instead of scraping its shadows; and watches answer
   balance during training, not only at the exam.
2. Rawest material: adliya expertise conclusions and representations, court ruling texts, E-qaror stage logs.
3. Methods: a formal request with purpose, privacy safeguards and give-back; sample first (100 conclusions); a
   yes/no balance probe inside the trainer.
4. External proof: adliya experts comparing Mezon's draft conclusions with their own.

Rewritten prompt: "Draft the formal request to the Ministry of Justice / Adolat centre for a lex.uz export, 100
anonymised adliya conclusions, public.sud.uz administrative ruling texts and E-qaror stage logs, with purpose,
safeguards and give-back; and add a yes/no balance probe to the trainer."

Acted: draft letter in Uzbek at docs/letters/adliya_data_request_DRAFT.md (not sent; Boss and the lawyer decide).
Queued: the balance probe in train_cpt (next run, not the one running).

## 21 Nov 04:35

1. A top pro validates the answer key of the exam against the primary source, independently of the pipeline that
   built it (our store parser could be wrong in the same way for the exam and the training data).
2. Rawest material: lex.uz's own edition pages (raw HTML for the edition in force on the item's date).
3. Methods: research/bench_key_check.py: for each flip item, take the words where options A and B differ (+3 words
   of context), and measure what share of their 4-word pieces appear on the official edition page; the keyed option
   must win by >= 0.15.
4. External proof: the official page text itself, not our parser.

Rewritten prompt: "Before training against MezonBench, verify every answer key against lex.uz's own edition page
for that date, using a method that does not reuse our parser; report agree / disagree / undecidable with N and fix or
drop every disagreement."

Acted: N=120 flip items: agree 65, disagree 1 (flip-028, PF-6075 annex 2 cl. 71, 2025-01-09: page favours B 0.43 vs
0.00), undecidable 54 (difference too short or not on the page). Decided items agree 65/66 = 98.5 %. Next: inspect
flip-028 by hand; extend the check to in_force; make the undecidable ones decidable (page text per clause id).
Also found: biznesombudsman.uz builds its links in JavaScript (crawl got 6 pages) -> needs its API, queued.

## 21 Nov 04:05

1. A top pro checks the exam before trusting a score: null baselines next to every result and a human spot-check of
   20 items; keeps a source ledger before the full refinery.
2. Rawest material: the government's own registers (data.egov.uz Adliya register of ministry acts, 1,266 rows) to
   prove what lex.uz is missing.
3. Methods: null baselines (majority / always-A / random), register-vs-crawl matching, a ledger.
4. External proof: the official register itself.

Rewritten prompt: "Before trusting any score, put the null baselines next to it and have a human spot-check 20 exam
items. Build a source ledger. Prove the lex.uz crawl is complete by matching it against the official Adliya register."

Acted: null baselines computed (always-A flip 49.2 %, always-ha in_force 50.0 %, random ~50 %; trivial overall
35.0 %; pilot v1 38.5 % is only +3.5 points over it). Source ledger written: docs/research/source_ledger.md
(21 sources). Register check queued until the data.egov.uz download ends.

## 21 Nov 03:20

**1. What a top professional would do that we are not asking for**
- Let the exam pick the data: write the adliya expert's real task list (order 3333 arts. 93-95 checklist,
  conclusion format positive / fixable defects / negative), build the gold exam from it, and run error analysis
  after every exam (fetch data for the failures) instead of "download everything".
- A source ledger: licence, personal data, role (law school / internship / exam), tokens, coverage by type/year/region.
- Measure each source's value on a small proxy model (Qwen3.5-4B) before paying for 27B runs.
- Know the tokenizer cost of Uzbek (done below).

**2. The rawest material**
- Expert output in the experts' own words: adliya representations (taqdimnoma), prosecutor protests, adliya
  conclusions, court ruling texts.
- Life-cycle pairs: draft (regulation.gov.uz) -> adopted (lex.uz / E-qaror) -> cancelled (cancelling act).
- Process data: a district adliya expert reviewing 5 real drafts while thinking aloud (recorded, with consent).

**3. Methods and tools:** MinHash dedup (datatrove), a quality classifier for Uzbek legal text, 13-gram
decontamination + canary (have), tokenizer fertility (done), proxy-model ablations, RAFT, expert iteration with our
verifier, calibration of "noaniq" (ECE), Cohen's kappa between two lawyers.

**4. What shows it is right (other than us):** a time-split backtest (law + decisions up to date T; did the flagged
decisions really get cancelled after T?), blind grading by independent lawyers with kappa, frontier models on the same
exam (public law questions only), adliya experts accepting or rejecting pre-filled conclusions.

**Rewritten prompt:** "Build Mezon-LM around the real job of an adliya expert, not around 'all data'. (1) Write the
task list (order 3333 arts. 93-95 + conclusion format) and a gold exam from it, graded by 2 independent lawyers
(kappa). (2) Collect the rawest expert material first: cancellation texts, court rulings, draft->adopted->cancelled
pairs, and a think-aloud review session with a district adliya expert. (3) Keep a source ledger; measure each source's
value on a small proxy model; run error analysis after every exam. (4) Prove it with a time-split backtest against
real later cancellations, blind lawyer grading, and the same exam given to frontier models."

**Acted on: tokenizer fertility** (`research/tokenizer_fertility.py`, Qwen3.8-27B tokenizer, 400 random extracted
lex.uz texts, `data/interim/tokenizer_fertility.json`):

| Script | Paragraphs | Words | Tokens / word | Chars / token |
|---|---|---|---|---|
| Uzbek Latin | 2,668 | 517,635 | 4.019 | 1.663 |
| Uzbek Cyrillic | 1,604 | 91,322 | 3.852 | 1.943 |
| Russian | 2,033 | 66,789 | 2.295 | 3.541 |

- Uzbek costs ~1.7x the tokens of Russian per word: 300M training tokens ~ 75M Uzbek words. Our earlier estimate
  (35.3M chars -> 21.7M tokens = 1.63 chars/token) already matched this.
- The official apostrophe U+02BB costs 2 tokens ('o', 'Ê', '»'); U+2018/2019/ASCII cost 1. Folding all apostrophes to
  ASCII saves only **1.6 %** of Latin tokens (400K-char sample), so we keep the official characters (the model must
  quote verbatim). Morphology is the real cost ("hokimligi" = 5 tokens, "qaror" = 3).
- Next deeper steps queued: the source ledger; the time-split backtest design; the order-3333 task list as the exam
  spine.
