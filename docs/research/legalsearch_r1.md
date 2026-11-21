# LegalSearch-R1 playbook for Mezon (written 20 Nov 2026)

Self-contained. Part A = what the paper says. Part B = what we do on Qwen3.8-27B.
Evidence marks: no mark = read in the paper's full HTML text. [snippet] = seen only in an abstract or search snippet. "not stated" = the paper does not say. [estimate] = our own number, not from any source. [background] = from my general knowledge, not checked in this session.
Honest caveat on method: I read the paper through a page-to-text tool with a summariser on top, not the raw PDF. I cross-checked its headline arithmetic (see A6) but I did not see a verbatim quote for every number. Before you cite a number on stage, open the table in the paper.

---------------------------------------------------------------------------

## PART A. What LegalSearch-R1 is

Paper: "Can LLMs Time Travel? Enhancing Temporal Consistency in Legal Agentic Search through Reinforcement Learning" (LegalSearch-R1). Fan, Zhou, Zhang, Weng, Hu, Zheng, Xu, Li, Yang, Li, Song (HKUST KnowComp group). arXiv 2605.25920, v1 25 May 2026, v2 19 Sep 2026, accepted at EMNLP NLLP 2026.
Links: https://arxiv.org/abs/2605.25920 · https://arxiv.org/html/2605.25920 · code https://github.com/HKUST-KnowComp/LegalSearch-R1

### A1. Task, inputs, outputs, jurisdiction
- Legal agentic search over **Chinese law, Chinese language**. No other jurisdiction or language tested (stated limitation).
- Input is a pair (q, t_q): the question and the year the legal events happened. t_q decides which statute version applies. The model must not use the date of today.
- The agent works in a ReAct-style loop: think, plan, call tool, read observation, answer. Output is a task answer in `<answer>` tags (a multiple-choice letter, a recited article text, a judgment, etc., depending on the task).
- 13 benchmark tasks: 7 in-domain (KQA, CCP, PTP, LCA, LCS from LawBench; LAP from LexEval; LAR new) and 6 out-of-domain professional exams from DISC-LawEval (CPA, PAE, NJE, UNGEE, LBK, PFE) with the publication year added as temporal context.
- LAR = Legal Article Recitation: "recite the statute text as it read at time t". Scored by character-level ROUGE-L. This is the task closest to our verifier (see B1).

### A2. Retrieval tools and trace format
Tool set T = {web_search, rag_retrieve, browse_webpage}.
- **rag_retrieve (the time-indexed statute tool).** Local corpus of **16 statutes, all amendment versions**. Every article chunk carries a validity window (t_from, t_to). Pipeline:
  1. An LLM query analyser (Qwen3-30B-A3B) extracts temporal references, article/chapter ids (turned into Chinese numerals) and keywords.
  2. Temporal filter: keep only provisions whose validity window overlaps t_q.
  3. Three scoring channels: keyword match weight 3.0, FAISS dense weight 2.0, BM25 weight 1.0.
  4. Reciprocal Rank Fusion: score(d) = sum over channels w_c / (K + r_c(d)), K = 60.
  - Argument schema: one parameter, `query`, an array of strings (example "2015 intentional homicide"). The date is NOT a separate argument; it is in the query text and parsed by the analyser. Top-k: "top-k results are returned", value **not stated**.
- **web_search**: Serper API, returns title/URL/snippet; for things not in the local corpus (judicial interpretations, commentary).
- **browse_webpage**: fetches a URL from earlier results; a reading agent (Qwen3-30B-A3B with a domain prompt) keeps statute text verbatim, keeps effective dates and revision history.
- Routing rule in the system prompt: article-specific questions go to rag_retrieve; theory/case/practice go to web_search. The system prompt says the model's own knowledge may be outdated and forbids using information not obtained through tools.
- Trace format: round 1 = `<think>` + `<plan>`; middle rounds = `<think>` + `<tool_call>` (JSON object with `name` and `arguments`); last round = `<think>` + `<answer>`. **Max 15 assistant turns.** Calls per episode: no fixed count beyond the 15-turn cap.
- How retrieved text is inserted: as the observation of the tool call (tool response turn). Exact template: not stated in the text I read.
- Loss masking of tool text: **not stated explicitly.** Only a hint: GRPO normalisation counts "agent-generated tokens (excluding tool responses)". Search-R1 (related work) states "retrieved token masking" in its abstract [snippet]. Assume masking is required; do it ourselves.

### A3. Models and training
- Backbone: **Qwen2.5-7B-Instruct, full-parameter** training. Helper LLM for browse/query analysis: Qwen3-30B-A3B.
- **SFT / cold start: none reported.** Pure end-to-end RL from the instruct model.
- Framework: VERL, asynchronous multi-turn rollouts, FSDP with parameter+optimizer offload, Ulysses sequence parallel size 4. Hardware: one node, 8 x NVIDIA H100. **GPU-hours / wall-clock: not stated.**
- RL algorithm: token-level **GRPO** plus Entropy-based Advantage Shaping (EAS) on planning tokens: psi = min(alpha * H_detach, |A| / kappa), A_EAS = A + psi.
- Hyperparameters (all as reported): batch 64 prompts; G = 8 rollouts per prompt; 112 steps; LR 1e-6; alpha 0.1; kappa 2; clip epsilon 0.2; **KL coefficient 0; entropy coefficient 0**; max prompt 4,096 tokens; max response 28,671; max context 32,767; rollout temperature 1.0, top-p 1.0. Evaluation: temperature 0, one rollout per prompt.
- Total rollouts = 64 x 8 x 112 = 57,344 (my arithmetic).

### A4. Reward (it is simpler than you might expect)
- Reward = 0 if the format check fails (balanced XML tags; a plan must be present in round 1).
- Otherwise a **binary task score**:
  - LAR: ROUGE-L >= 0.95 -> 1.
  - CCP: unordered match with suffix normalisation.
  - LCS: LLM judge scores answer and legal basis; reward 1 only if both correct.
  - other tasks: exact match.
- Not in the paper: weighted components, a temporal reward, a citation reward, penalties. **Temporal behaviour emerges from the task design** (the answer is only right if the right version was retrieved), not from a temporal reward term.
- Reward hacking and lazy abstention: **not discussed.** Tasks have forced answers, so abstention does not exist. This is a real gap for us (B3).
- Train/eval mismatch: training reward for LAR is binary at 0.95, eval is continuous ROUGE-L.

### A5. Data
- Sources: LawBench, LexEval, DISC-LawEval, plus the authors' own LAR annotations by law students (13 amendment versions 2000-2025 of the Criminal Law, Criminal Procedure Law, Civil Procedure Law; annotators pick articles that changed by a 20% character threshold or a clear change in meaning). More than 100,000 candidate questions were considered.
- Train: 3,584 samples (512 per task x 7), of which 2,104 are temporal. In-domain test: 896 (128 per task), 610 temporal. Out-of-domain test: 768 (128 per task x 6), 571 temporal (74%).
- Time split and contamination handling: **not stated.** Splits are by task sample, not by date.

### A6. Evaluation and results
Baselines: legal LLMs (DISC-LawLLM, LegalDelta, each with and without CoT); vanilla LLMs (GPT-4o-mini, Qwen-2.5-7B, Qwen-3 8B/14B/30B-A3B); reasoning models (o4-mini, QwQ-32B, Qwen-3-30B-A3B thinking, DeepSeek-V3.2); deep-research agents (Search-R1 base/instruct, DeepResearcher, DeepPlanner) retrained on the same legal data with the same 7B backbone. Not included (stated): LRAS (no public weights), Fuzi-Mingcha and Hanfei (could not follow the `<answer>` format).

In-domain averages (Table 2): LegalSearch-R1 55.90; DeepSeek-V3.2 50.56; LegalDelta (no think) 48.71; Qwen-3-30B-A3B thinking 46.62; DeepPlanner 39.19; Search-R1-instruct 34.51. Text claims +42.7% over DeepPlanner and +10.6% over DeepSeek-V3.2; I checked: 55.90/39.19 = 1.426 and 55.90/50.56 = 1.106, so both match.
LAR (the recitation task): LegalSearch-R1 96.73 ROUGE-L vs DeepSeek-V3.2 63.30, DeepPlanner 54.02, Qwen-3-30B-A3B thinking 43.14, Search-R1-instruct 35.31. This is where retrieval-by-time matters most.
It does NOT win every task: DeepSeek-V3.2 is higher on LCS (42.97 vs 35.16), KQA (62.50 vs 50.00), LCA (50.00 vs 46.09); LegalDelta higher on PTP, LCA, CCP.
Out-of-domain (Table 4): LegalSearch-R1 63.67 average (CPA 70.31, PAE 42.19, NJE 41.41, UNGEE 70.31, LBK 74.22, PFE 83.59); DeepSeek-V3.2 66.41 (higher); Qwen-3-30B-A3B 63.80; best deep-research baseline DeepPlanner 53.91; best legal LLM LegalDelta 49.35.
Abstract headline: "+12.9% to 29.8%" over deep-research frameworks and specialised legal LLMs (the abstract's own words, quoted via summary); I could not reconcile these two percentages with a specific table cell. "+57.7% to 80.3%" is for temporal consistency over baselines.
**Temporal-consistency metric (what it really is):** not formally defined. It is the **count of search queries that contain an explicit temporal reference**. Baselines: 97 to 227. LegalSearch-R1: 502 in-domain, 537 out-of-domain (+121% to +454%; I checked 502/227 = 2.21 and 537/97 = 5.54). During training, temporal queries rise from about 100 to over 250. So their "temporal consistency" is a behaviour proxy, not "the article cited was the right edition". Ours can be stricter (B5).
Ablation: only one. Removing rag_retrieve lowers the final training reward from 0.561 to 0.469. **No ablation of EAS, no SFT ablation, no model-size ablation, no reward ablation.** Seeds and confidence intervals: **not stated**; single greedy rollout per prompt.
Failure analysis: only one case study (a 2001-2004 inheritance dispute; baselines applied the current 2021 Civil Code and got the opposite result; the agent used web_search for the change and rag_retrieve for the pre-amendment Inheritance Law Art. 20). No systematic error breakdown.
Limitations (authors): Chinese only; statutes only, no case law in the corpus; excluded baselines listed above.

### A7. Licence
- Code repo: **Apache-2.0** (repo LICENSE/sidebar). Repo has folders data/, evaluate/, user/, verl/, scripts `user/train.sh`, `user/evaluate.sh`, `user/evaluate_ood.sh`, data processing `user/legalsearch_data_process.py`; config `user/tools/config.yaml` wants an OpenAI key and a Serper key. README does not describe a released dataset, model weights, reward code or tool API (I did not open the source files; the reward and tool code may be inside `verl/` or `user/`: worth a 10-minute look).
- Paper text: arXiv perpetual non-exclusive licence (not CC). Weights: none mentioned. Data licence: not stated.

---------------------------------------------------------------------------

## A8. Closest related work (what each adds)

| Paper | What it gives us | Key numbers | Read depth |
|---|---|---|---|
| "Asking For An Old Friend", arXiv 2605.23497 (ICAIL 2026), https://arxiv.org/html/2605.23497 | German statutory QA, 312 expert-validated pairs (115 post-cutoff, 113 single-provision pre-amendment, 84 multi-provision pre-amendment; 39 duplicate pairs kept as a consistency check). Failure modes: post-cutoff staleness, recency bias. Compares vanilla / web search / RAG-ToC / RAG-kNN with a regex-extracted as-of date filter (k = 6, text-embedding-3-large). | Perfect-outcome %: Claude Sonnet 3.7 post-cutoff vanilla 24.35 -> web 63.48 -> RAG-ToC 83.48 / RAG-kNN 86.96. Claude Opus 4.5 pre-amendment vanilla 35.40 -> RAG 78.76-81.42. DeepSeek V3.2 pre-amendment only 44.25-50.44 with RAG. Removing the date filter: "substantial drop", no figure. Judge validated on 48 questions, r = 0.853, kappa = 0.751. | full text |
| "When Do LLMs Apply the Wrong Law?", TALD-Bench, arXiv 2608.14610, https://arxiv.org/abs/2608.14610 | 51,956 Chinese civil judgments around the Civil Code; 9 LLMs; strong bias to newer law; hints help. | >70% accuracy on new-law cases, <25% on old-law cases. CC BY 4.0. | abstract only [snippet] |
| "Temporal Misgrounding in Legal RAG" (FiscalQA Pro), arXiv 2608.09393, https://arxiv.org/abs/2608.09393 | French tax code, versioned corpus of 32,436 article-versions; 209 scored questions; deterministic scoring (regex/numeric nuggets), deliberately no LLM judge. | Closed-book 3.0%; static current-version RAG 2.7% (retrieves the date-applicable version 0% of the time); multi-version index with date conditioning 98.3%; oracle article 99.1% (so the remaining gap is first-stage recall). | abstract only [snippet] |
| LexKairos, arXiv 2608.09106 (https://arxiv.org/pdf/2608.09106; code github.com/thunlp/LexKairos) | 9 Chinese sub-tasks on statute temporal knowledge, case temporal modelling, statute-case reasoning; 8 LLMs under vanilla/CoT/thinking; Gemini-3-Flash best; models weak at time-sensitive statute metadata recall. | not read | [snippet] |
| CALRK-Bench, arXiv 2603.26332 (https://arxiv.org/abs/2603.26332; code github.com/jhCOR/CALRKBench) | Korean law: temporal validity of norms, sufficiency of information, why judgments shift; recent LLMs score low. | not read | [snippet] |
| Search-R1, arXiv 2503.09516 | Outcome reward + "retrieved token masking"; +41% (Qwen2.5-7B) and +20% (Qwen2.5-3B) over RAG baselines on 7 QA sets. | | abstract only [snippet] |
| ReSearch 2503.19470; R1-Searcher 2503.05592 | RL teaches when to search with no step labels; R1-Searcher is two-stage outcome-based RL with no cold-start distillation. Reward details not seen. | | abstract only [snippet] |
| DAPO 2503.14476 | Open RL system on verl; 50 AIME-2024 points with Qwen2.5-32B base [snippet]. The four techniques (clip-higher, dynamic sampling, token-level loss, overlong reward shaping) are [background], not verified in this session. | | abstract only |
| Dr. GRPO 2503.20783 | Identifies an optimisation bias in GRPO that inflates response length, especially for wrong answers [snippet]. That it also removes the std-normalisation is [background]. | | abstract only |

What the related work agrees on (and the paper's own case study shows): models default to the newest law; the fix that works is date-conditioned retrieval over a versioned corpus. Our law store is exactly that.

---------------------------------------------------------------------------

## PART B. Mezon on top of Qwen3.8-27B

Our task is different: audit a hokim/Kengash decision against national law as it read on the decision date; output the Adliya-style conclusion (positive / positive with fixable defects / negative) with, for every defect, act + article + verbatim quote. Rule from the project: no flag without a valid citation; "flagged" never "illegal"; no decision text to a cloud API.

### B1. Mapping: paper component -> our component

| LegalSearch-R1 | Mezon |
|---|---|
| (q, t_q): question + year of events | (decision text, decision date D, decision reg. number, body). D is the adoption date; the date is exact (day), not a year. |
| rag_retrieve over 16 statutes, each article with (t_from, t_to) | `law_as_of` / `search_law` over the whole lex.uz store: act -> article -> edition with valid_from/valid_to (SQLite + FTS5). Far larger corpus; much less curated. |
| LLM query analyser infers the date from query text | **Date is a required, explicit argument** supplied by the model (and checkable: must equal D or a derived date). No analyser needed. Our improvement over the paper. |
| Keyword 3.0 + FAISS 2.0 + BM25 1.0, RRF K=60 | FTS5 (BM25) first; add embedding channel (bge-m3 or e5, not chosen yet) and RRF later. Start with FTS5 + exact article lookup. |
| web_search, browse_webpage | **Not used.** Local only (no cloud calls). lex.uz is already crawled. |
| LAR task (recite the text as of t) | Free, unlimited, exactly verifiable training/eval task from the store: "Quote article N of act X as it read on date D". Scored with our verifier. |
| Format check -> reward 0 | Same, plus: JSON parses, verdict enum valid, each defect has the 4 fields. |
| Binary answer-correctness reward | Verifier-based reward: citation valid + quote verbatim + (when available) outcome label match. See B3. |
| LCS LLM-judge "answer and legal basis both right" | Replaced by our deterministic verifier (no judge needed for citation validity). A local-model judge only for "does the quote support the defect", and only for eval, never as the RL reward in v1. |
| Training data 3,584 mixed tasks | 4 task families (B4). |
| Temporal consistency = count of queries with explicit dates | Stricter: share of cited (act, article) where the edition in force on D was the one cited AND quote is a verbatim substring of that edition. Plus flip tests. |
| Qwen2.5-7B-Instruct full FT, no SFT | Qwen3.8-27B + LoRA, with a cold-start SFT (our labels are weak and scarce, see B6). |
| 8 x H100, VERL | 1 x RTX PRO 6000 96 GB (+ L40S 48 GB). |

### B2. Tool API and trace format

Use the model's own chat template (`tokenizer.apply_chat_template(messages, tools=TOOLS)`); do NOT hand-write the tool-call syntax. Qwen3 uses a JSON object inside `<tool_call>...</tool_call>` and returns results inside `<tool_response>...</tool_response>`. Newer Qwen generations may use a different body inside `<tool_call>` (for example XML-style parameters) [background, unverified for Qwen3.8]. Check the template in the checkpoint's `tokenizer_config.json` on Friday before generating any SFT data.

Tools (all read-only, all local, all deterministic):

```
law_as_of(act_id: str, article: str, date: "YYYY-MM-DD") -> {
    found: bool, act_title, article, edition_id, valid_from, valid_to,
    status: "in_force"|"not_yet"|"lost_force"|"not_found",
    text: str (full article text; capped at 3,000 chars with truncated:true) }

search_law(query: str, date: "YYYY-MM-DD", top_k: int = 5, act_ids: list[str] = None) -> {
    hits: [ {act_id, act_title, article, edition_id, valid_from, valid_to, snippet(<=300 chars), score} ] }
    # only editions in force on `date`; never returns later editions.

list_editions(act_id: str) -> { editions: [ {edition_id, valid_from, valid_to, amended_by} ] }

get_decision(reg_number: str) -> { found, body, type(qaror|farmoyish), adopted_on, in_force_on,
    clauses: [ {n, text} ], cited_acts: [str], status_notes }   # split_decision output

verify_quote(act_id: str, article: str, date: "YYYY-MM-DD", quote: str) -> {
    article_exists_on_date: bool, quote_verbatim: bool, normalized_match_ratio: float }
```
Design rules (taken from the paper's results and the related work):
- `date` mandatory; the tool errors if missing. 12 assistant turns max (paper: 15); at most 8 tool calls; every tool result capped (about 1,500 tokens) so a 27B rollout fits in 16K context in training.
- `verify_quote` is a self-check tool the model may call. The reward verifier runs separately on the final answer, so calling it is never counted as proof.
- Normalisation (apostrophes, script) is done inside the verifier with `research.textnorm`, so the quote must be a verbatim substring after the shared normalisation only.

Trace format (Qwen tokens; compare the paper's think/plan/tool_call/answer):
```
<|im_start|>system  ...role, rules, tool schemas, "your memory of the law may be outdated; use only tool results; every cited article must be fetched for the decision date"  <|im_end|>
<|im_start|>user    Decision: <reg_number>, adopted <D>. Text: <split_decision output>  <|im_end|>
<|im_start|>assistant
<think> plan: list clauses, which acts they cite, which checks apply ... </think>
<tool_call>{"name": "law_as_of", "arguments": {"act_id": "...", "article": "24", "date": "2024-01-11"}}</tool_call><|im_end|>
<|im_start|>user    <tool_response>{...}</tool_response>   <|im_end|>      (Qwen packs tool results in a user turn)
... more rounds ...
<|im_start|>assistant
<think> ... </think>
{"conclusion": "positive|positive_with_fixable_defects|negative|unclear_needs_expert",
 "defects": [ {"clause": 3, "check": 3, "act_id": "...", "article": "...", "edition_id": "...",
               "quote": "<verbatim from the edition in force on D>", "why": "..."} ],
 "unclear_reason": null | "no_citable_norm" | "text_missing" | "conflicting_editions" }<|im_end|>
```
The final answer is a JSON object (easier to verify than free tags). Keep an `<answer>` wrapper if you want to mirror the paper; not required.
Loss masking: compute loss only on assistant tokens (think, tool_call, final JSON). Mask system, user, and every `<tool_response>` span. The paper does not state this; Search-R1 [snippet] does it.

### B3. Reward function (pseudocode)

Principles: (1) hard gate on format, as the paper does; (2) citation validity is checked deterministically and is the main signal; (3) never reward a flag the verifier cannot ground (project invariant); (4) "unclear" is allowed but priced; (5) the labels are incomplete, so do not punish "no flag" harshly on decisions that merely survived.

Data facts that shape this: positives with text are few (273 of 287 positive records are E-qaror "declared invalid" rows without text; text rules can be scored only on positives that have text). Most cancelled decisions are individual decisions procedure rules can't catch. In-force does not mean lawful. So the outcome label is weak; the verifier signal is strong. Hence the weights favour verifier terms.

```python
def reward(trace, item):                 # item: decision, D, gold (maybe None), task_family
    # 0. hard gates (paper: reward 0 if format fails)
    if not format_ok(trace):           return 0.0          # JSON parses, enums valid, <=12 turns, tool calls well-formed
    if any(call.date is None for call in trace.law_calls): return 0.0
    ans = trace.final
    # 1. citation audit, per defect
    ok, bad = 0, 0
    for d in ans.defects:
        v = verifier(d.act_id, d.article, D, d.quote)   # article exists on D AND quote substring of that edition
        wrong_edition = (v.exists_today and not v.exists_on_D)   # temporal-trap: cited the current text
        if v.article_exists_on_D and v.quote_verbatim and d.edition_id == v.edition_on_D and was_retrieved(trace, d):
            ok += 1                                    # also require the text was fetched in this trace (no recall from memory)
        else:
            bad += 1 + (1 if wrong_edition else 0)     # extra penalty for the exact failure the paper targets
    cit = (ok - 1.5*bad) / max(1, ok + bad)            # in [-1.5, 1]; unverifiable citation costs 1.5 x a valid one earns
    # 2. outcome term (only when a label exists)
    out = outcome_score(ans, item.gold)                # see below
    # 3. temporal behaviour
    tmp = share(call.date == D for call in trace.law_calls)   # 1.0 if every call used the decision date
    # 4. efficiency / length
    eff = -0.02*max(0, n_tool_calls-6) - overlong_penalty(trace.tokens, soft=12000, hard=16000)
    # 5. combine
    r = 0.45*cit + 0.35*out + 0.10*tmp + 0.10*unclear_term(ans, item, trace) + eff
    if ans.defects and ok == 0:  r = min(r, -0.5)      # flags with zero grounded citation can never score well
    return clip(r, -1.5, 1.0)
```
Weights (0.45/0.35/0.10/0.10) are **our starting guesses [estimate]**, not from the paper; the paper has no weighted reward. Tune on a held-out dev set; do not tune on MezonBench test.

Outcome term by task family:
- Verification-only items (LAR-style recite; flip tests): correct iff verifier passes the requested quote -> out in {0, 1}; no gold label needed.
- Cancelled decisions with a named ground (gold.defect_type, gold.cited_norm if recoverable from the cancelling act): +1 if some verified defect matches the type (and/or the same article); +0.4 if conclusion is "negative" or "fixable" with verified but different defects (the lawyer decides); 0 if "positive" (a miss: recall); -0.3 never needed since miss is already 0 and costs reward.
- Decisions with no label (survivors): do NOT give +1 for "positive". out = 0 for a clean conclusion; verified flags there get no outcome bonus but get cit credit only if the lawyer-approved set includes them; in RL v1, restrict survivor items to precision tests: any flag there with `bad > 0` is penalised via cit; verified flags are neutral (0 out) because the label is unknown. This prevents "flag everything" without teaching "flag nothing".

Three-level "unclear" (`unclear_term`):
1. **Warranted unclear** (item is marked `expert_needed` by the lawyer or the verifier proved nothing citable exists: no article in force on D matches, or the text is missing): reward 0.6 x the reward of a perfect verified answer; no citations required; `unclear_reason` must match the machine-checkable reason.
2. **Lazy unclear** (gold has a verified defect that the model could have found, or the reason code is false): reward 0.0 for the outcome term and an extra -0.2. Strictly below a valid verified flag and equal to or slightly above a wrong or unverifiable flag (-0.5 floor), so abstaining beats hallucinating but never beats working.
3. **Partial** (model gives verified defects AND marks specific clauses `unclear` with a reason): full cit credit on verified defects, no penalty on the unclear clauses, which is what an Adliya expert does.
Anti-collapse guard: track the abstention rate per batch; if it exceeds 25% [estimate] of non-expert-needed items, scale case-2 penalty by 2x and log it. The paper has no abstention (forced answers), so this is not copied from any source; it is my design.
Reward-hacking checks to unit-test before any RL run: (a) quoting a very short substring ("the") must fail via a minimum quote length (>= 40 chars, covers a full clause) and must fail if the same quote appears in the decision itself; (b) citing an article that exists on D but is irrelevant: add a relevance check by local model for eval; for training use a cheap lexical overlap floor between quote and the defect's `why`; (c) re-fetching in a loop: eff term and 8-call cap; (d) quotes from today's edition when D is earlier: -1 extra (wrong_edition); (e) a verifier bug is a reward hack: freeze the verifier version and run its own tests (golden Qarshi / Yangiyo'l / Xatirchi must pass).

RL algorithm settings: see B4 stage 3.

### B4. Training pipeline, stage by stage

Hardware reality (check with Boss before any GPU use): per project notes the box GPU is shared with his chat model (about 55% of the card) and `qwen off` / `qwen switch` must never be run by us. 27B in bf16 is about 54 GB of weights [estimate], so training and a vLLM server do not both fit on one 96 GB card at bf16 while the chat model is loaded. The L40S (48 GB) cannot host 27B bf16; it can host a quantised copy (about 28 GB at 8-bit) [estimate], but a quantised rollout policy differs from the bf16 policy being trained. So: **no online on-policy GRPO on 27B on our hardware in the time we have.** Use expert iteration (sample with the current model, keep verifier-passing traces, SFT again). It is the same signal as RL with a binary verifier reward, offline.

Stage 0 (hours): build the 5 tools, the verifier-based reward, unit tests, the golden cases. Build item pools (below). No GPU.

Item pools (sizes are targets [estimate], all cheap because the store provides gold):
| Family | What | Source | Target N train / dev / test |
|---|---|---|---|
| F1 Recite-as-of | "quote art. N of act X as in force on D" | store, random acts, dates chosen across edition boundaries | 3,000 / 300 / 300 |
| F2 Flip pairs | same article, two dates around an amendment; answer must differ | store editions | 1,000 pairs / 100 / 150 |
| F3 Citation audit | decision + its cited acts: which cited articles lost force or did not exist on D | the 68 dead-article decisions and similar, plus synthetic from store | few hundred; see caveat |
| F4 Full audit | decision -> conclusion + verified defects | ~920 weak rule-made examples + cancelled-with-text positives | 920 train (weak), dev/test limited by positives with text (14 per notes: positives with text are scarce) |

Stage 1: Cold-start SFT on **verifier-passing traces only**. Make traces by running the base Qwen3.8-27B with the tools in a prompted loop over F1-F4 items (4 samples per item), keep only traces with reward above a threshold and 0 bad citations, plus a few hundred rewritten from the 920 rule examples (render their rule output as a tool-using trace; a lawyer spot-checks 50). Target 2,000-4,000 traces, avg about 5-6K tokens [estimate]. Why SFT here when the paper skipped it: the paper started from an instruct model with 7B and 3,584 tasks with dense answers; our final JSON is long, the labels are weak, and a 27B that has never seen Uzbek legal tool traces will waste rollouts. This is my judgement; the paper does not test SFT either way.
LoRA settings (our choice [estimate]): rank 64, alpha 128, all linear layers, LR 1e-4 to 2e-4 for SFT, 2 epochs, max length 16K, gradient checkpointing, bf16, batch 16 sequences via accumulation. Adapter outputs only; no merging until eval.
GPU-hours [estimate]: about 12-36M training tokens x about 1.5-2.5K tokens/s on one RTX PRO 6000 with gradient checkpointing -> about 3-7 GPU-hours. Treat as uncertain by a factor of 2.

Stage 2: Expert iteration rounds (RL-lite, 2 rounds). Round = sample 4-8 traces per prompt from the current model on about 2,000-3,000 fresh prompts, score with the B3 reward, keep the top trace per prompt with reward >= 0.5, drop prompts where all 8 pass or all 8 fail (this is the same idea as dynamic sampling in DAPO [background]), SFT again from the base on the union. Generation about 60-100M tokens per round at about 1-1.5K aggregate tokens/s on one card with vLLM [estimate] -> about 15-25 GPU-hours per round if the card is free; fewer if the L40S serves a quantised sampler and we accept the mismatch. Two rounds about 40-60 GPU-hours, plus SFT 2 x 5 h. These numbers are guesses; measure throughput in the first 30 minutes and recompute.

Stage 3 (only if time and a smaller model): online GRPO on a ~7-9B variant, to copy the paper's recipe where it has evidence (7B, full FT, 8 x H100, 112 steps, G = 8, batch 64, LR 1e-6, KL 0, clip 0.2, entropy 0, temp 1.0, response up to about 28K tokens). We keep: G = 8, KL 0, clip 0.2, temp 1.0; change: LoRA needs a much higher LR than full FT (about 1e-5 to 5e-5 [estimate/background]); loss aggregation token-level and no std-normalisation or length-normalisation (Dr. GRPO [snippet] for the length bias); optional clip-higher 0.28 and overlong shaping (DAPO [background]); max response 12K because our decisions are shorter than their 28K budget [estimate]; steps 100-150 at batch 32 x G 8 = 25,600-38,400 rollouts [estimate]. Rollout tokens about 5-8K -> 130-300M tokens; on one 96 GB card with an 8B model at about 3-5K tokens/s [estimate] that is roughly 10-25 hours of sampling plus training time -> **about 30-60 GPU-hours total [estimate]**. Paper's own cost: not stated; 57,344 rollouts on 8 x H100.
Why a smaller model is plausible: the paper's whole result is on 7B; Search-R1 [snippet] shows bigger gains at 7B than 3B but no 27B comparison. No source here tests model size for temporal legal search, so the small variant is an engineering bet, not evidence-based. Keep the 27B SFT+EI model as the product candidate and the small model as the RL experiment; compare both on MezonBench.

Stage 4: eval (B5), then freeze.

### B5. MezonBench v1 (modelled on the paper's evaluation and on 2605.23497 / FiscalQA Pro)

Principles copied: fixed tasks with deterministic scoring where possible (FiscalQA Pro: no LLM judge for the core metric; LegalSearch-R1 LAR: exact-text metric); with/without tools arms; temporal behaviour metric; paired or flip items (2605.23497 duplicate-pair idea); frontier baselines.
Fixes the paper skipped: time split, contamination handling, seeds, confidence intervals.

Splits:
- **Time split by decision date**: train on decisions adopted before T1, dev T1-T2, test after T2. Choose T2 later than the base model's training cutoff as far as known (Qwen3.8 cutoff: not known to me, check the model card), so that the cancelling acts are unseen.
- **Edition hold-out**: for F1/F2, hold out whole acts (not just dates) so the model cannot memorise articles.
- Natural temporal traps from our own findings (use as dev/test seeds, verify each on lex.uz first): Law on Local State Power art. 25 lost force on 19.10.2024 but is still cited in 2025 (68 decisions per our notes); the Law on Local State Power amended 12.11.2026; PF-6243 clause 4 "bekor qilish" left the list on 01.05.2026.
- Contamination: dedupe by registration number and by `textnorm.similarity` >= 0.9 between train and test decisions; keep the three golden cases (Qarshi, Yangiyo'l, Xatirchi) out of training; log the verifier version.

Tracks and metrics:
| Track | N (test) | Metric |
|---|---|---|
| T1 Recite-as-of | 300 | exact-after-normalisation quote correctness (verifier); also ROUGE-L like the paper |
| T2 Flip pairs | 150 pairs | pair accuracy: both dates right; and recency-bias rate = share of pairs answered with the newer edition for the older date (the failure TALD-Bench and 2605.23497 describe) |
| T3 Citation audit | about 200 | precision/recall of "this cited article was not in force on D" |
| T4 Full audit | as many as exist | recall on cancelled-with-text positives (print N; small), precision on lawyer-reviewed flags (>= 50 per project plan), citation validity (must be 100% by construction), minutes saved (5 decisions) |
Temporal-consistency metrics (report both):
- TC-strict = share of defects whose (act, article, edition) is the one in force on D and whose quote is verbatim in it. Required result for shipped output is 100% after the validator; the *raw model* number before the validator is the interesting one.
- TC-behaviour (the paper's proxy) = share of law tool calls that carry the decision date D, and mean number of date-bearing queries per episode.

Arms: (1) no tools (closed-book), (2) tools with the base Qwen3.8-27B, (3) + SFT, (4) + expert iteration, (5) small RL model, (6) frontier models, with and without tools.
Frontier baselines: **only on public data and only the T1/T2 national-law items** (public statute text, no hokim decision text, nothing from our labels or reviews) so the project rule "decision text never goes to a cloud API" is not touched. Boss approves the list. Names as the paper does: DeepSeek-V3.2, a reasoning model, GPT-class and Claude-class (exact versions: choose on the day).
Statistics: report Wilson 95% intervals for every proportion; paired bootstrap (10,000 resamples) for model-vs-model differences on the same items; at p = 0.5 a Wilson interval is about plus or minus 9.8 points at N = 100, 5.6 at N = 300, 4.0 at N = 600 (my arithmetic). So T4 with a few dozen positives can only show large effects; say so, never report accuracy on the small bad class. Run 3 seeds for any sampled (temperature > 0) arm; the paper reports one greedy run and no intervals.
Honesty line for the pitch: "in our test of N items" always; the paper's headline numbers are Chinese law in a different setting and must not be quoted as ours.

### B6. Before Sat 21 Nov 10:00 versus after

Context: today is Fri 20 Nov, the build starts after the 12:30 registration; feature freeze is Sat 10:00; deadline 17:55. There are about 20 hours to the freeze, and nobody should expect a trained model by then.

Before the freeze (priority order):
1. Tool wrappers over the store + verifier, with date mandatory (3-4 h). Test on the golden three.
2. Reward function + its unit tests, especially the reward-hacking checks in B3 (2 h). Even without training, this is the same code the product validator uses.
3. Prompted agent loop with Qwen3.8-27B + tools, no training (2-3 h). This is what the demo can actually show: temporal retrieval + verified quotes + the validator dropping bad flags.
4. MezonBench seed: generate T1/T2 items from the store (mechanical, 1-2 h), run arms (1) and (2), report TC-strict and TC-behaviour with CIs. A one-slide result: "closed-book vs with date-aware tools".
5. Start trace generation for SFT in the background (verifier-filtered), if Boss approves GPU share. Stop at about 1,000 traces if time is short.
6. Optionally launch a short LoRA SFT overnight (about 3-5 h [estimate]) only if the chat model coexistence is cleared; evaluate on dev in the morning; ship the adapter only if it beats arm (2) on T1/T2 with non-overlapping intervals.
After the freeze: finish the SFT set to 2-4K, expert-iteration rounds, small-model GRPO experiment, lawyer-reviewed T4 growth, the time-split final test, frontier public-data baselines, then write `eval/report.md` only from printed numbers.
Do not claim in the pitch: any RL-trained model, any "Nx" gain, or any paper number as ours.

### B7. Risks and how the paper handled them

| Risk | What the paper did | What we do |
|---|---|---|
| Reward hacking | not discussed | Deterministic verifier, minimum quote length, quote must come from fetched text, penalty ordering, unit tests for each hack (B3) |
| Lazy abstention | no abstention task | Three-level unclear, abstention-rate guard, 25% trigger [estimate] |
| Data contamination | not stated | Time split after model cutoff, act hold-out, similarity dedupe |
| Label noise (survivors are not "lawful"; cancelled is often individual-decision) | not applicable | No "positive" reward from survival; verified-flag credit; recall reported only on positives with text, with N |
| Tiny test sets | 128 per task; no CIs | Wilson + paired bootstrap; synthetic T1/T2 give N in the hundreds |
| Behaviour proxy for temporal consistency (query count) can be gamed by adding years to queries | accepted as is | TC-strict is checked on the cited edition and quote |
| Over-trust in one run | one greedy rollout | 3 seeds on sampled arms |
| Tool output length blows the context | max context 32,767 | caps per tool result, 16K training context |
| Statutes-only limitation | stated | we also have decisions; the corpus is not curated, so recall of `search_law` is the likely bottleneck (FiscalQA Pro oracle-article result 99.1% vs end-to-end 98.3% suggests retrieval recall, not version choice, is the remaining gap) |
| GPU shared, 27B does not fit rollout + train | 8 x H100 | expert iteration instead of online RL on 27B; small model for online GRPO; ask Boss before GPU use; never run `qwen off`/`qwen switch` |
| License | Apache-2.0 code | Qwen weights Apache-2.0 (per your note); paper's data licence unknown, do not copy their data; their repo is a reference for config, not a dependency |
| Legal claims | n/a | Output wording stays "possible violation, flagged for expert review"; a human decides every flag |

### Sources
- LegalSearch-R1: https://arxiv.org/abs/2605.25920 , https://arxiv.org/html/2605.25920 , https://github.com/HKUST-KnowComp/LegalSearch-R1
- Asking For An Old Friend: https://arxiv.org/html/2605.23497
- TALD-Bench: https://arxiv.org/abs/2608.14610 [snippet]
- Temporal Misgrounding / FiscalQA Pro: https://arxiv.org/abs/2608.09393 [snippet]
- LexKairos https://arxiv.org/pdf/2608.09106 [snippet]; CALRK-Bench https://arxiv.org/abs/2603.26332 [snippet]
- Search-R1 https://arxiv.org/abs/2503.09516 ; ReSearch https://arxiv.org/abs/2503.19470 ; R1-Searcher https://arxiv.org/abs/2503.05592 ; DAPO https://arxiv.org/abs/2503.14476 ; Dr. GRPO https://arxiv.org/abs/2503.20783 (all abstract-level [snippet])
