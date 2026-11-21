# How AI reached "expert level" and how it was measured (for Mezon)

Date: 20 Nov 2026. Public sources only. Evidence grades: **[abstract]** = I fetched the arXiv abstract page (not the full paper);
**[snippet]** = search-result snippet only; **[memory]** = my own background knowledge, not re-checked today, verify before citing;
"not found" = I looked and did not find it. No full paper was read in this pass, so every number below is abstract/snippet level.

## 1. Reasoning training

| Method | What it showed | Grade |
|---|---|---|
| Lightman et al., "Let's Verify Step by Step" (arXiv 2305.20050) | Process supervision (a label per reasoning step) beats outcome supervision (label on final answer only) on MATH; process-supervised reward model solves 78% of a representative MATH test subset. Releases PRM800K = 800,000 step-level human labels. Abstract does not give the outcome-supervised number. | [abstract] |
| DeepSeek-R1 (arXiv 2501.12948) | Pure RL with verifiable rewards, no human reasoning traces, produces self-checking and strategy switching on math, code, STEM. Reasoning patterns from the big model distil into smaller ones. | [abstract] |
| Snell et al., scaling test-time compute (arXiv 2408.03314) | Verifier search or per-prompt output revision; best method depends on prompt difficulty; adaptive allocation gives >4x efficiency over best-of-N; a smaller model with test-time compute can beat a 14x larger one (FLOPs-matched, when the small model has non-trivial success). | [abstract] |
| s1 (arXiv 2501.19393) | 1,000 curated question+trace pairs (s1K) + "budget forcing" (append "Wait"); s1-32B beats o1-preview on competition math by up to 27%; AIME24 50% to 57% by scaling thinking. | [abstract] |
| LIMO (arXiv 2502.03387) | Small curated set (about 1% of prior data; exact count not on the abstract page) gives AIME24 63.3% and MATH500 95.6%. | [abstract] |
| Kimi k1.5, Qwen QwQ / Qwen3 thinking, OpenAI o-series notes, self-consistency (Wang 2022) | Not fetched. Same family: RL on verifiable rewards plus long CoT; majority vote / best-of-N with a verifier. | not found in this pass; [memory] only |

Lessons that transfer:
1. RL works where there is a **cheap, trustworthy verifier** (math answer, unit tests). Law has no such verifier, so for Mezon the verifier must be built: the citation validator (does the article exist, in force on the date, quote present) is a hard verifier; "is it really a defect" is not, it needs lawyer labels.
2. Step-level supervision beat outcome-only. For Mezon a "step" = one link in the chain: act identified, in force on date, article located, norm vs clause compared, hierarchy applied. Step labels from the lawyers are the PRM800K analogue (far smaller scale; see s1/LIMO for why 1,000 good examples can matter).
3. Test-time compute helps most with a verifier: sample N audits, drop any whose citations fail validation, keep the majority/most-supported. Cheap to add.
4. s1/LIMO are on math where the base model already knew the skill. Whether 1,000 examples unlock Uzbek legal reasoning depends on the base model's Uzbek-law knowledge. Untested; do not assume it.

## 2. Head-to-head case studies

**Medicine**
- Med-PaLM 2 (arXiv 2305.09617): 86.5% on MedQA (USMLE-style), +19% over Med-PaLM; physicians preferred its answers to physician answers on 8 of 9 axes over 1,066 consumer questions, pairwise, clustered-bootstrap CIs. [snippet] Authors say it is research, not clinical validation. Criticism [memory]: curated question set, not real patients.
- AMIE (arXiv 2401.05654): randomized double-blind crossover, OSCE-style text consultations, 149 scenarios (Canada, UK, India), 20 primary-care physicians vs AMIE, patient actors; AMIE better diagnostic accuracy, rated superior on 28/32 specialist axes and 24/26 patient-actor axes. [abstract] Stated limit: text chat is unfamiliar to clinicians, not real practice. Specialist blinding detail not on the abstract page.
- MAI-DxO (arXiv 2506.22405): 304 NEJM clinicopathological cases, sequential-diagnosis benchmark; o3 + orchestrator 80% (85.5% in max-accuracy mode) vs 20% for generalist physicians; costs 20% below physicians. [abstract] Not on the page: physician count and experience. [memory] physicians were not allowed colleagues, books or other tools, a common criticism (unrealistic baseline). Verify before citing.
- Goh et al., JAMA Netw Open 2024: 50 physicians randomized, GPT-4 + usual resources vs usual resources: 76% vs 74%, adjusted diff 2 points, 95% CI -4 to 8, not significant; GPT-4 alone scored higher than both physician groups. [snippet] Lesson: model-alone beating humans does not mean human+model beats humans. Test the workflow you will ship.

**Law**
- GPT-4 bar exam: OpenAI's report claimed about 90th percentile. Martinez (Artificial Intelligence and Law, 2024) re-evaluated: below about 69th percentile overall and about 48th on essays on a July administration; the original pool was skewed to repeat takers; preprint gives about 62nd vs first-time takers and about 48th vs those who passed (essays about 15th). [snippet; the figure is 69th, not 68th] The choice of comparison population moved the claim by 20+ points. Also, the MBE/UBE is not lawyering.
- LegalBench (arXiv 2308.11462): 162 tasks, six types of legal reasoning, 40 authors, built with legal professionals. [abstract] Mostly US-law, classification-style tasks; says nothing on auditing.
- LawGeex 2018: 20 US-trained lawyers vs the vendor's AI, five Enron NDAs, 30 provisions; AI about 94% vs lawyer average 85%; best lawyer matched 94%, worst 67%; AI 26 seconds vs 51-156 minutes per lawyer. [snippet] Vendor-commissioned, five documents, one narrow task; a detailed independent methodology critique was not found. Treat as a marketing study.
- Vals Legal AI Report, Feb 2025: four tools (Harvey, CoCounsel, Vincent, Oliver) vs a lawyer-baseline group across seven tasks. Data extraction: baseline 71.1, Harvey 75.1, CoCounsel 73.2, Vincent 69.2, Oliver 64.0. Document Q&A: Harvey 94.8 vs baseline 70.1. Lawyers still led on redlining (79.7) and EDGAR research. [snippet] Vendors chose which tasks to enter; Lexis+ AI withdrew; Vals notes the methodology is controversial. Oct 2025 follow-up on legal research: all AI products, including ChatGPT, beat the lawyer baseline, within four points of each other. [snippet]
- Schwarcz et al., "AI-Powered Lawyering" (J. Law & Empirical Analysis 2026): randomized, 137 law students (Minnesota, Michigan), six tasks, Vincent AI vs o1-preview vs no AI; speed gains about 34-140% in five of six tasks (working-paper and published ranges differ; check the final text); o1-preview improved analytical depth; hallucinated citations: Vincent 3 total, o1-preview 11 total. [snippet] Students, not practising lawyers; right kind of design.
- Harvey BigLaw Bench: per-task expert-written rubrics scoring completeness/accuracy; Harvey admits it emphasizes tasks models can do; Arena (Nov 2025) uses lawyer pairwise preference converted to Elo. JudgmentBench (arXiv 2605.25240, May 2026, Stanford/Snorkel/Harvey): 30 tasks, 1,539 rubric scores and 1,530 pairwise judgments from practising attorneys; pairwise beat rubrics and took under half the annotation time; rubrics miss tacit holistic features. [snippet, preprint, not peer reviewed] Vendor-involved.
- Legal judgment prediction: not researched in this pass (not found). [memory] Predicting outcomes from text often leaks the outcome through the facts section; do not rely on it.

**Math and code**
- IMO 2025: Gemini Deep Think 35/42 (5 of 6 problems), graded and certified by IMO coordinators with student criteria; OpenAI also 35/42 but graded by three former IMO medalists by consensus, not officially; OpenAI's claim was disputed over process. [snippet] Best example of credible measurement: outside body, same rubric as humans. Math has an unambiguous proof standard; law does not.
- Competitive programming (Codeforces, IOI, AlphaCode): not fetched; [memory] only. Code has automatic tests as verifier; Mezon has no equivalent.

## 3. Pitfalls and what reviewers accepted

- **Comparison population** (Martinez): who the "humans" are can swing the claim by 20 points. State the baseline: who, how experienced, which tools, how much time.
- **Vendor-run, vendor-chosen tasks** (LawGeex, VLAIR): discounted. IMO was credible because the grader was independent.
- **Unrealistic human conditions** (MAI-DxO no-tools physicians [memory], AMIE text chat): give humans the tools they normally use.
- **Model alone vs model + human** (Goh): the deliverable is the workflow. Mezon's is "reviewer with Mezon vs reviewer without".
- **Contamination**: [memory] bar-exam, MedQA, olympiad items sit in public web data. Mezon's own risk: lex.uz cancelled decisions and the cancelling acts are public, so a model trained on lex.uz may have seen the answer. Hold out by date (adopted and cancelled after the training cut-off) and keep a private set.
- **Citation hallucination** (Stanford, arXiv 2405.20362): Lexis+ AI and Thomson Reuters tools hallucinated between 17% and 33% of the time; commercial RAG tools hallucinate less than general chatbots but far from zero. [abstract; query count and GPT-4 rate not on the fetched page] "No flag without a valid source" plus a deterministic validator is the right design; report the validator's drop rate too.
- **Automation bias**: Goh found under-use, not over-use. Over-trust studies in law: not found. Measure directly with seeded wrong flags.
- **Rubric vs preference**: rubrics are repeatable but miss tacit quality (JudgmentBench [snippet]); use both.

## 4. Legal reasoning specifically

- IRAC prompting (Kang et al., arXiv 2310.14880): ChatGPT asked for full IRAC analysis, graded by law students on law-school rubrics; paper reports incomplete or incorrect reasoning paths and F1 about 0.49 without expert IRAC analysis. [snippet]
- SemEval-2024 Task 5 entry: IRAC prompting F1 0.60 vs chain-of-thought 0.53 vs direct 0.49. [snippet, one team's table]
- MSLR (arXiv 2511.07979): about 1,400 official Chinese insider-trading decisions with IRAC-annotated reasoning traces, 60K step-level labels; o1-mini 72% IRAC recall; model-generated CoT helped more than human-designed prompts. [snippet] Closest published analogue to what Mezon wants: step-level legal labels from real decisions.
- Statutory interpretation / hierarchy-of-norms papers: no dedicated paper found (only a category inside LegalBench). Mezon's hierarchy rule (higher force wins, later wins, doubt favours the person; NLA arts. 6, 18) would be original and must be self-evaluated.
- Judge-like explanation quality: no validated metric found. Use lawyer pairwise preference (JudgmentBench direction) and check every stated reason traces to a quote.
- No Uzbek-language legal benchmark found. We must build it.

## For Mezon: staged path and evidence standard

Today: rule-trained adapter. Never skip a rung, and never say "illegal"; say "possible violation, flagged for expert review" (CLAUDE.md hard rule 1).

| Stage | Build | Claim allowed | What we must show, against whom | Sources |
|---|---|---|---|---|
| 0. Plumbing | Citation validator + deterministic rules (checks 1-3, 7-11); pin the eval harness; seal a date-split hold-out set now | "Every flag cites a real, in-force article" | 100% citation validity, enforced and logged; report drop rate | Stanford 2405.20362 |
| 1. Learns the lawyer's steps | Lawyer-written step traces (IRAC-style: act, in force?, article, clause vs norm, hierarchy, conclusion) for about 300-1,000 decisions; SFT then step-level labels | "Follows an auditor's reasoning steps" | Step-level agreement with lawyer traces; 2 lawyers, report Cohen's kappa between them; N of traces | Lightman 2305.20050; s1; LIMO; MSLR; Kang |
| 2. Verifier + test-time compute | N samples, validator filter, majority/most-supported, abstain "unclear needs expert" | "Fewer false alarms without losing recall" | Precision on >=50 lawyer-reviewed flags per check (already our target); recall on declared-invalid positives that have text; report N for both | Snell 2408.03314; DeepSeek-R1 |
| 3. Beats baselines, not lawyers | Compare vs plain base model, rules only, keyword RAG | "Better than a general chatbot on Uzbek local decisions" | Same held-out decisions adopted after training cut-off; the cancelling text is the independent exam; recall with Wilson CI, not accuracy | Martinez (define baseline); contamination note |
| 4. Reviewer + Mezon vs reviewer alone | Randomized crossover: each reviewer audits different decisions with and without Mezon | "Reviewers are faster and/or catch more with Mezon" | At least 5 district adliya or hokimlik lawyers (the planned 5 timed reviews are a pilot, not proof), seeded set with known-cancelled and clean decisions, minutes and defects found, blinded grader scoring against the cancelling act, CIs. Include wrong-flag seeds to measure automation bias | AMIE (randomized crossover); Schwarcz (RCT); Goh |
| 5. Mezon alone vs lawyers | Same decisions to lawyers working normally (own tools, normal time) and to Mezon | Only now: "matches or exceeds lawyers on defect-spotting for this task" | Lawyers of stated seniority, tools and time allowed; at least 100 decisions with prevalence reported (bad class is rare; 90% of cancellations are individual decisions); independent blinded panel (Adliya experts, not our two lawyers) grading anonymized outputs; pre-registered metric (recall at fixed precision, plus pairwise preference); CIs. Say "on this task", never "better than a lawyer" in general | IMO 2025 official grading; JudgmentBench; Vals baseline design; LawGeex as cautionary example |
| 6. Prospective | Flag live decisions, wait for official outcomes | "Flags later confirmed by adliya/court at X%" | Time-stamped flags before the outcome, public log; N confirmed vs not | Certified-after-the-exam logic of IMO 2025 |

The N thresholds above (>=50, >=100, >=5) are my proposals, not values from a source, except the >=50 reviewed flags which is already in CLAUDE.md.

Rules for any public claim: state N, the baseline's seniority and tools, who graded and whether blinded, held-out date, and failures. A mixed result (AI ahead on speed and recall, lawyers ahead on judgment calls, as with redlining in VLAIR) is more credible to Adliya than a clean win. The CLAUDE.md rule "write eval/report.md only from numbers a script printed" is already the right standard.

## Gaps (not found or not done)
Full papers not read; Kimi k1.5, Qwen3, o-series notes, self-consistency, competitive-programming results, legal judgment prediction, LawGeex methodology critique, automation-bias studies in law, a statutory-interpretation LLM paper, and any Uzbek legal benchmark were not found or not fetched.
