# Critique of the night's approach, and the clean redo (21 Nov 2026, 08:05 Tashkent)

Boss's goal: prove each stage small first (law school, internship, real cases, strict judge, real-time sync), each one
beating the base model, and then show Mezon-LM beats the top models when it has enough information, tools, internship
and RL. This file is the honest critique of how far tonight's work proves that, and the redo that would.

## What was wrong (Karpathy-style: become one with the data, baselines first, one change at a time)

1. **No frontier baseline at all.** Every comparison was against our own base Qwen. "Beats top models" has zero
   evidence until Opus / GPT / Gemini sit the same frozen exam, closed book AND with the same tools.
2. **The exam kept changing under the models.** Tonight we fixed the exam 5 times (invalid flip pairs, grader, act-name
   tool bug, biased 30-item sample, no forced final answer). Each fix was right, but numbers from before and after are
   not comparable. Fix: MezonBench v1.1 is now FROZEN (data/bench/FROZEN_v1_1.json: item hashes, grader/tool/store
   hashes). Any change = v1.2 and every model re-runs.
3. **Baselines came late.** The trivial line (35 %) and the majority baselines were computed after the first claim.
   Now they print with every score.
4. **The law school targeted the wrong skill.** Closed-book recall of 20K edition dates is memorisation; one 7M-token
   pass cannot do it (v1.1: 54-57 % on taught articles, 41-43 % on untaught). It did learn text (law loss
   0.887 -> 0.273) and hierarchy (90 %) and forgot nothing.
5. **Lookup and flip WITH tools test plumbing**, not legal skill: the question names act, article and date. 29/30 there
   says "the tool loop works", not "Mezon is a lawyer".
6. **The real job was never measured:** finding the governing norm for a decision clause, spotting the defect, writing
   the adliya conclusion. The golden cases (Qarshi, Yangiyo'l, Xatirchi) run through the rule engine, not the model.
7. **Real-time sync** (the model knowing laws changed in the last weeks) has no eval yet.
8. **We looked at outputs by eye too rarely**: the act-name bug and the empty hierarchy answers were found only because
   one partial file was opened. Every run now gets 10 raw outputs read before any number is trusted.

## The clean redo: one stage = one change, measured on the frozen exam

| Stage | Change vs previous | Eval (frozen) | Passes if |
|---|---|---|---|
| 0. Baselines | none | v1.1 (396) + where (60) + real-case set; base closed / base + tools; **frontier closed / frontier + same tools** | (reference only) |
| 1. Law school | CPT on law text | closed book: hierarchy, terms, where; NOT date recall | gate rule (v2_decision_rule.md) |
| 2. Internship | tool-use SFT (traces) | tools on: all families + where + OOD phrasing set | +10 points over base + tools, no collapse, citation validity 100 % |
| 3. Strict judge | expert iteration with the 3-level reward | same as 2 + calibration: wrong-confident rate, warranted-noaniq rate | wrong-confident -30 %, right not lower |
| 4. Real cases | the audit task | 11 real cancelled decisions + 150 clean controls (counts, not rates) + the lawyers' 40-question gold exam | flags consistent with the cancellation, false alarms counted |
| 5. Real-time sync | the daily-synced store vs a store frozen 30 days ago | "recent" items (laws changed in the last 30 days) with tools | synced store answers them, frozen one abstains |
| 6. Scale | the winners only, full corpus (refinery) | the whole table again | each stage still beats the one before |

**"Beats top models" is claimed only as:** "On MezonBench v1.1 (frozen, N, CI), Mezon-LM + Mezon tools scored X vs
<frontier model> closed book Y and <frontier model> + the same tools Z." The honest expectation: frontier models without
our tools will fail date-aware Uzbek law (they cannot know editions); frontier models WITH our tools may come close,
because the moat is the data + date-aware tools + verifier, and the small model makes it cheap, local and private. Both
results are worth showing.

## What needs Boss

- **Frontier baseline:** running Opus / GPT / Gemini means sending the exam's public law questions (lex.uz text, no
  decision text, no personal data) to their APIs, with Boss's API keys and Boss's yes. Until then no "beats top models".
- **Lawyers' gold exam (40 questions) and the 60-flag review:** the external judge of stage 4.

## Audit 21 Nov 08:20: the tools exam is saturated (measured)

- Base Qwen + tools, balanced 30/family + forced final answer (partial file, 105 of 120): CLEAN 102/103 right,
  0 wrong, 1 abstain; hierarchy 15/15 (the loop is fixed by the forced final turn). The four families cannot show any
  training gain any more: they give act, article and date, so they test plumbing.
- search_law on the 60 "where" sentences: recall@5 60/60 with the full sentence, 60/60 with 5 random content words,
  52/60 with 3 words. Only because the store holds 38 acts. The real test of search (and of the model) starts when the
  store holds all 166K acts from the refinery: rerun this recall check there first (FTS5 alone, then + bge-m3).
- Consequence: MezonBench v2 must ask what people ask (no act/article given), chain clause -> norm -> in force on date,
  use Russian/Cyrillic phrasings, and run against the full store. Internship data should target what v2 shows is weak.

## Trust table 21 Nov 09:35 (research/bench_trust.py, same 118 CLEAN items, strict = (right - 1.5 wrong) / N)
| model | right | wrong | noaniq | acc | selective | strict |
|---|---|---|---|---|---|---|
| Qwen 27B closed | 44 | 18 | 56 | 0.373 | 0.710 | 0.144 |
| law school v1.1 closed | 58 | 37 | 23 | 0.492 | 0.611 | 0.021 |
| Opus 5.5 closed | 56 | 8 | 54 | 0.475 | 0.875 | 0.373 |
| Qwen 27B + tools | 116 | 1 | 1 | 0.983 | 0.991 | 0.970 |
| Opus 5.5 + tools | 115 | 1 | 2 | 0.975 | 0.991 | 0.962 |
Law school v1.1 already beats Opus on raw accuracy closed book (0.492 vs 0.475) but guesses: 37 confident errors vs 8,
so its strict score is 0.021 vs 0.373. The strict judge's job is exactly this: keep ~58 right, cut wrong to <= 8.
Headline metric from now on: the strict score, with right / wrong / noaniq beside it.
