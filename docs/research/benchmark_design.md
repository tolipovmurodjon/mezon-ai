# How the top benchmarks are built, and the clean Mezon design that takes the best of each (21 Nov 2026)

Each well-known benchmark exists because an older one got fooled in a specific way. Mezon copies the fix, not the
topic. (Descriptions are from memory of the published papers; check exact figures before quoting them on stage.)

| Benchmark | The trick it stops | Its fix | Mezon takes it as |
|---|---|---|---|
| SWE-bench / Verified | text-matching answers | the model does the real job (a patch), graded by running tests; Verified = humans confirm each task is fair | MezonAudit-bench: the model writes the Adliya conclusion, graded by executable checks (citation validator, defect match, no false alarm); lawyers verify |
| SWE-smith | too few real tasks | inject known bugs into real code | Audit-smith: inject one known defect into a real clean decision |
| LiveCodeBench, SWE-bench-Live | training on the test (contamination) | only tasks dated after the model's cutoff | LIVE split: decisions adopted after the training cutoff, refreshed monthly |
| ARC-AGI, FrontierMath | leaked test sets | a private, never-published test set | a PRIVATE split (30 % of every family), only hashes published; scores reported on both |
| GPQA ("Google-proof") | questions you can just look up | experts write questions that skilled non-experts with web access still fail | v3 cross-source items: the answer is in no single document (draft dates + adoption date + rule) |
| BrowseComp, GAIA | answers that are hard to grade | hard to find, easy to verify: one short, unique answer | every item has one checkable answer (an article, a date, A/B, a verdict) |
| Humanity's Last Exam | saturation | expert-written, kept only if frontier models fail | we do NOT filter by frontier failure (it biases against them); we report the full set |
| MMLU-Pro | lucky guessing | 10 options instead of 4 | multi-choice items get 4-6 options; constant-answer baselines printed |
| SimpleQA | rewarding confident guessing | "not attempted" counts separately from wrong | right / wrong / noaniq + the strict score (+1 / 0 / -1.5) |
| tau-bench | lucky single runs | pass^k: the agent must succeed on all k repeats | pass^4 on Audit-bench and v3: an expert is reliable, not lucky |
| LegalBench | narrow tasks | 162 tasks by lawyers across 6 reasoning types | v3 families map to issue spotting, rule recall, rule application, interpretation, rhetorical understanding |
| HealthBench, GDPval | open answers graded by vibes | expert-written rubrics per task / real professional deliverables graded by experts | lawyer rubrics for the conclusion text (each defect, article, quote, severity), 2 lawyers, kappa |
| Stanford legal RAG audit (Magesh 2024) | trusting legal AI | count hallucinations: ungrounded, misgrounded, fabricated | the citation gate: any fabricated or out-of-force citation fails the instance |

## The Mezon suite (clean, authentic, hard)
1. MezonBench v1.1: plumbing (lookup with act, article, date given). Saturated with tools; kept as a regression test.
2. MezonBench v2.1: hard QA (no address, chains, dead citations, conflicts, Russian/Cyrillic, honest noaniq).
3. MezonBench v3: expert tier, cross-source (regulation.gov.uz draft + lex.uz decision + rule), real outcomes,
   lawyer gold.
4. MezonAudit-bench: the real job as an agent (SWE-bench style), REAL / SMITH / CLEAN / LIVE splits, citation gate,
   pass^4, lawyer-verified subset.
Every suite: frozen with hashes, a private split, oracle + constant + all-noaniq baselines, eye-audit of 10 items per
family before freezing, the same harness for every model, Wilson CIs and N on every number.

## The claim we are allowed to make
"On MezonAudit-bench REAL+SMITH (N, private split included, pass^4) and MezonBench v3, Mezon-LM 27B scored X;
the best frontier model with the same tools scored Y; citation validity 100 %." Nothing else.
