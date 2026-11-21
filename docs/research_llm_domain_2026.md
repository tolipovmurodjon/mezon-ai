# Research: domain LLM for Mezon (read 20 Nov 2026)

Method: public web search only, nothing of ours sent out. Most items were confirmed from search result text or one abstract page; full papers were NOT read. Where a claim comes only from a search snippet it is marked [snippet]. Anything not found is listed in "Not found / unverified" at the end. Numbers are the papers' own, not ours.

## 1. RLVR (GRPO and successors), reward design

- **DAPO: An Open-Source LLM Reinforcement Learning System at Scale** (ByteDance Seed et al., arXiv 2503.14476, Mar 2025, NeurIPS 2025). https://arxiv.org/abs/2503.14476
  Number: Qwen2.5-32B base reaches 50 on AIME 2024; naive GRPO gets 30; beats DeepSeek-R1-Zero-Qwen-32B (47) with 50% of the steps. Code on verl.
  Mezon: use DAPO tricks (clip-higher, dynamic sampling, token-level loss) when we run GRPO on our verifier.
- **Understanding R1-Zero-Like Training: A Critical Perspective (Dr. GRPO)** (Zichen Liu et al., Sea AI Lab/NUS/SMU, arXiv 2503.20783, Mar 2025, rev. Oct 2025). https://arxiv.org/abs/2503.20783
  Number: GRPO's length and std normalisation inflate wrong-answer length; removing them keeps accuracy; 43.3% AIME24 with a 7B base. DAPO keeps token-level normalisation, so the choice is not settled [snippet, third-party note].
  Mezon: watch length growth of wrong answers; our output is length-bounded (conclusion + quotes), so cap length in the reward.
- **LoRA Without Regret** (Thinking Machines, blog, 2025). https://thinkingmachines.ai/blog/lora/
  Number: LoRA matches full fine-tuning for RL even at rank 1; the argument is that policy gradients carry about O(1) bit per episode (their MATH example about 320k bits vs 3M params in rank-1 LoRA on Llama-3.1-8B [secondary summary]). A replication on Qwen3-0.6B (Kaitchup) found full FT pulls ahead; preliminary, not peer reviewed.
  Mezon: RL with LoRA on one 96 GB card is a legitimate plan; SFT needs higher rank.
- **Abstention reward hacking.** Binary rewards push guessing; the reverse hack (always "unclear") is blocked by ternary rewards: right = +1, abstain = small partial credit (below 1), wrong = negative.
  - Reinforced Hesitation, arXiv 2511.11500 (ternary RLVR, tuned penalty, abstain-vs-error trade-off) [snippet].
  - Ternary rewards for abstention, arXiv 2601.20126 (Granite-3.3-2B, Qwen-3-4B, MedMCQA) [snippet].
  - Behaviorally calibrated RL, Wu et al., arXiv 2512.19920 (Qwen3-4B-Instruct; proper scoring rules) [snippet].
  - Train for Truth, Keep the Skills, arXiv 2510.17733: binary reward checked against retrieved documents resists hacking better than continuous scores; 39.3% hallucination reduction on open-ended generation [snippet].
  Mezon: reward = +1 verified-correct flag with valid citation, partial credit for "unclear" only when the gold label is also unclear/review, strong negative for a cited-but-false article, zero for abstaining on a known positive. Track abstain rate every eval.
- **Position: The Hidden Costs and Measurement Gaps of RLVR** (Fang Wu ... Jure Leskovec, Yejin Choi, arXiv 2509.21882, v3 May 2026). https://arxiv.org/abs/2509.21882
  Claim: gains shrink or vanish under budget-matched baselines; RLVR can turn abstentions into confident answers; contamination inflates. Proposes budget-matched curves with variance, calibration + abstention tracking, judge-robustness test, contamination screen.
  Mezon: compare against the SFT-only model given the same compute and the same sampling budget (best-of-k).
- **GPU/sample budgets.** Nothing sourced for 7B-32B at our scale beyond: Extract-0 (arXiv 2509.22906): 7.66B model, SFT then GRPO with semantic reward, LoRA about 0.53% of weights, mean reward 0.573 vs GPT-4.1 0.457 and o3 0.464 on 1,000 held-out extraction tasks [snippet]. I did not find sourced GPU-hour counts. Treat as unverified.

## 2. Small specialised models vs frontier

- **Extract-0** (above): beats GPT-4.1 and o3 on its own held-out extraction set. Conditions: narrow task, SFT + GRPO, similarity reward. Baselines are not the newest.
- **LegalSearch-R1, "Can LLMs Time Travel? Enhancing Temporal Consistency in Legal Agentic Search through Reinforcement Learning"** (Wei Fan ... Yangqiu Song, arXiv 2605.25920, May 2026, v2 Sep 2026, EMNLP NLLP 2026). https://arxiv.org/abs/2605.25920 (abstract read)
  Number: 7B agent, 13 legal tasks, beats deep-research frameworks and specialised legal LLMs by 12.9% to 29.8%; temporal consistency better by 57.7% to 80.3%. Method: RL with local statute retrieval + web search, temporally indexed data over several amendment periods. Reward design and sample counts NOT in the abstract.
  Mezon: closest published match to our task (time-aware law + citations + RL). Read the full paper first (code on GitHub under AlexFanw).
- **Re:Form** (arXiv 2507.16331): 7B RL variants reach about 98-99% validation on Dafny, SFT models beat GPT-4o; preliminary study [snippet].
- **Scale AI blog** (labs.scale.com): RL text-to-SQL 46.9% vs 21.9% best off-the-shelf; RLVR +17-29 points across Qwen3 variants [snippet, vendor blog].
- Blogs claiming "$500 RL fine-tune beats frontier" are anecdotal; do not cite.
- Caveat from 2509.21882: many comparisons use weak/old baselines and unmatched compute.
  Mezon: win condition is a narrow task + verifier + retrieval tools + RL; compare to the newest frontier models given the SAME tools.

## 3. Legal benchmarks and methods

- **LegalBench** (Guha et al., arXiv 2308.11462): 162 tasks, 20 LLMs. https://arxiv.org/abs/2308.11462
- **LawBench** (arXiv 2309.16289): Chinese law, 20 tasks, 51 LLMs, memorisation/understanding/application levels; legal fine-tuning gave only modest gains [snippet]. https://arxiv.org/abs/2309.16289
- **LexEval** (arXiv 2409.20288): Chinese, 23 tasks, 14,150 questions. https://arxiv.org/abs/2409.20288
  Mezon: none tests Uzbek or decision auditing; we need our own benchmark. Borrow LawBench's memorise/understand/apply split to report per-level scores.
- **Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools** (Magesh, Surani, Dahl, Suzgun, Manning, Ho; JELS 2025; arXiv 2405.20362). https://arxiv.org/abs/2405.20362
  Number: Lexis+ AI and Westlaw tools hallucinate at 17% or more; Lexis+ AI 65% accurate, Westlaw AI-AR 42% accurate. Hallucination defined as incorrect info OR a false claim that a source supports a proposition. Even RAG tools fail.
  Mezon: our verifier tests exactly the second kind (quote verbatim + article exists on date); report both kinds separately.
- **Large Legal Fictions** (Dahl, Magesh, Suzgun, Ho; J. Legal Analysis 2024; arXiv 2401.01301). Stanford summary: 69% to 88% hallucination on specific legal queries for GPT-3.5, Llama 2, PaLM 2 (200,000+ queries). The "58%" figure I was asked about was NOT found. https://arxiv.org/abs/2401.01301
- **Temporal law, found by search (abstracts/snippets only, not opened except 2605.25920):**
  - Asking For An Old Friend, Prior, Schultz, Grabmair, arXiv 2605.23497 (ICAIL 2026): German statutory QA, 312 expert-validated pairs, severe degradation post-cutoff; data TUMLegalTech/temporal_bias.
  - When Do LLMs Apply the Wrong Law?, arXiv 2608.14610: Temporal Applicable-Law Determination; strong bias toward newer law.
  - LawInForce-eCFR, AACL 2026 (aclanthology 2026.aacl-long.42): law-in-force retrieval from real eCFR amendments.
  - CALRK-Bench, arXiv 2603.26332 (Korean law validity over time); LexKairos, arXiv 2608.09106; Temporal Misgrounding in Legal RAG (French tax), arXiv 2608.09393.
  Mezon: our point-in-time store is the asset; use their "wrong version" error taxonomy as a metric (cites article text from a later edition).
- Multilingual/low-resource legal: nothing specific to Uzbek found. LawThinker (arXiv 2602.12056, legal deep-research agent) surfaced but not read.

## 4. Domain adaptation of Qwen-family models

- **LoRA Learns Less and Forgets Less** (Biderman et al., arXiv 2405.09673, TMLR 2024). https://arxiv.org/abs/2405.09673
  Finding: in common low-rank settings LoRA underperforms full FT on the target domain but forgets less; full FT learns perturbations 10-100x higher rank than typical LoRA; tested on code and math, SFT and continued pretraining.
  Mezon: for fact-heavy CPT use high rank or full FT; for skill/format use LoRA.
- **CMR Scaling Law: Predicting Critical Mixture Ratios for Continual Pre-training** (arXiv 2407.17467, EMNLP 2024). Power-law fit between loss, mixture ratio and tokens, lets you predict the highest domain share that keeps general ability; general loss first rises then falls. https://arxiv.org/abs/2407.17467
- **Learning Dynamics in Continual Pre-Training** (arXiv 2505.07796): scaling law with replay ratio, LR peak and annealing. https://arxiv.org/abs/2505.07796
  Mezon: no sourced Qwen-specific replay ratio found. Run a small sweep (for example 10/30/50% general replay) and measure with CMR. Any default ratio I could state would be unverified.
- **Qwen3 Technical Report** (Qwen Team, arXiv 2505.09388, May 2025). Strong-to-weak distillation (off-policy then on-policy, teacher Qwen3-32B/235B) beats RL on small models in efficiency; a secondary summary says about 1/10 the GPU hours [unverified against Table 21]. https://arxiv.org/abs/2505.09388
  Mezon: distilling a frontier teacher's verified traces may beat RL from scratch on our budget; keep only traces that pass the verifier.
- Facts live in the database, not weights: supported indirectly by Magesh (RAG still hallucinates) and LegalSearch-R1 (RAG + RL). No single paper sourced for "weights = intuition, database = facts". Tool-use/agent-trace SFT: no sourced Qwen-specific guidance found.
- "Qwen3.8-27B": I did not verify this model or its card. Check the model card before building on it.

## 5. Karpathy and lab guidance

- **nanochat** (Karpathy, GitHub, MIT). https://github.com/karpathy/nanochat . Full pipeline in runs/speedrun.sh, about 4 h on 8xH100 (about $100) for the original tier; metric "time to GPT-2" (CORE 0.256525); leaderboard times varied by source (about 1.65-3.04 h) [snippet, exact dates unconfirmed].
  Mezon: a single script from data to eval with one headline metric is the pattern to copy.
- **2025 LLM Year in Review** (Karpathy, blog, Dec 2025; coverage via digit.in and others). RLVR became a standard training stage; "jagged intelligence"; he said he lost trust in benchmarks, since verifiable-environment benchmarks are easy to game via RLVR or synthetic data [secondary summaries; original wording not checked]. Original: karpathy.bearblog.dev (not opened).
  Mezon: a public static benchmark will be gamed, including by us; keep a private time-split holdout.
- "Software 3.0" talk: exists to my knowledge but I did not source it here; unverified.
- **Adding Error Bars to Evals** (Evan Miller, Anthropic, arXiv 2411.00640, Nov 2024). https://arxiv.org/abs/2411.00640 . Report standard error under each score; compare models with paired question-level differences; use clustered SE for related questions; do power analysis [snippet].
- Google DeepMind and Qwen-team domain fine-tuning guidance: not found beyond the Qwen3 report. Anthropic: only the error-bars paper.

## 6. Fair benchmark design

- Time split: train on decisions up to date T, test on decisions adopted after T (and law editions after T), so cancelled-later outcomes and new law versions cannot leak. Supported in spirit by the temporal-law papers above (post-cutoff and pre-amendment splits).
- Contamination: 2509.21882 uses partial-prompt probes (give half the item, see if the model completes the rest) and treats contaminated sets as memorisation probes. Frontier models may have seen lex.uz text; run the probe on them.
- Grading: exact/verifier grading for citations (article exists on date, quote verbatim), plus blinded lawyer grading of a sample for the conclusion. LLM-judge results should be stress-tested (2509.21882).
- Statistics: report N, standard error or bootstrap CI, paired differences between models, clustered SE where decisions share a body/law (Miller 2411.00640). Report recall on the positive class, not accuracy, per CLAUDE.md.
- With and without tools: report every model both ways, same retrieval tool, same token budget, same number of samples (budget-matching from 2509.21882).
- Abstention: always print abstain rate beside accuracy.

## Not found / unverified
- Sourced GPU-hour or sample-count budgets for GRPO at 7B-32B in a legal domain.
- Qwen-specific replay mix ratios; sourced guidance on tool-use trace SFT.
- Karpathy's exact words on RL/evals (only secondary summaries read); Software 3.0 talk.
- DeepMind and Anthropic domain fine-tuning guidance (only the error-bars paper found).
- The "58%" legal hallucination figure.
- Papers numbered 2608.xxxx/2609.xxxx and 2610.xxxx appeared in search results; I did not open them and cannot vouch for them.

## Top 8 actions for Mezon, cheapest first
1. Build the eval harness before training: time-split, N, paired CI, abstain rate, with and without tools, same budget for every model. (Miller 2411.00640; Wu et al. 2509.21882)
2. Run the partial-prompt contamination probe on frontier models over our test decisions. (2509.21882)
3. Add the temporal "wrong edition" error metric using point-in-time law. (2605.23497, 2608.14610, LawInForce-eCFR)
4. Read LegalSearch-R1 in full (reward, samples, retrieval design) and copy what fits. (2605.25920)
5. Design a ternary reward: verified correct +1, justified "unclear" small credit, false citation strongly negative, lazy abstain zero. (2511.11500, 2601.20126, 2510.17733)
6. Generate SFT traces from frontier teachers WITH our retrieval tool, keep only verifier-passing ones; then short on-policy distillation or GRPO. (Qwen3 report 2505.09388; Extract-0 2509.22906)
7. Use LoRA for RL and format; use higher rank (or full FT on the 96 GB card) only for any CPT on Uzbek legal text; sweep replay ratio with CMR. (Thinking Machines LoRA Without Regret; Biderman 2405.09673; CMR 2407.17467)
8. Train with DAPO-style tricks (clip-higher, dynamic sampling) and compare against SFT with matched compute and best-of-k. (DAPO 2503.14476; Dr. GRPO 2503.20783; 2509.21882)
