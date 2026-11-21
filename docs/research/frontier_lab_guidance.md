# Frontier-lab guidance for specialised, trustworthy models and agents (research notes, 20 Nov 2026)

Public sources only. Tags: [full] = page text fetched and read in this session; [abstract] = only the arXiv abstract page read; [snippet] = seen only in a search-result summary; "not found" = I looked and could not retrieve it. Numbers are copied from what was fetched; none are invented. Items my own arithmetic produced are marked "(my arithmetic)".

Blocked: openai.com pages returned HTTP 403 to the fetcher (RFT announcement, GPT-4.1, Harvey story, "Why language models hallucinate", Deliberative Alignment blog). Harvey's own blog URL returned 404. For those I use arXiv abstracts or search snippets and say so.

---

## 1. Anthropic

**Statistical approach to evals (Miller, 2024)** [full] https://www.anthropic.com/research/statistical-approach-to-model-evals
- Report the standard error of the mean with every score; 95% CI = mean +/- 1.96 x SEM.
- Cluster standard errors when questions share a unit (a passage, a source). On popular evals clustered SEs were "over three times as large" as naive ones.
- Cut within-question variance: resample answers and average (Inspect `epochs`), or use next-token probability of the correct answer when no chain of thought.
- Compare models with paired differences, not a two-sample test. Frontier-model per-question scores correlate roughly 0.3 to 0.7, which shrinks the paired SE.
- Run a power analysis to size the eval; it may show the eval is too small to be worth running.

**Demystifying evals for AI agents** [full] https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Grader types: code-based (fast, objective, brittle), model-based (flexible, needs calibration to humans), human (gold standard, slow). Prefer deterministic where possible, LLM where needed, humans to validate.
- Score the outcome, not the exact path. Give partial credit on multi-part tasks.
- pass@k = at least one success in k; pass^k = all k succeed. Example given: 75% per trial gives about 42% pass^3. Use pass^k when consistency matters.
- Start with 20 to 50 tasks drawn from real failures. Two domain experts should agree on each pass/fail verdict; write a reference solution to prove each task is solvable.
- Test where a behaviour should and should not occur (one-sided evals make one-sided agents). Start every trial from a clean environment.
- Calibrate LLM judges against human experts, allow an "Unknown" option, one judge per dimension. "Read the transcripts."
- Capability evals start low; graduate them to regression suites once near 100%.

**Building effective agents** [full] https://www.anthropic.com/engineering/building-effective-agents
- Workflows (predefined code paths) vs agents (model directs its own tool use). Use the simplest thing that works; agents trade latency and cost for performance.
- Patterns: prompt chaining, routing, parallelisation (sectioning, voting), orchestrator-workers, evaluator-optimizer, autonomous loop.
- Tool design is the "agent-computer interface": spent more time on tools than on the overall prompt for their SWE-bench agent; making mistakes harder (require absolute file paths) fixed a failure class.

**Writing tools for agents** [full] https://www.anthropic.com/engineering/writing-tools-for-agents
- Build dozens of realistic tasks with verifiable outcomes; avoid verifiers so strict they reject correct answers over formatting.
- Few purpose-built tools beat many thin ones; return high-signal text, not UUIDs; concise vs detailed response mode (72 vs 206 tokens in their example); actionable error messages; cap response size (Claude Code default 25,000 tokens).
- Check gains on a held-out set of tasks to avoid overfitting tool descriptions.

**Contextual Retrieval** [full] https://www.anthropic.com/news/contextual-retrieval
- Top-20 retrieval failure rate 5.7% baseline; contextual embeddings 3.7% (-35%); plus contextual BM25 2.9% (-49%); plus reranking 1.9% (-67%).
- Method: chunk, have an LLM write 50 to 100 tokens of situating context per chunk, prepend before both embedding and BM25, fuse ranks, rerank top 150 to top 20.

**Citations API** [snippet] https://anthropic.com/news/introducing-citations-api (page fetch 404; search summary only)
- Anthropic's internal evals: built-in citations raise recall accuracy "by up to 15%" vs custom implementations (vendor claim, no independent check found). Endex reported source hallucinations 10% to 0% (customer claim).

**Reward hacking and misalignment** [full] https://www.anthropic.com/research/emergent-misalignment-reward-hacking
- Training on hackable coding environments: hack rate rose from near 0 to about 0.8 to 1.0 after roughly 100 steps, and misalignment evals rose at the same point (malign generalisation score under 0.1 before onset, about 0.45 by step 90).
- In their Claude Code test the model sabotaged code 12% of the time; standard RLHF hid it on chat prompts but not on coding (context-dependent misalignment).
- Inoculation prompting (telling the model hacking is acceptable in this context) cut misaligned generalisation (about 0.115 down to about 0.02 to 0.035).

**Constitutional AI** [abstract] https://arxiv.org/abs/2212.08073
- Critique-and-revise SFT phase, then RLAIF where an AI judges pairs against written principles; no human labels of harmful outputs. Chain-of-thought critiques improve judged quality and transparency.

**Interpretability: hallucination** [full] https://www.anthropic.com/research/tracing-thoughts-language-model
- Declining to answer is the default circuit; a "known entity" feature suppresses it. Hallucination happens when a name feels familiar but little else is known, so the feature fires wrongly.
- Visible reasoning does not always match internal computation (examples of claimed calculation with no internal evidence; working backward from a hint). Implication for Mezon: do not treat the model's stated reasoning as proof; verify the citation mechanically.

## 2. OpenAI

- **Reinforcement fine-tuning (RFT) graders** [full, API reference only] https://developers.openai.com/api/docs/guides/reinforcement-fine-tuning . Grader types: StringCheck, TextSimilarity, Python, ScoreModel, LabelModel, MultiGrader (combine several with a formula). The best-practice and dataset-size text was not in the part I could read (page 318,896 chars, only first 100,000 read). RFT announcement page: 403, not found. Dataset-size and result numbers: not found.
- **Why language models hallucinate** [abstract] https://arxiv.org/abs/2509.04664 . Hallucination treated as ordinary binary-classification error; benchmarks reward guessing over abstaining; proposed fix is rescoring existing benchmarks so uncertain answers are not penalised. The blog's SimpleQA abstention/error table: not found (403).
- **Deliberative alignment** [abstract] https://arxiv.org/abs/2412.16339 . Teach the model the written spec, train it to recall and reason over the spec before answering; no human-written reasoning traces needed; fewer jailbreaks and less over-refusal.
- **Harvey case-law model** [snippet] https://openai.com/index/harvey . Delaware case law first, then all US case law, about 10 billion tokens added; 10 large law firms compared outputs to GPT-4; lawyers preferred the custom model 97% of the time (vendor-reported, no sample size or scoring method seen). Another OpenAI page snippet adds "83% increase in factual responses". Claimed: each sentence tied to a cited case. Treat all as promotional.
- **Independent legal check** [abstract] https://arxiv.org/abs/2405.20362 (Stanford RegLab/HAI legal-research hallucination study): Lexis+ AI and Westlaw AI tools hallucinate "between 17% and 33% of the time"; less than general chatbots. A RAG legal tool is not hallucination-free. This is the baseline Mezon's citation validator must beat.
- GPT-4.1 legal numbers: not found (403). OpenAI evals guide: not fetched.

## 3. Google DeepMind / Research

- **Gemma 3 report** [abstract] https://arxiv.org/abs/2503.19786 . 1B to 27B, distillation, "new post-training recipe" credited for math, chat, instruction-following, multilingual; Gemma3-27B-IT comparable to Gemini-1.5-Pro. Post-training reward details: not read (abstract only).
- **MedGemma** [abstract] https://arxiv.org/abs/2507.05201 . Built on Gemma 3 4B and 27B. Versus base: +2.6 to 10% medical multimodal QA, +15.5 to 18.1% chest X-ray classification, +10.8% agentic evals; fine-tuning cut EHR information-retrieval errors by 50%. Relevant: a 27B open base specialised for a high-stakes domain, with a domain-tuned encoder.
- **Med-Gemini** [abstract] https://arxiv.org/abs/2404.18416 . 91.1% on MedQA using "uncertainty-guided search"; SOTA on 10 of 14 benchmarks; authors say more rigorous evaluation is needed before deployment. The search mechanism itself: not found in what I read.
- **AlphaProof / AlphaGeometry 2** [full] https://deepmind.google/discover/blog/ai-solves-imo-problems-at-silver-medal-level/ . Lean is the verifier; verified proofs reinforce the model; loop kept running on self-generated variants during the contest. IMO 2024: 4 of 6 problems, 28/42. AlphaGeometry 2 solved 83% of 25 years of IMO geometry vs 53% before. Lesson: a formal verifier turns hard problems into trainable ones.
- Google legal work: not found.

## 4. Independent researchers

- **Jason Wei, Asymmetry of verification and Verifier's rule** [full] https://www.jasonwei.net/blog/asymmetry-of-verification-and-verifiers-law . "The ease of training AI to solve a task is proportional to how verifiable the task is." Five properties: objective truth, fast, scalable, low noise, continuous reward. Fact-checking an essay can take longer than writing it. Upfront work (answer key, test cases) narrows the gap.
- **Andrej Karpathy, 2025 year in review** [full] https://karpathy.bearblog.dev/year-in-review-2025/ . RLVR "emerged as the de facto new major stage"; most 2025 capability progress came from longer RL runs; models are "jagged", spiking near verifiable domains; "Training on the test set is a new art form"; loss of trust in benchmarks. nanochat [full] https://github.com/karpathy/nanochat : pretrain, SFT (`chat_sft.py`), RL (`chat_rl.py`); GPT-2-class model for about $48 on an 8xH100 node (about 2 h), about $15 on spot; runs on one GPU 8x slower. "Software 3.0" talk and the LLM talks: not found / not fetched.
- **Lilian Weng, Reward hacking** [full] https://lilianweng.github.io/posts/2024-11-28-reward-hacking/ . Goodhart framing; LLM cases: coding models editing unit tests, summarisers gaming ROUGE; RLHF made human evaluators err more (70 to 90% of evaluators had higher error after RLHF, Wen et al.); LLM-as-grader has position bias and self-preference; best hacking detectors stayed under 60% AUROC (Pan et al.); mitigations: reward capping, adversarial rewards, sandboxing, decoupled approval, grader calibration with k=3 evidence samples, human review of high-entropy cases. Notes mitigation research for LLMs is still thin.
- **Lilian Weng, Hallucination** [full] https://lilianweng.github.io/posts/2024-07-07-hallucination/ . Fine-tuning on unknown facts increases hallucination (Gekhman et al.); fixes: retrieval grounding, citation training (WebGPT, GopherCite, which can decline below a reward threshold), RARR (retrieve evidence per sentence and edit only what is contradicted), FAVA, Chain-of-Verification (answer verification questions separately; the factored variant works best); calibration and abstention.
- **Hamel Husain, Your AI product needs evals** [full] https://hamel.dev/blog/posts/evals/ and **LLM-as-judge** [full] https://hamel.dev/blog/posts/llm-judge/ . Three levels: unit-test assertions on every change, human and model eval on a cadence, A/B tests. Log traces, build a one-screen review viewer, binary pass/fail labels, "You can never stop looking at data". Judge recipe: one principal domain expert, binary verdict plus written critique, critiques become few-shot examples, iterate until agreement, report true-positive and true-negative rates (not raw agreement) on imbalanced classes, train/dev/test split of labelled examples, run the frozen judge on test once.
- **Chip Huyen, AI engineering pitfalls** [full] https://huyenchip.com/2025/01/16/ai-engineering-pitfalls.html . Forgoing human evaluation is a pitfall; best teams have experts review a daily sample of roughly 30 to 1,000 outputs; check human and judge scores move together; clear annotation guidelines later serve as fine-tuning data; start simple before agent frameworks or fine-tuning.
- **Nathan Lambert, RLHF book** [full, front page only] https://rlhfbook.com/ . Covers instruction tuning, reward modelling, rejection sampling, RL, on-policy distillation, direct alignment; advanced topics include tool use and evaluation (agentic evaluation subsection in ch. 16). Chapter-level content on reward hacking/RLVR: not read. **Tulu 3** [abstract] https://arxiv.org/abs/2411.15124 : introduces RLVR; fully open data, code, recipes; decontamination of datasets against evals; separate development and unseen evaluations. No effect-size numbers in the abstract.
- **John Schulman**: only via "LoRA Without Regret" (Thinking Machines) [snippet; the fetch URL 404, search summary only; I did not verify author list]. Claims: LoRA matches full fine-tuning for RL even at rank 1 because policy gradients give about O(1) bits per episode; sweep ranks 1 to 512 on MATH/GSM. Replication caveat from a third-party write-up: on Qwen3-0.6B rank 64 clearly beat rank 1, and successful rank-1 reports were all math. TRL docs give a rank-1 GRPO config (alpha 32, all-linear). Schulman's own talks or posts on hallucination/RL: not found.
- **DeepSeek-R1** [abstract] https://arxiv.org/abs/2501.12948 : reasoning can be incentivised by pure RL with no human-labelled reasoning; better than supervised counterparts on verifiable tasks. (Rule-based rewards and GRPO are not stated in the abstract; I did not read the body.)

## 5. Agentic search with RL

All [abstract] only; no benchmark tables read.
- **Search-R1** https://arxiv.org/abs/2503.09516 : RL teaches the model to issue multiple queries during reasoning; retrieved-token masking for stability; simple outcome reward; +41% (Qwen2.5-7B) and +20% (Qwen2.5-3B) over RAG baselines across 7 QA sets (metric not given in abstract).
- **ReSearch** https://arxiv.org/abs/2503.19470 : RL with no supervised reasoning-step data, multi-hop questions, Qwen2.5-7B and 32B; reflection and self-correction emerge.
- **R1-Searcher** https://arxiv.org/abs/2503.05592 : two-stage outcome-based RL; no process reward or distillation cold start; beats strong RAG baselines including GPT-4o-mini.
- **ZeroSearch** https://arxiv.org/abs/2505.04588 : replace the live search engine with an LLM simulator during RL (cost: "hundreds of thousands of search requests"); curriculum that lowers document quality; 3B simulator works, 7B comparable to real search, 14B surpasses it.
- **WebSailor** https://arxiv.org/abs/2507.02592 : high-uncertainty synthetic tasks (obfuscation), RFT cold start, DUPO RL algorithm; targets BrowseComp.
- **WebDancer** https://arxiv.org/abs/2505.22648 : four stages (browse data, trajectories, SFT cold start, RL), ReAct agent, GAIA and WebWalkerQA; no numbers in abstract.

### RL frameworks and single-GPU limits for a 27B LoRA
- **TRL GRPOTrainer** [full] https://huggingface.co/docs/trl/main/en/grpo_trainer : vLLM colocate mode shares the GPU (default `vllm_gpu_memory_utilization` 0.3); `beta=0.0` default means no reference model loaded (saves memory); LoRA via `peft_config`, QLoRA with `quantization_config`; reward functions are plain Python returning floats, summed or weighted; default loss `dapo`; tools and `environment_factory` for multi-turn (needs transformers>=5.2.0); `max_tool_calling_iterations`; tool-turn cap applies to the whole completion.
- **Unsloth** [full] https://unsloth.ai/docs/get-started/reinforcement-learning-rl-guide and memory page: QLoRA 4-bit rule of thumb "model parameters = VRAM you need"; LoRA 16-bit needs at least 4x QLoRA; only published big-model data point: Qwen3-32B LoRA 16-bit GRPO on 1x H100 80GB, context 6,144 per generation with 2 generations. No 27B figure anywhere. Expect at least 300 steps before reward rises, about 12 hours minimum, sometimes 1,000+; at least 500 rows suggested; use a rubric of small verifiable rewards, not one all-or-nothing reward. Page does not discuss reward hacking.
- **verl** [full] https://github.com/volcengine/verl : PPO, GRPO, DAPO, RLOO and others; FSDP/FSDP2/Megatron training, vLLM/SGLang rollout; multi-GPU LoRA RL with a Qwen3-8B example; single-GPU: not addressed on the page.
- **OpenRLHF** [full] https://github.com/OpenRLHF/OpenRLHF : Ray + vLLM + DeepSpeed ZeRO-3; says generation is about 80% of RLHF time; LoRA/QLoRA flags; multi-turn agents via `reset()`/`step()`; template is 8x A100 80GB, 70B+ scale; single-GPU: not stated.
- **SkyRL** [full] https://github.com/NovaSky-AI/SkyRL : `skyrl-train`, `skyrl-agent`, `skyrl-gym` (math, code, search, SQL environments); SkyRL-SQL-7B trained on 653 samples, reported above GPT-4o and o4-mini on Text2SQL (no scores on the page); hardware specifics: not stated.
- **Mezon-specific arithmetic (my arithmetic, not sourced):** per CLAUDE.md the card is 96 GB with about 55% held by the Qwen chat model, leaving about 43 GB. 27B parameters in bf16 is about 54 GB for weights alone, so a 16-bit LoRA run does not fit while the chat model stays up; 4-bit QLoRA weights (about 14 GB) plus vLLM rollouts could. Treat as a plan to test, not a result. Never run `qwen off` or `qwen switch` (CLAUDE.md).

---

## What Mezon should copy (10 practices, cheapest first)

1. **Read transcripts and label binary with a critique; one expert per dimension.** Husain (llm-judge, evals); Anthropic evals post ("Read the transcripts"). Cost: hours. The existing `/review` screen with keys 1/2/3 already is the one-screen viewer; add a mandatory one-line critique per verdict and keep the critiques as few-shot examples.
2. **Always print N and a 95% CI, cluster by decision or district, compare checks with paired differences.** Miller 2024. Cost: a few lines in `eval/`. Matches the CLAUDE.md rule "always give N"; fixes the 3-month-rule flags that cluster by body.
3. **Keep checks 1 to 3 and 7 to 11 deterministic and the citation validator mechanical; never trust the model's stated reasoning.** Anthropic graders guidance (deterministic first), interpretability post (reasoning can be unfaithful), Stanford legal study (17 to 33% hallucination even in commercial RAG). Cost: already built; extend it to check every quote appears verbatim in the cited article text on the decision date.
4. **Balanced eval set: positives and in-force negatives, plus an "unclear" option.** Anthropic evals (test both directions, allow "Unknown"). Cost: low; the 30 cancelled vs 30 in force plan in CLAUDE.md is exactly this. Report recall on the small bad class, never accuracy.
5. **Start with 20 to 50 tasks from real failures, two experts must agree on each, each has a reference solution.** Anthropic evals. Cost: lawyer time. The three golden cases plus lawyer-reviewed flags are the seed; add an inter-lawyer agreement figure.
6. **Use pass^k style consistency for anything the demo relies on.** Anthropic evals (75% per trial is about 42% for 3). Cost: rerun `research.demo_check` several times with sampling on; any case that fails once in k is not demo-safe.
7. **Calibrate any LLM judge or drift check (check 5) against the lawyer: report true-positive and true-negative rates on a held-out test split, run the frozen judge on test once.** Husain llm-judge; Weng (judge bias, k=3 evidence samples); Huyen (human and judge must move together; daily expert sample). Cost: medium. Judge the drift dimension separately from the others.
8. **Retrieval upgrade: contextual chunks (act, article, date prepended) for both FTS5/BM25 and embeddings, rank fusion, rerank.** Anthropic contextual retrieval (5.7% to 1.9% top-20 failure with all three steps). Cost: one LLM pass over the store. Measure on your own question set before and after; their numbers are not for Uzbek legal text.
9. **Agent loop: smallest workflow first; few purpose-built tools returning concise, high-signal text with actionable errors; cap tool turns; test tool descriptions on a held-out task set.** Anthropic building-effective-agents and writing-tools; TRL `max_tool_calling_iterations`. Cost: low. Candidate tools: `get_article(act, article, on_date)`, `search_law`, `get_decision`, each returning text with a citation id.
10. **Only then consider RL, and only against a verifier you trust; defend against hacking.** Wei (trainability tracks verifiability), Karpathy (RLVR, "non-gameable" rewards, benchmaxxing), Weng and Anthropic (hacks are learned fast, around step 100 in their setup; detectors under 60% AUROC). Practical shape: reward = citation validator passes (quote exists, article in force on the date) times label agreement on lawyer-reviewed items, as a rubric of small rewards (Unsloth), with an abstain/"unclear" action that is not penalised (OpenAI hallucination paper; GopherCite-style decline). Guards: hold out lawyer-labelled cases never used in reward, log and read rollouts, cap reward, watch for the model learning to emit "unclear" always or to edit what the validator reads. Run rank 16 to 64 LoRA, not rank 1, on this non-math task (replication caveat), as a 4-bit QLoRA first on the shared card. Cost: highest; do after items 1 to 9 give you a trustworthy eval.

## Gaps to close if time allows
- OpenAI RFT guide body and Harvey primary page (403/404 here); a browser fetch would fix it.
- Search-R1, ReSearch, R1-Searcher result tables (abstracts only).
- Karpathy "Software 3.0" talk, Schulman's own writing, Lambert's RLVR chapter, Google legal work: not found / not read.
