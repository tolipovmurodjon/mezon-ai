# Mezon-LM playbook: how we make an open model the best Uzbek legal expert (decision audit is its first application)

Written 20 Nov 2026 from 6 research reports (files in this folder, appended in full in the Gemini copy) plus our own
measured run. Read this section first; the appendices hold the sources and the exact numbers.

**Source tags used everywhere:** [full] = paper read in full · [abstract] = abstract page only · [snippet] = search
result text only · [ours] = measured on our machines. Only [full] and [ours] numbers may be said on stage; re-read the
paper before quoting anything else.

## 1. The goal and the honest standard

**Goal (Boss, changed 20 Nov evening): a foundation, not a narrow tool.** Mezon-LM is an Uzbek legal expert model:
it knows how Uzbek law is built and how to use it (laws, codes, presidential and Cabinet acts, ministry and local acts,
court rulings, every edition by date), reasons like the best lawyer or judge, and works on any legal task. Auditing
district and regional decisions is one application on top of it, and so are court-ruling analysis, legal questions,
conflict-of-norms checks and later drafting. First it learns the law and the tools; then each new task is a thin
layer. It should beat frontier models (Claude Opus, Fable, GPT) on Uzbek law and, later, real lawyers, proven on
MezonBench with blind expert grading. (The hackathon demo stays the local-decision audit: the first application.)

**What "foundation" means in practice** (stages in section 4 are ordered this way):
1. **Know the system:** the hierarchy of norms, how acts amend and repeal each other, how editions work, the legal
   vocabulary in Latin, Cyrillic and Russian. Continued pre-training on all of lex.uz + verified Q&A built from it.
2. **Use the tools:** never answer from memory; look the article up as of the date, verify the quote.
3. **Reason in many task families:** statute questions, conflicts of norms, court rulings (what was decided and on
   which norm), decision audits, explanations for a citizen. Each family has a verifier or a lawyer grader.
4. **Prove it per family** on MezonBench, so a gain in one family can't hide a loss in another.

**The standard for each claim** (from expert_reasoning.md: the AMIE crossover, the Martínez re-evaluation of the GPT-4
bar-exam claim, the IMO 2025 grading dispute):
| Claim | What must exist first |
|---|---|
| "Gets the citation right" | the citation validator at 100 % on every flag [ours, enforced] |
| "Beats model X on this task" | held-out decisions dated after both models' cutoffs, same tools for both, N, 95 % CI, paired comparison |
| "Saves reviewer time" | a crossover: the same reviewers with and without Mezon, timed (5 reviews = a pilot, not proof) |
| "Better than a lawyer on this task" | Mezon vs lawyers on the same decisions, graded blind by an independent Adliya panel, ≥ 100 decisions, ≥ 5 reviewers (our proposal) |
| "Finds what experts miss" | prospective: flags made before an official outcome, checked when the outcome arrives |

**Expert, not intern (Boss, 20 Nov):** a top lawyer knows the system by heart (hierarchy, principles, the shape of
each code, typical defects), reasons first, and opens the code book only to confirm the exact wording and edition of
what they will cite. Mezon-LM must work the same way:
- **Knowledge in the weights:** continued pre-training on all of lex.uz + reasoning SFT, so the model knows where
  things are and how they fit without looking them up (measured closed-book on MezonBench: flip, hierarchy, in_force).
- **Reasoning first:** think through the issue (what rule, which date, which force wins) before any tool call;
  RL rewards the right conclusion, not the number of lookups (the 2025 reasoning models: DeepSeek-R1, Qwen3 thinking,
  OpenAI o3 thinking with tools; IMO 2025 gold was natural-language reasoning with no tools).
- **Tools only to verify:** 1-3 targeted calls to confirm the articles it will cite; the RL reward carries a small
  cost per tool call so it learns to act less and reason more (verify the 2025 tool-efficiency papers before citing).
- **Morning briefing (Boss's idea, 20 Nov):** before work, the model gets a short digest of what changed in the law
  since its last training (new acts, amended articles with old vs new wording, acts that lost force), built daily
  from the lex.uz sync. Like a lawyer reading the official gazette with coffee: fresh facts in context, deep knowledge
  in the weights, and each retraining folds the recent digests into the weights.
- **Tool cost, done right:** the cost applies only to extra lookups beyond a small budget. Checking an article it is
  about to cite is never penalised; skipping that check is (otherwise RL teaches it to stop verifying and guess).
- The citation validator still checks every final citation: knowledge can be fuzzy, the output can't.

## 2. Where we stand [ours]

- Base: **Qwen3.8-27B** (dense, 64 layers = 48 Gated-DeltaNet linear-attention + 16 full attention, hidden 5120,
  vocab 248,320, context 262,144, vision built in, 55.6 GB bf16, Apache-2.0). It is real: the Qwen3.8 family on
  Hugging Face is 27B, Flash-Next (125B total / 6B active, licence qwen-community-1.0) and 2.4T-A95B. There is no
  smaller 3.8 model; the small ladder is **Qwen3.5 0.8B / 2B / 4B / 9B**.
- Run 1 (20 Nov): bf16 LoRA rank 16 on the RTX PRO 6000, 825 train / 91 held-out, 2 passes, **52.8 min**, 70.6 GB
  peak. Held-out loss **2.382 → 0.0253 (pass 1) → 0.0232 (end)**. Adapter: `data/models/sft/final` on the 6000, copied
  to R2.
- **What it learned:** the Adliya answer format. **What it did not learn:** law. 672 of 917 answers were the same
  "no defects" JSON, written by our own rule engine. This adapter is the **baseline**, not the product.
- Hardware: the 6000 (96 GB) is ours alone, nothing else shares it (two agents assumed it shares Boss's chat model;
  that is the old box, not this one). The L40S (48 GB) runs the crawl, the OCR server and the demo.

## 3. The ten findings that decide the design

1. **Facts go in the database, skills go in the weights.** On events after the cutoff, RAG beat fine-tuning by a
   wide margin (Mistral 7B: base 0.481 · fine-tuned 0.504 · fine-tuned on paraphrases 0.588 · **RAG 0.875**; Ovadia
   [full]). Training on facts the model doesn't know raises hallucination (Gekhman [full]: 37.5 → 25.8 accuracy;
   relabelling those examples "I don't know" kept 61.8). → All law text and editions stay in the law store; weights learn
   how to read a dated edition, quote exactly and say "unclear".
2. **Date-conditioned retrieval over a versioned corpus is the fix for temporal errors.** LegalSearch-R1 (Qwen2.5-7B,
   GRPO, Chinese law, 16 statutes with every amendment version) beat DeepSeek-V3.2 in-domain (55.90 vs 50.56) and on
   article recitation (96.73 vs 63.30), but lost out of domain (63.67 vs 66.41) [read through a summariser; re-read the
   tables]. Its weak spots we fix: the date was not a tool argument, the reward had no citation or temporal term, and
   "temporal consistency" only counted dated queries.
3. **Legal AI tools hallucinate 17-33 % even with retrieval** (Stanford, Magesh et al. 2024). Our cite-or-drop validator
   is exactly the defence against that. This is the pitch line.
4. **RL with a verifiable reward is where small models overtake big ones**, but only where a cheap verifier exists
   (Jason Wei: trainability tracks verifiability; DeepSeek-R1 AIME 15.6 → 77.9 [full]; Qwen3 reasoning RL used only
   3,995 query-verifier pairs [full]). Our verifier: the article exists on that date + the quote is a verbatim substring
   of that edition + the verdict matches the real outcome.
5. **Reward hacking arrives fast.** Anthropic saw the hack rate rise from about 0 to 0.8-1.0 within ~100 RL steps
   [full]; RL can turn honest abstentions into confident wrong answers (Choi, Leskovec et al. [abstract]). → A
   three-level "unclear" reward, a held-out checker that is never in the reward, read the rollouts, track the abstain
   rate.
6. **For a small model, distillation from a strong teacher is cheaper than RL** (Qwen3 8B: on-policy distillation 1,800
   GPU-hours vs 17,920 for RL [full]). → Teacher traces must pass our verifier, and a cloud teacher may only see public
   lex.uz texts, with Boss's yes.
7. **A few hundred to a few thousand clean examples beat large noisy sets** (LIMO 817 samples, s1 1,000 [snippet];
   Lawma beats GPT-4 on most of 260 legal classification tasks with dozens to hundreds of labels per task [snippet]).
8. **LoRA is enough, and forgets less** (LoRA learns less, forgets less, Biderman [full]; rank 16-64, not rank 1: the
   rank-1 results were math only and a Qwen3-0.6B replication found rank 64 clearly better [snippet]).
9. **Learning a small corpus into the weights needs many rewrites** (EntiGraph: 1.3M source tokens → 455M synthetic,
   Llama 3 8B 39.49 % → 56.22 % closed-book, vs 60.35 % with RAG [full]). → Continued pre-training on lex.uz is a later,
   measured experiment, not the core.
10. **Evals: report N, standard error, clustering and paired differences** (Miller, Anthropic [full]: clustered SEs were
    over 3× larger). Agent evals: 20-50 tasks from real failures, two experts agree on each verdict, pass^k for
    consistency, an "Unknown" option (Anthropic [full]).

## 4. The recipe, stage by stage

| Stage | What we build | Why (source) | Size and cost (our estimate) |
|---|---|---|---|
| **F. Foundation curriculum** (runs under every stage below) | task families, each with its own data, verifier and benchmark track: (1) **law lookup as of date** (all 166,705 lex.uz acts); (2) **hierarchy and conflicts** (which norm wins and why, NLA arts. 6, 18); (3) **amendment history** (what changed, when, by which act); (4) **court rulings** (61,049 administrative cases: outcome + the norm applied); (5) **decision audit** (local, later ministry acts); (6) **plain explanation** for a citizen or business, generated only from verified results. Continued pre-training on all lex.uz text (every edition, 3 languages) with ~10 % general replay, measured on the benchmark before keeping it | Boss's goal; EntiGraph (corpus learning needs rewrites), Ovadia/Gekhman (facts stay in retrieval), Qwen3 (multi-stage post-training) | CPT: est. 0.5-2B tokens after the full crawl; measure on a 50M-token pilot first |
| **0. MezonBench v1** | per family above; first 4 tracks: (a) **as-of-date recitation**: "article X of act Y on date D" incl. dates just before/after an amendment; (b) **flip pairs**: the same decision checked on two dates where the law changed; (c) **citation audit**: does each cited article exist and stand on that date; (d) **full audit**: decisions later cancelled on adliya representation / protest / court + clean in-force controls. Time split after all models' cutoffs; acts held out; Wilson CI + paired bootstrap; abstain rate; pass^3. Frontier models only on public lex.uz items, only with Boss's yes. | LegalSearch-R1 eval style, Miller, Anthropic agent evals, Stanford labels | 200-400 items, mostly generated from the law store; lawyers grade track (d) |
| **1. Tools** | `law_as_of(act, article, date)` (date required), `list_editions(act)`, `search_law(query, date)`, `get_decision(reg)`, `verify_quote(act, article, date, quote)`; traces in Qwen's real `<think>` `<tool_call>` `<tool_response>` tokens (read the local chat_template.jinja first), final answer = Adliya JSON; ≤ 8 tool calls per audit | LegalSearch-R1 tool loop, Anthropic "small tool set, turn caps" | 1 day |
| **2. Real teacher data** | (a) **RAFT-style** examples: the right edition + 4 distractors incl. older/newer editions of the same article; (b) **cancellation cases**: the cancelling act's text (adliya representation, protest, court) gives the real defect and reason; (c) **"unclear" relabel** where the store has no basis; (d) **lawyer step traces** (issue → rule as of date → application → conclusion) for 50-100 cases; every example passes the validator | RAFT, Gekhman, MSLR (60K step labels), Lightman process supervision | 2-5K examples; days, mostly generation on our GPUs |
| **3. Cold-start SFT** | rejection sampling: the 27B with tools writes N attempts, keep the ones the verifier passes, LoRA r16-32 on them | DeepSeek-R1 cold start, GLM-4.5 expert iteration | ~3-7 GPU-hours on the 6000 |
| **4. RL** | GRPO with DAPO-style fixes; reward = format gate × (citation validity + outcome match + temporal correctness) with **unclear**: warranted → small positive, lazy (basis existed) → negative, wrong confident → most negative; unverifiable citation → negative, citing the current edition when an older one applied → extra negative. 27B: expert iteration (offline rounds) on one 96 GB card; online GRPO on a Qwen3.5-9B sibling | DAPO, Dr.GRPO, TRL GRPOTrainer (LoRA, tools, multi-turn), reward-hacking papers | 27B expert iteration ~40-60 GPU-hours; 9B online GRPO ~30-60 GPU-hours |
| **5. Optional CPT** | synthetic continued pre-training on lex.uz (EntiGraph-style rewrites) with ~10 % replay; keep only if MezonBench rises without hurting format and tools | EntiGraph, replay scaling laws | measure first; weeks |
| **6. Human proof ladder** | crossover with district adliya reviewers → blind Adliya panel vs lawyers → prospective flags | AMIE, Goh trial, IMO grading | months, with Adliya |

**Every data source feeds the foundation (so Adliya can later point it at any legal job):**
| Source | What the model learns from it | Task families | Stage |
|---|---|---|---|
| lex.uz, all 166,705 acts, every edition, 3 languages | the legal language, the hierarchy, how acts amend and repeal each other | all; lookup, conflicts, history | CPT + tools + generated Q&A |
| lex.uz relations (cites / cited-by / amended-by) | the law graph: which act implements, amends or cancels which | history, conflicts, mandate drift | generated Q&A + tool `list_editions` |
| lex.uz cancellation notes + cancelling acts | real reasons decisions were cancelled (adliya representation, protest, court) | decision audit | SFT teacher data, RL outcome reward |
| public.sud.uz (61,049 administrative rulings; PDFs later) | outcomes and the norms courts apply | court-ruling analysis, outcome prediction | eval first, SFT later; never names (strip parties and judges) |
| stat.sud.uz | how often each kind of decision loses in court | calibration, risk priors | features, pitch numbers |
| e-qaror.gov.uz + e-qaror-respublika | adoption stages, basis lines, declared-invalid labels, parent acts | procedure checks, audit, mandate drift | labels + eval |
| regulation.gov.uz / regulation.adliya.uz | drafts, discussion windows, draft vs adopted | gate 0 review, checks 9-11 | eval + SFT |
| sharh.lex.uz (commentary) | expert interpretation of articles | interpretation, reasoning | only after the licence check |
| data.egov.uz (Adliya datasets) | registers of acts | lookup coverage | store |
| gov.uz, my.gov.uz, government Telegram channels | which body does what; citizen services; early signals | routing, plain explanation | later |
| OCR of 2,074 scanned PDFs (PaddleOCR-VL) | the texts lex.uz only has as images | all | joins the corpus |
| lawyers' reviews (/review) and the 40-question exam | expert judgement | every family's grader | eval, then preference / RL data |

**Model roles:** Qwen3.8-27B = the main auditor. Qwen3.5-9B = the fast filter and the online-RL testbed (IFEval 91.5,
~22 GB bf16 LoRA per Unsloth). Qwen3.5-4B = fallback. The citizen app stays a thin client on our server. Flash-Next is
out (licence, size).

**Serving notes (qwen38_family.md):** vLLM needs `--mamba-cache-mode align` for prefix caching on the hybrid layers
(experimental), Blackwell needs the cu130 build, tool calls use the `qwen3_coder` parser, `enable_thinking=false` turns
thinking off, fine-tuning needs `flash-linear-attention >= 0.4.2` + `causal-conv1d`.

## 5. What we do before the freeze (Sat 21 Nov 10:00) and after

**Before (only what can be measured by morning):**
1. The 5 tools on the local law store, with tests (the verifier rejects a fabricated article, a repealed edition and a
   non-verbatim quote).
2. MezonBench v1 tracks (a)-(c) generated from the law store; track (d) from the existing positives + clean controls.
3. Run: base Qwen3.8-27B with tools vs run-1 adapter vs rules alone. Print N, CI, abstain rate.
4. The pitch says: the benchmark, the validator at 100 %, the measured baseline, and the recipe as the roadmap.
   No "trained model beats GPT" claim.

**After (2 weeks):** real teacher data, cold-start SFT, the 9B RL pilot (~250 steps), then 27B expert iteration.
**After (2 months):** full RL, a rolling post-cutoff eval every month, the crossover with Adliya reviewers.

## 6. Keeping it current (laws change weekly)

- The law store syncs daily (lex.uz RSS + edition checks); the model never needs retraining to know a new law.
- Weights are retrained only for skills, about quarterly, with ~10 % replay data (our judgement, not a source).
- Freshness tests in MezonBench: a law changed yesterday (ask on the day before and the day after), an injected stale
  edition (does the model trust the tool or its memory), a missing-edition refusal.
- No knowledge editing (ROME/MEMIT): it degrades over many sequential edits [snippet] and nobody reports it in
  production.

## 7. Open questions and known gaps

- LegalSearch-R1's exact tables, the OpenAI RFT guide, Harvey's primary pages, the search-agent RL result tables and
  Karpathy's "Software 3.0" talk were not read in full (blocked or not found).
- No public Uzbek legal benchmark exists for any model; MezonBench is itself a contribution.
- No source tests online GRPO on a 27B hybrid-attention model on one GPU; the 9B route is an engineering bet.
- The GPU-hour figures in section 4 are our estimates.

## Appendix files (in this folder)
legalsearch_r1.md · qwen38_family.md · open_lab_recipes.md · frontier_lab_guidance.md · knowledge_freshness.md ·
expert_reasoning.md · research_llm_domain_2026.md (first pass, in docs/)
