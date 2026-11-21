# How open labs post-train, and how small specialists beat frontier models (research 20 Nov 2026)

Evidence tags: **[full]** = I read that part of the paper's HTML text in this session. **[abstract]** = only the arXiv abstract page. **[snippet]** = a search-result excerpt or a secondary source, not the primary text. Where a number is missing, it is missing on purpose: I did not fill it from memory. Several papers' sections were only partly read (the fetcher truncates long pages), and I say so.

Not verified: the name "Qwen3.8-27B" from our CLAUDE.md. I found no Qwen3.8 report; the newest Qwen I saw is Qwen3.5-397B-A17B (released 16 Feb 2026), and only commentary on it, no tech report [snippet]. Check the exact model card before you cite any Qwen recipe as "ours".

---

## 1. Open-weight lab recipes

### 1.1 Qwen3 (arXiv 2505.09388) [full for post-training and pretraining sections]
- Pretraining: 36T tokens, 119 languages. Stage 1 over 30T at 4,096 context, stage 2 about 5T higher-quality (STEM, code, reasoning), stage 3 hundreds of billions of tokens at 32,768 context.
- Four-stage post-training for the flagships:
  1. Long-CoT cold start: queries filtered with Qwen2.5-72B-Instruct, responses from QwQ-32B. The report gives no sample count, and says to "minimize both the number of training samples and the training steps".
  2. Reasoning RL with GRPO on only 3,995 query-verifier pairs. Qwen3-235B-A22B AIME'24 went from 70.1 to 85.1 in 170 RL steps.
  3. Thinking-mode fusion: continued SFT on thinking data (rejection-sampled from the stage-2 model) plus non-thinking data.
  4. General RL over more than 20 task types (instruction following, format, agent, preference).
- Strong-to-weak distillation for the small models (0.6B to 14B, and 30B-A3B): off-policy distillation first, then on-policy distillation (student samples, matches teacher logits by KL). Qwen3-8B costs 17,920 GPU-hours with the RL route and 1,800 with on-policy distillation. The report says distillation needs about 1/10 of the GPU hours.
- Lesson for us: a few thousand well-verified RL queries are enough; small models should be distilled from a big sibling, not RL'd from scratch.

### 1.2 DeepSeek-R1 (arXiv 2501.12948, Nature 645:633-638) [full for the first 100K characters; the distillation section was not in the read part]
- R1-Zero: pure RL with GRPO and rule-based rewards (accuracy plus format, equal weight). AIME 2024 pass@1 rose from 15.6% to 77.9% (86.7% with self-consistency).
- The final R1 pipeline: cold-start SFT on "thousands" of long-CoT examples (no exact count given), reasoning RL with a language-consistency reward, rejection-sampling SFT, then a final RL stage with general preference rewards. GRPO settings: lr 3e-6, KL 0.001, 16 samples per question, batch 512, 10,400 steps in stage 1 and 1,700 in stage 2, with general/preference rewards in only the last 400 steps. The SFT set in Table 5 has 804,745 samples (about 800K).
- Failed attempts named: process reward models and MCTS.
- Distillation vs RL on 32B [snippet from the paper's PDF via search]: R1-Distill-Qwen-32B gets 72.6 AIME 2024 and 94.3 MATH-500. The Qwen2.5-32B base trained with large-scale RL (the "Zero" run) gets 47.0 and 91.6. QwQ-32B-Preview gets 50.0 and 90.6. The authors call distillation economical and effective, and say going beyond needs stronger bases and larger-scale RL.
- Counter-evidence: arXiv 2505.14216 (RL vs distillation, accuracy vs capability) [snippet]. I did not read it.

### 1.3 DeepSeek-V3.2 (arXiv 2512.02556) [snippet]
- DeepSeek Sparse Attention added by continued training from V3.1-Terminus. Scaled, stabilised GRPO-style RL. Agentic task synthesis: more than 1,800 environments and 85,000 complex prompts. Claimed GPT-5-level; the "Speciale" high-compute variant is claimed above GPT-5 and on par with Gemini-3.0-Pro. I did not verify the post-training compute share; one blog says more than 10% of pretraining, which is unconfirmed.

### 1.4 Kimi k1.5 (arXiv 2501.12599) [abstract]
- RL with long context and improved policy optimisation, no MCTS, no value function, no PRM. Full model: AIME 77.5, MATH-500 96.2, Codeforces 94th percentile. Long2short (long-CoT used to improve short-CoT models): AIME 60.8, MATH-500 94.6, LiveCodeBench 47.3.

### 1.5 Kimi K2 (arXiv 2507.20534) [abstract]
- 1T-parameter MoE, 32B active. MuonClip optimiser (Muon plus QK-clip), 15.5T pretraining tokens with "zero loss spike". Post-training: a large-scale agentic data synthesis pipeline plus joint RL on real and synthetic environments. Non-thinking numbers: SWE-bench Verified 65.8, Tau2-Bench 66.1, ACEBench(En) 76.5, LiveCodeBench v6 53.7, AIME 2025 49.5, GPQA-Diamond 75.1.
- Kimi K2.5 (arXiv 2602.02276) [snippet]: joint text-vision training; a text-only SFT stage reportedly activates visual and tool-use behaviour.

### 1.6 Kimi-Researcher (official blog, 20 Jun 2025, moonshotai.github.io/Kimi-Researcher) [snippet]
- Trained entirely with end-to-end agentic RL on an internal k-series model. HLE pass@1 went from 8.6% to 26.9% (pass@4 40.17%); xbench-DeepSearch 69% pass@1. This is the cleanest public example of "RL on the whole tool loop beats SFT on traces". Treat the secondary figures (23 steps, 200+ URLs per task) as unverified.

### 1.7 GLM-4.5 (arXiv 2508.06471) [abstract] and slime
- 355B MoE, 32B active, 23T training tokens; post-training with expert-model iteration (train specialists, then merge/distil into one) plus RL. TAU-Bench 70.1%, AIME 24 91.0%, SWE-bench Verified 64.2%. GLM-4.5-Air is 106B.
- slime (github.com/THUDM/slime, LMSYS blog 9 Jul 2025) [snippet]: Megatron for training plus SGLang for rollouts; agentic RL (sandbox, tool use, test-based rewards) is plugged in through custom generate/reward hooks. The README says it is the RL framework behind GLM-4.5 to GLM-5.x.
- GLM-5 (arXiv 2602.15763) [snippet]: 28.5T training tokens, context mid-training 4K to 200K, asynchronous RL that separates generation from training.

### 1.8 AI2 Tülu 3 (arXiv 2411.15124) [abstract] and Olmo 3 (arXiv 2512.13961) [abstract plus snippet]
- Tülu 3: SFT, DPO, and RLVR (Reinforcement Learning with Verifiable Rewards), on Llama 3.1 bases; open data, code, evals. Beats Llama 3.1 Instruct, Qwen 2.5, Mistral and GPT-4o-mini / Claude 3.5 Haiku per the abstract. The abstract has no data sizes or scores; I did not read the body.
- Olmo 3 (7B and 32B): whole "model flow" released. Think pipeline (SFT, DPO, RLVR with GRPO) with the Dolci data suite [snippet]. Olmo 3 Think 32B is called the strongest fully-open thinking model [abstract].

### 1.9 MiniMax-M1 (arXiv 2506.13585) [snippet]
- CISPO: clip the importance-sampling weights instead of clipping token updates, so no token is dropped from the gradient. Their controlled study on Qwen2.5-32B shows about 2x faster than DAPO. This is one controlled setup from the authors.

### 1.10 gpt-oss (arXiv 2508.10925) [snippet]
- 120b: 116.8B total, 5.1B active; 20b: 20.9B total, 3.6B active. 2.1 million H100-hours for the 120b. Claimed to pass o3-mini and approach o4-mini. Post-training CoT-RL method not read.

### 1.11 What the labs share
1. A small cold start (or none), then RL with a checker, not a learned reward, wherever one exists.
2. A big teacher, then distillation to small students (Qwen3, DeepSeek-R1-Distill, GLM expert iteration).
3. Synthetic agentic environments with executable verification (K2, V3.2, GLM).
4. Format/language/length rewards as cheap guardrails (R1).
5. A late, short general-preference stage so the specialist does not lose chat ability (R1's last 400 steps; Qwen3 stage 4).

---

## 2. Small specialist beats frontier: case studies

For each: what was equal and what was not. Most "beats GPT" claims are on the author's own benchmark.

| Case | Base | Data | Method | Compute | Result | Frontier baseline, equal tools? |
|---|---|---|---|---|---|---|
| **Extract-0** (arXiv 2509.22906, one author) [full] | DeepSeek-R1-Distill-Qwen-7B (7.66B; LoRA 40.4M params) | 281,128 synthetic examples, 1,000 held out, 280,128 for training | LoRA SFT (5 epochs) then GRPO (248 steps, 8 samples) with a field-wise similarity reward | 1x H100 80GB, $196 ($42 data, $98 SFT, $56 RL) | Mean reward 0.573 vs GPT-4.1 0.457, o3 0.464; JSON validity 89.0% (base 42.7%, SFT-only 79.9%) | Paper does not say whether baselines got the same schema/prompt; benchmark and reward are the author's own, synthetic, English only; no independent replication found |
| **Lawma** (ICLR 2025) [snippet] | Llama 3 8B (also 135M to 8B) | A few dozen to a few hundred labelled examples per task, 260 legal classification tasks | Light SFT | not read | Beats GPT-4 on most of 260 tasks, often by double-digit points; GPT-4 zero-shot average 62.0% | Classification only; no generation or citation |
| **SWE-RL** (arXiv 2502.18449) [abstract] | Llama 3 70B | not read | RL with a rule-based reward (similarity to the developer's patch) | not read | 41.0% on SWE-bench Verified | Abstract compares to nothing here |
| **DeepSWE-Preview** (Together/Agentica blog, HF card) [snippet] | Qwen3-32B | 4,500 R2E-Gym tasks | RL only, no SFT, framework rLLM | 6 days on 64 H100 | 42.2% pass@1; 59% with test-time scaling (Best@16 hybrid) | The 59% needs verifiers/test-time scaling; later papers pass it (SWE-Master-32B 61.4%, SWE-TRACE-30B 63.5%) [snippet] |
| **ether0** (arXiv 2506.17238) [snippet] | Mistral-Small-24B | 640,730 problems, 375 chemistry tasks (about 50k per task per FutureHouse) | RL, with reasoning in natural language | not read | Claims it beats frontier LLMs, human experts and chemistry models on its tasks; best comparators o3 and Opus 4 | Preprint; released weights differ from paper (post-safety); I did not read the table |
| **MedGemma** (arXiv 2507.05201) [abstract] | Gemma 3 4B and 27B | not in abstract | Medical continued training and tuning | not in abstract | vs its own base: medical multimodal QA +2.6 to +10%; chest X-ray findings +15.5 to +18.1%; agentic +10.8%; fine-tuned: 50% fewer EHR retrieval errors | Gains are against the Gemma base, not frontier. "Comparable to specialised SOTA" on pneumothorax and histopathology |
| **SteuerLLM** (arXiv 2602.11081) [snippet] | 28B | German tax materials | not read | not read | Beats similar-size general models, sometimes much larger ones, on its own SteuerEx exam benchmark | Frontier comparison not verified |
| **TaxPraBen** (arXiv 2604.08948) [snippet] | various | | tax-data fine-tuning | | Closed frontier models best overall; tax fine-tuning gave only limited gains | A counter-example; do not skip it |
| **BLT / FLawN-T5** (2311.09693, 2404.02127) [snippet] | small models | | fine-tuning | | Fine-tuned small models near-perfect on basic legal text handling (BLT); but GPT-4 still ahead of the best open model on LegalBench in FLawN-T5 (77.3 vs 60.1) | Mixed. Narrow, closed-form tasks win; broad legal reasoning does not |

Reading across the table: small models win when the task is narrow, the output is checkable, and the grader is the author's own. Nobody here shows a small model beating a frontier model on open-ended legal reasoning with citations. I found no paper showing a fine-tuned small model beating frontier models on citation-grounded legal generation. Treat that as an open gap, and as our chance, but not as a claim we can make.

---

## 3. Cross-cutting lessons

1. **Quality over quantity.** LIMO (arXiv 2502.03387) [snippet]: 817 curated samples reach 57.1% AIME and 94.8% MATH, about 1% of the data earlier SFT used. s1 (arXiv 2501.19393): about 1K curated examples; I did not confirm figures [snippet]. Qwen3 uses 3,995 RL queries [full]. Extract-0 is the opposite case: 280K synthetic, but graded by a script.
2. **Distillation vs RL for small models.** Qwen3: on-policy distillation about 1/10 the GPU-hours of RL for an 8B [full]. R1: distilled 32B (72.6 AIME) beat RL-from-base 32B (47.0) [snippet]. RL still wins where there is no teacher that knows the task (Kimi-Researcher, DeepSWE, ether0, Extract-0 all RL on a base that had little skill). For Mezon the teacher is a bigger Qwen plus a verifier, so use both: distil, then RL on top.
3. **Verifiable rewards.** Tülu 3 RLVR [abstract], R1 rule rewards [full], Extract-0 field-similarity reward [full], SWE-RL patch similarity [abstract]. A cheap deterministic grader is the engine. The Extract-0 author admits the similarity reward can miss consequential errors (a dropped middle initial) [full]. Same risk for us: a citation that exists but does not support the claim.
4. **Reward hacking and spurious reward.** I did not find a source on test-editing in coding RL (my search missed it); do not cite one from me. What I found: Qwen2.5 RLVR gains may be partly recall of contaminated benchmarks; on a clean post-release arithmetic set, random or inverse rewards did not help (arXiv 2507.10532) [snippet]; follow-up arXiv 2601.11061 [snippet]. Guard: hold-out items that postdate the base model's cutoff, check against reward-free baselines.
5. **Curriculum and length.** R1 grows max length from 32,768 to 65,536 mid-run [full]. Kimi k1.5 makes long context and policy optimisation the key [abstract]. Qwen3 stage 1 keeps cold start tiny [full]. Filter prompts by difficulty: skip those the model always or never solves (this practice is in several reports; I did not read the exact filtering numbers).
6. **Long context.** Qwen3 adds it only in the last pretraining stage (32,768) [full]; GLM-5 extends 4K to 200K in mid-training [snippet]. Our case needs long inputs (acts plus annexes), so check the base's native window before training short.
7. **Forgetting and replay.** "LoRA Learns Less and Forgets Less" (arXiv 2405.09673) [snippet]: LoRA forgets less out of domain than full fine-tuning, with a similar learn-vs-forget trade-off; target-module choice matters more than rank; LoRA is lr-sensitive. R1 and Qwen3 add general data in a late short stage [full]. I found no published replay ratio I can quote; choose one by measurement (see section 4).
8. **Eval contamination.** See point 4. Also: Extract-0's benchmark comes from its own training pipeline (held out, but same distribution) [full]. Evaluate on decisions adopted after the base model's cutoff and on lawyer-labelled flags.
9. **Equal-tools test.** Kimi-Researcher's xbench claim compares to "o3 with search tools" [snippet]; DeepSWE's 59% is with test-time scaling [snippet]. Always state whether the baseline had retrieval and a verifier, and give the same to it.

---

## 4. Recipe for Mezon (Qwen3.8-27B + a smaller sibling, 1x 96 GB + 1x 48 GB GPU)

Constraints we hold: the pipeline never sends decision text to a cloud API, so no cloud teacher on the real corpus. Teacher candidates are our own 27B (thinking mode) and its verifier-filtered output. Hardware: 96 GB for the 27B (LoRA, bf16 or 4-bit base), 48 GB for the sibling. Compute figures below are my planning estimates, not from the papers.

### Stage 0: Eval first (all horizons)
- Build the exam before training: the 3 golden cases, `data/labels` positives, lawyer-reviewed flags (at least 50, per CLAUDE.md), plus post-cutoff decisions. Report N, recall, precision, citation validity.
- Source: contamination result (2507.10532) and the equal-tools rule in section 3.9. Score the frontier models and our 27B with the same retrieval and the same citation verifier.
- 1 day: freeze 30 cancelled + 30 in-force decisions and the scorer. 2 weeks: lawyer labels grow to at least 100. 2 months: a rolling post-cutoff test set from the daily sync.

### Stage 1: Baseline with no training (1 day)
- 27B in thinking mode with the point-in-time retrieval and the citation verifier, structured output (flag, article, quote). Measure it. Many wins in section 2 came from the grader and the format, not the weights (Extract-0 base JSON validity 42.7% to 89.0%) [full].
- Source: Extract-0; Qwen3 thinking budget [abstract].

### Stage 2: Rejection-sampling SFT with a tiny cold start (2 weeks)
- Generate many audits per decision with the 27B, keep only those where the citation verifier passes and the flag matches a label or lawyer verdict. Train LoRA on the kept ones: hundreds to low thousands, not millions.
- Source: R1 cold start and rejection sampling [full]; Qwen3 minimal cold start [full]; LIMO [snippet]; Lawma (dozens to hundreds of labelled examples per task) [snippet].
- Use LoRA with attention plus MLP target modules, conservative lr, to limit forgetting [2405.09673, snippet]. Mix in general/Uzbek instruction data; pick the replay share by checking regression on an Uzbek general set.

### Stage 3: Distil into the smaller sibling (2 weeks)
- Teacher = the stage-2 27B. Student = the sibling on the 48 GB card. First off-policy on the verified traces, then on-policy distillation (student samples, KL to teacher logits) if the serving stack allows it.
- Source: Qwen3 strong-to-weak, about 1/10 the GPU-hours of RL [full]; R1 distilled 32B beat RL-from-base 32B [snippet].
- Use it for the cheap bulk passes: triage, clause splitting, retrieval query writing. The 27B does the final audit.

### Stage 4: RLVR with the law verifier (2 months; a pilot in 2 weeks)
- Reward = deterministic checks we already own: article exists, in force on the decision date, quote is a substring of the cited text, flag type matches label, output schema valid, length cap. Penalise any flag without a valid citation (matches our "no flag without a source" rule). GRPO or a CISPO-style loss; a few thousand verified prompts are enough to move a model per Qwen3 (3,995 pairs) [full].
- Source: R1 rule rewards [full], Tülu 3 RLVR [abstract], Extract-0 two-stage SFT then GRPO [full], MiniMax CISPO [snippet], slime as the rollout stack if we leave single-card training [snippet].
- Risk: reward hacking on weak graders. A citation that exists is not a citation that supports the claim. Add a second, held-out checker (entailment by a different model, then lawyer spot checks) that is never in the reward. Evaluate only on post-cutoff items (2507.10532, snippet).
- Compute guess: pilot of 200-250 steps with 8 samples per prompt (Extract-0 ran 248 steps on 1 H100 [full]); full run on the 96 GB card is a multi-day job. Context lengths for acts and annexes drive the memory, so measure first.

### Stage 5: Agentic tool-use RL on the real loop (2 months, optional)
- Tools: search law store (as-of date), open article, compare two acts, find parent act, cite. Reward at the end on the verified flag, like Kimi-Researcher (HLE 8.6% to 26.9% by end-to-end RL) [snippet] and DeepSWE (RL only, 42.2% pass@1 from Qwen3-32B, 6 days on 64 H100) [snippet].
- Be honest: DeepSWE's compute is far above ours. At our scale, start with the stage-4 single-turn version, and add tool turns only if error analysis shows retrieval misses.

### Stage 6: Final short general stage and release gates (2 months)
- A short mixed stage with Uzbek/Russian/English general data and refusal behaviour so the specialist stays usable (R1 last 400 steps, Qwen3 general RL) [full].
- Gates before any claim: recall on cancelled decisions with text, lawyer precision on at least 50 flags, 100% citation validity (enforced by the verifier, not by the model), regression on a general Uzbek set, and the timed review test. Never say "illegal"; say "possible violation, flagged for expert review".

### What fits in each time box
| Horizon | Do | Skip |
|---|---|---|
| 1 day | Stage 0 exam freeze; Stage 1 baseline with retrieval and the verifier; error taxonomy of failures | Any training |
| 2 weeks | Stage 2 rejection-sampling LoRA; Stage 3 off-policy distillation to the sibling; RL pilot (stage 4, about 250 steps) on one check type (for example check 3 or 10 with the clearest labels) | Agentic RL, large mixes |
| 2 months | Full stage-4 RLVR across checks; on-policy distillation; Stage 5 if error analysis calls for it; the lawyer-labelled set to 100 or more; the post-cutoff rolling eval | Training from scratch, anything that sends text to a cloud API |

### Open questions I could not settle from public sources
- Exact Qwen3.8 licence, window and recipe (not found).
- A published replay ratio for domain SFT: none found, so we measure it.
- Any small model beating frontier models on citation-grounded legal audits: none found; Lawma is classification, BLT is basic text handling, TaxPraBen found limited gains.
- Reward hacking in coding RL: my search returned nothing; run a dedicated search before relying on a number.

---

## Sources (arXiv/official)
- Qwen3: https://arxiv.org/abs/2505.09388 (HTML read)
- DeepSeek-R1: https://arxiv.org/abs/2501.12948 (HTML read, partly)
- DeepSeek-V3.2: https://arxiv.org/abs/2512.02556
- Kimi k1.5: https://arxiv.org/abs/2501.12599
- Kimi K2: https://arxiv.org/abs/2507.20534 ; Kimi K2.5: https://arxiv.org/abs/2602.02276
- Kimi-Researcher: https://moonshotai.github.io/Kimi-Researcher
- GLM-4.5: https://arxiv.org/abs/2508.06471 ; GLM-5: https://arxiv.org/abs/2602.15763 ; slime: https://github.com/THUDM/slime and https://www.lmsys.org/blog/2025-07-09-slime
- Tülu 3: https://arxiv.org/abs/2411.15124 ; Olmo 3: https://arxiv.org/abs/2512.13961
- MiniMax-M1: https://arxiv.org/abs/2506.13585 ; gpt-oss: https://arxiv.org/abs/2508.10925
- Extract-0: https://arxiv.org/abs/2509.22906 (HTML read)
- SWE-RL: https://arxiv.org/abs/2502.18449 ; DeepSWE: https://together.ai/blog/deepswe and https://huggingface.co/agentica-org/DeepSWE-Preview
- ether0: https://arxiv.org/abs/2506.17238 ; MedGemma: https://arxiv.org/abs/2507.05201
- Lawma: https://iclr.cc/virtual/2025/poster/30835 ; BLT: https://arxiv.org/abs/2311.09693 ; FLawN-T5: https://arxiv.org/abs/2404.02127
- SteuerLLM: https://arxiv.org/abs/2602.11081 ; TaxPraBen: https://arxiv.org/abs/2604.08948
- LIMO: https://arxiv.org/abs/2502.03387 ; s1: https://arxiv.org/abs/2501.19393
- LoRA Learns Less and Forgets Less: https://arxiv.org/abs/2405.09673
- Contamination: https://arxiv.org/abs/2507.10532 ; https://arxiv.org/abs/2601.11061
