# Two small pilots on one RTX PRO 6000: "internship" (tool-use SFT) and "strict judge" (verifiable-reward training)

Design only, 21 Nov 2026. Nothing was run on a GPU and no code was changed. I read the repo files named in the brief and
ran small read-only Python counts on the law store, the decision store and the CSVs.

**Tags:** [ours] measured or counted in this repo today · [full] source read in full · [abstract] abstract page only ·
[recalled] from memory, re-read before quoting · [derived] arithmetic from [ours]/[full] numbers · [estimate] my guess,
to be replaced by a measurement in hour 0.

---

## 0. What the repo says, in the numbers that decide the design

| Fact | Value | Why it matters |
|---|---|---|
| MezonBench exam | 400 items: lookup 120, flip 120, in_force 120, hierarchy 40; 350 distinct (act, path) articles [ours] | The training pools must avoid these 350 articles |
| Base, closed book, no thinking | 101/400 right, 238 "noaniq"; lookup 0 right / 118 abstain, flip 25 / 30 wrong / 65 abstain, in_force 42 / 24 wrong / 54 abstain, hierarchy 34 / 5 wrong / 1 abstain [ours, `preds_base.jsonl`] | Lookup has zero signal closed-book. Flip and in_force have both right and wrong answers: usable for RL |
| Base with thinking (same 100 items) | 27 right / 4 wrong / 69 abstain vs 38 / 13 / 49 without thinking [ours, proof README] | Thinking made it more careful, not more knowledgeable. Closed-book pilot B stays in non-thinking mode |
| Speed, HF `generate`, batch 1 | 0.2 s per item without thinking (400 items = 90 s); 54.6 s per item with thinking (100 items = 91 min), about 2,580 characters each [ours, `preds_base*.jsonl` seconds] | About 15 tokens/s per sequence [derived]. Anything multi-turn or thinking needs vLLM or a batched sampler, or a 400-item exam takes hours |
| Law store | 38 acts; 12,208 distinct (act, path) articles of at least 80 characters; 3,704 of them with several editions; 5,312 consecutive-edition pairs whose text differs [ours] | Fresh pool outside the exam: 11,858 articles and 4,923 flip pairs [ours]. Plenty |
| Hierarchy | 38 acts give only 513 act pairs of different legal force; 40 are in the exam [ours] | The pool is small and the base already gets 34/40. Retention anchor only, not a headline |
| Law-school pilot throughput | 7,165,012 trained tokens in "~3 h" at LoRA r128 [ours, proof README] = about 660 tokens/s [derived] | Budget for A and B training: tokens / 660 |
| Memory | bf16 LoRA r128 at 2,048 tokens used 76.7 GB (brief). Weights alone are 55.6 GB (playbook) | No room for a second 54 GB copy on the card (matters for GRPO, section 3) |
| Real positives with original text | `positive_originals.csv`: 35 rows, **only 15 resolved, 11 unique** (4 are duplicated rows); all 15 are adliya representations; 6 of the 11 are Cyrillic [ours] | The "~35 positive cases" are ~11 usable ones today. See section 1.6 |
| Real positives, template clusters | 4 of the 11 are the same "ish o'rinlarini band qilish" job-quota template (222-10-136, 362-2-31, 161-14-207, 109-5-75) [ours]; Qarshi 461-4-59-Q/24 (in `sft.jsonl`) is the same template again | Split by template cluster, never by single decision, or dev leaks into train |
| Real positives, length | median about 15,000 characters; 2 of 11 are 6,000 characters or less [ours] | They do not fit a 3,072-token training window without cutting |
| Decision store | 1,985 decisions, 1,248 with text over 500 characters; median 4,458 characters; 780 are 6,000 characters or less [ours] | Audit-style traces come from here (rule engine as the silver teacher), not from the 11 real cases |
| Golden cases | Qarshi 231-4-59-Q/24 and Xatirchi VII-3-1-5-77-K/25 are among the 11; Yangiyo'l VI-76-4-10-146-K/24 is **not resolved** (no original text) | Golden set is held out by registration number and by near-duplicate cluster |

Two corrections to the brief's premise that I want on the table before anyone plans around them:
1. About 11 real positive cases with text exist, not 35. Real-case SFT therefore cannot teach "find the defect"; it can only
   serve as a small dev smoke test. The statistical teacher for audits is the rule engine on the 1,248 crawled decisions.
2. The exam is closed-book as written. Tool use is a different measurement ("tools-on") that must be run on the same 400
   items; both modes are reported for every adapter.

---

## 1. Pilot A: the internship (SFT on tool-use traces)

### 1.1 Claim to prove

"After a small amount of tool-use SFT, the model answers date-dependent law questions by calling the tools, quotes only
what the tools returned, abstains when the store has nothing, and keeps its general abilities."
It is **not** a claim about auditing skill (N too small, section 1.6).

Qwen models already call tools natively, so the honest comparison is **the law-school adapter with the same tools given in
the prompt (call it L0-tools)** versus **adapter A with the same prompt**. If L0-tools already scores high, A is not needed
and we say so. After CPT on raw text plus lessons, tool-call ability may have degraded; hour 0 measures that too.

### 1.2 Message format (exact)

Render every example with the local `tok.apply_chat_template(messages, tools=TOOLS, ...)` from the model's own
`chat_template.jinja`; never concatenate strings by hand. The playbook's serving note says Qwen3.8 uses the `qwen3_coder`
tool parser, which means XML-style calls, not JSON [playbook; verify against the local template in hour 0]. Expected shape
(illustrative values, not store facts; `<...>` are placeholders):

```
<|im_start|>system
# Tools
You have access to the following functions: <tools> {law_as_of, list_editions, search_law, get_decision, verify_quote} </tools>
...call format instructions from the template...

Siz O'zbekiston qonunchiligi bo'yicha ekspertsiz. Qonunni ko'rsatilgan sanadagi tahriri bo'yicha javob bering.
Bilmasangiz yoki asos topilmasa, "noaniq" deb yozing.<|im_end|>
<|im_start|>user
«<act title>» (<kind>, <number>) <N>-modda <YYYY-MM-DD> kuni amalda bo'lganmi? Faqat "ha" yoki "yo'q" deb javob bering.<|im_end|>
<|im_start|>assistant
<think>
Savol sana va modda raqamiga bog'liq. Avval <date> dagi tahrirni olaman.
</think>

<tool_call>
<function=law_as_of>
<parameter=act>
<number>
</parameter>
<parameter=article>
<N>
</parameter>
<parameter=date>
<YYYY-MM-DD>
</parameter>
</function>
</tool_call><|im_end|>
<|im_start|>user
<tool_response>
{"error": "art:<N> not found in <act> as on <date>", "act_key": "...", "edition": "..."}
</tool_response><|im_end|>
<|im_start|>assistant
<think>
Bu sanadagi tahrirda modda yo'q. Moddaning qo'shilgan sanasini tekshiraman.
</think>

<tool_call>
<function=list_editions> ... </function>
</tool_call><|im_end|>
<|im_start|>user
<tool_response>{"editions": ["...", "..."], ...}</tool_response><|im_end|>
<|im_start|>assistant
<think>
Modda keyingi tahrirda paydo bo'lgan; savol sanasi undan oldin. Javob: yo'q.
</think>

yo'q<|im_end|>
```

Rules for the format:
- **Thinking stays on**, with short thinks (one to three sentences, 15-60 words) before each call and before the answer. The
  first think states the task and the plan with no answer in it; the second reads the tool result (dates, edition, error)
  and decides. Qwen3-style templates keep the reasoning of assistant turns after the last user query, so the multi-step
  loop is consistent [recalled; the round-trip test below confirms]. Final answer obeys the exam's own instruction
  ("Faqat A yoki B", "ha / yo'q", quote at least 60 characters).
- **Loss mask:** train on every assistant span (think, tool call, final answer, `<|im_end|>`) and on nothing else. System,
  user and `<tool_response>` tokens get label -100. Search-R1 masks retrieved tokens for the same reason: the model must not
  learn to write tool output [abstract; the mechanism itself is not explained there]. `train_sft.encode()` masks everything
  before the last assistant header, so it needs a multi-span version (new function, not a change to the old one).
- **Round-trip test before any GPU time** (CPU): render 20 examples, check the count of `<tool_call>` and `</tool_call>`
  matches, that parsing the tool call back yields the exact arguments, that exactly the assistant spans are unmasked, and
  that no example exceeds 3,072 tokens. Reject the build if one check fails.
- `max_len` 3,072. The tools schema in the system prompt is about 700-1,000 tokens [estimate] and is paid in every example.
  Tool responses are truncated at 1,500 characters in training traces (the tool itself caps at 4,000), audit decisions at
  6,000 characters like run 1. Memory at 3,072 is not measured (76.7 GB was at 2,048): if the first 5 steps exceed 90 GB,
  drop to `max_len` 2,560 or r64.

### 1.3 How the traces are built without a cloud model

**Tier 1 (default, deterministic, CPU only, can be built while the GPU is busy): the tools are the teacher.** A solver
program takes a question from the generator and emits the ideal call sequence by actually running `mezon.tools.call` on the
law store; the think text is filled from the tool results with 8 or more phrasings per step type. No model is involved, so
every quote is correct by construction.

| Family | Ideal trace | Final answer |
|---|---|---|
| lookup | `law_as_of(act, article, date)`; 50 % also `verify_quote` on the span it will cite | verbatim span of 60 to 250 characters from `text` |
| flip | `law_as_of(act, article, date)`; compare which given variant matches `text` | A or B |
| in_force | `law_as_of`; if error "not found" or "did not exist": `list_editions` to confirm | ha / yo'q |
| hierarchy | half with no tool (the rule is NLA art. 6, in the weights); half with `search_law` on the NLA | A or B |
| recovery | first call has a wrong act spelling or article form (a realistic slip) and the error comes back; the retry uses `search_law` or `list_editions` | the right answer |
| discovery | question names a topic and a date, not an act: `search_law(query, date)` then `law_as_of` on the hit | one sentence plus a verified quote |
| abstain | the date falls in a store edition gap (`law.edition_gap`), or after 2026-11-20, or the act is not in the store: tool says so | "noaniq" plus one clause saying why |
| audit | `get_decision(reg)`; then per cited act and article `law_as_of` at the decision date; then `verify_quote` for every flag; the verdict and flags come from `mezon.rules.run.audit(use_llm=False)` | Adliya format: positive / positive with fixable defects / negative, each defect with article and quote, or "unclear, needs expert" |

For audit traces the existing `mezon.agent.run` produces steps named `decision_text`, `rules`, `basis`, `law`, `verify_quote`;
the trace builder maps them to the five public tools (`get_decision`, `law_as_of`, `list_editions`, `verify_quote`) and
drops the internal `rules` step. The model must reach the verdict by reading, so the rule engine's output is **not** put in
a tool response. It appears only as the target text of the final answer. Hence the audit slice teaches the Adliya answer
format and citation discipline, not defect finding. Check 4 and 5 style open questions are out of scope for the pilot.

**Tier 2 (optional, only if the clock allows): self-generated, filtered by the verifier.** Sample the model itself with
tools on fresh questions (k = 4, temperature 1.0), keep only traces whose final answer the store grades right, whose
quotes `verify_quote` accepts, with 4 calls or fewer and a valid call format; add to the data at no more than 40 %. This is
rejection sampling in ReST-EM's sense (generate, filter with binary feedback, fine-tune; "repeat a few times") [abstract].
It is the better teacher for natural style, but multi-turn thinking sampling is expensive, so it is a second round only.

No cloud model, no decision text leaves the machines.

### 1.4 Size, balance, replay, splits

Total **1,200 examples, about 2.2M training tokens [estimate: 1,200 x ~1,800 tokens], about 55 minutes at 660 tokens/s
[derived], one epoch.** Small on purpose: the goal is to prove a procedure, and format learning needs hundreds, not
thousands (LIMO 817 and s1 1,000 [snippet], from the playbook).

| Slice | Count | Notes |
|---|---:|---|
| lookup | 130 | |
| flip | 130 | A 65 / B 65 (swap order per twin) |
| in_force | 130 | ha 65 / yo'q 65; 25 are error-recovery traces |
| hierarchy | 50 | A 25 / B 25, 25 without tools |
| discovery (search then read) | 80 | |
| abstain ("noaniq") | 70 | at least 3 distinct reasons, none above 40 % of the slice |
| audit (crawl decisions + rule engine) | 250 | verdict mix below |
| **legal subtotal** | **840** | 70 % |
| replay: the model's own thinking answers to general prompts (self-distilled) | 200 | generated in hour 0 on the law-school adapter |
| replay: Tulu 3 style instruction chats | 120 | already downloaded (10,019 chats exist) |
| replay: Uzbek and Russian instruction or QA chats | 40 | |
| **replay subtotal** | **360** | 30 %. Replay of 5-25 % is the range Gupta et al. found useful for CPT [full]; Unsloth says keep at least 75 % of SFT data in reasoning style [full]: here every legal example and the self-distilled third are thinking-style, which gives about 77 % [derived] |

**Answer-balance rules (hard gates, the build fails otherwise):**
1. No final-answer class (family, answer) above **15 %** of the 1,200. By construction the largest is about 5.4 %
   (65 / 1,200), with a large margin.
2. Within every binary family, each class is 45-55 %. Flip is built as twins (the same article and date with A and B
   swapped) so position cannot carry the answer.
3. Free-text answers (lookup quotes): no identical answer string above 2 %; unique prompts 100 %; no two examples share
   an (act, path, date).
4. Audit slice: engine "clean" decisions are downsampled to at most 35 % of the slice; no verdict above 35 %; no identical
   final-answer text above 2 %. Run 1's 672 identical answers out of 917 (73 %) is the failure this gate exists for [ours].
5. Think text: every phrasing template is at most 3 % of its step type.
6. Tool-call count per example: 0 calls at most 15 %, 1 call at most 45 %, 2 or more at least 40 %. This keeps it from
   learning "always call once".

**Splits and leaks (all checked by a script that stops the run):**
- **Exam (400 items) never trains.** The generator receives an exclude set of all 350 exam (act, path) pairs, so train and
  exam are disjoint by article, and therefore by date. Tool responses in a training trace may show exam text only as masked
  context (for example a `search_law` hit); the assertion checks that no exam article is a **target** (a quoted span, a
  graded answer). Simpler and safer: drop any trace whose tool responses contain an exam (act, path).
- **Seen / unseen stays meaningful.** The exam's unseen half was never in the law-school lessons; the seen half was taught
  without the exam question. Nothing in A or B touches either, so a gain is skill, not memory. Report seen and unseen
  separately.
- **Golden cases.** Qarshi 231-4-59-Q/24, Xatirchi VII-3-1-5-77-K/25 and Yangiyo'l VI-76-4-10-146-K/24, plus their
  cancelling acts and every act cited as a cancelled number (207-4-59-Q/24, 161-4-59-Q/23, 261-4-59-Q/24, VII-4-12-5-77-K/25,
  VI-76-21-10-146-K/24), are removed from all data by registration number.
- **Template clusters.** District decisions copy each other (Qarshi 231 copies 207 word for word [CLAUDE.md]). Cluster all
  decisions with `textnorm.similarity` on `split_decision` clauses at 0.90 or more; a whole cluster goes to train or to dev,
  never both. Any cluster touching a golden or dev case goes to dev. Log the number of decisions dropped.
- **Dev (not exam, not golden):** the 6 real positives of the job-quota cluster (4) plus Qarshi and Xatirchi are the dev
  smoke set (golden = 2 of the 6, never used even for early stopping); a further 150 clean crawl decisions form a
  false-alarm control. Train uses the remaining 5 real cases once each, plus crawl audit traces. N for the real cases is
  5 and 6: any statement about them is a count, not a rate.
- **Out-of-distribution phrasing set (new):** 60 exam-style questions written by hand with different templates
  (Russian and Cyrillic wording, different sentence order, article given as a part or clause path), built from non-exam
  articles. This tells "learned the procedure" from "learned the template".

### 1.5 The metric that proves it worked

Primary (one number): **tools-on MezonBench accuracy, adapter A versus the law-school adapter with the same prompt and
tools, same 400 items, paired.** Each item is a Bernoulli outcome, so use the exact McNemar test on discordant pairs and
Wilson 95 % intervals (the exam code already prints N and Wilson). Report right / wrong / abstain, never accuracy alone.

Secondary, all printed by scripts:
- per family and per seen / unseen / recent, with N;
- **citation validity**: every quoted span in every final answer passes `verify_quote` on the date (must be 100 % of those
  answers that quote; any failure is a stop);
- **tool-call validity**: parses, known tool names, required arguments present (at least 98 % [judgment]);
- **tools-on OOD set** (60 items) accuracy vs the in-template exam: a gap above 15 points means template memorising;
- **closed-book control** (the exam without tools): not below L0 by more than the CI and not collapsed: the share of the
  single most common answer string in the 400 predictions must be below 40 % (run 1 was 100 % [ours]) and abstain below 80 %;
- **forgetting:** held-out loss on the law-school pilot's web and instruction sets versus its "before" numbers (web 1.6968,
  instructions 1.7365 [ours]) and versus L0; the free-text test (20 non-audit prompts must not answer with the audit
  JSON, run 1's failure); a 100-prompt general sample graded by length and language sanity, not by a model;
- **audit smoke on dev** (N small): count of dev real positives not given "positive" (clean) and count of control decisions
  given "negative". Reported as counts with the case ids.

### 1.6 Real cases: what they can and cannot do

- **Today 11 unique resolved originals** (15 rows). The 24 unresolved of the 35 labelled positives are unresolved because
  the original number was not found on lex.uz by registration number (e.g. Yangiyo'l), so they are mineable, but the work is
  resolving originals, not writing code. Target before v2: at least 60 resolved positives from all four triggers
  (adliya representation, prosecutor protest, court, adliya letter); today 15 rows are all adliya representation.
- Decision text is long (median ~15,000 characters, only 2 of 11 within 6,000), so real cases need a windowed read
  (`get_decision` returning preamble and clauses in pages) before they can be training examples at all. In the pilot they are
  cut at 6,000 characters and the final answer is the calibrated "positive with fixable defects / unclear, needs expert"
  with the checks that actually fired, never the cancellation reason (the cancelling text names the representation number
  but not the defect [ours: `evidence_snippet`]). Follow the existing wording rule: "flagged a defect consistent with the
  representation".

---

## 2. Pilot B: the strict judge (verifiable reward)

### 2.1 What is judged

The law store grades four families with `research/mezonbench.py grade()`: lookup (verbatim span), flip (A/B), in_force
(ha/yo'q), hierarchy (A/B). **Pilot B is closed-book and non-thinking.** Reasons, all from the numbers above: closed-book
lookup has 0 right of 120, so a group of samples is all-zero and gives no learning signal (GRPO's advantage is zero when
all samples score the same; this is general GRPO behaviour [recalled]); thinking costs 54.6 s per item at batch 1 [ours]
and did not raise the number right (27 vs 38 of 100 [ours]). Lookup is a tools task (pilot A, tools-on). Hierarchy is 5 %
of the mix, a retention anchor. The real training signal is flip and in_force: they have right and wrong answers and a
large abstain share to convert or to keep.

### 2.2 Fresh questions, disjoint from the exam

Reuse `mezonbench.build()` logic with a new seed (not 20261120) and these changes (new module, e.g.
`research/mezonbench_train.py`; the exam builder is untouched):
- exclude every (act, path) in the 350 exam articles (disjoint by article, so disjoint by date);
- skip dates where `law.edition_gap` is not None (same as the exam);
- hierarchy: exclude the 40 exam pairs, both orders (473 pairs remain; the overlap in acts is unavoidable with 38 acts, so
  hierarchy is excluded from the headline);
- every flip item is a **twin pair** (A and B swapped), every in_force item has a second wording ("... edi?" / the same
  question with the answer clause in the other order);
- **unanswerable items (about 12 %)** with gold "noaniq", built from facts the store knows it lacks: a date inside an
  edition gap, or a date after 2026-11-20. The exam has no such items, so the 40-item unanswerable test set (new, article-
  disjoint) is also the **only** measure of warranted abstention, reported on its own.
- the grader is `grade()` plus one line for gold "noaniq": abstain is right, anything else is "wrong confident".

Per round: **3,000 base items** = flip 1,000 (2,000 prompts with twins), in_force 1,000, hierarchy 100, unanswerable 400,
plus 500 extra flip and in_force items held for round 2. The pool allows far more (4,923 flip pairs outside the exam [ours]).

### 2.3 The reward (three levels for "noaniq")

| Outcome | Reward | Reason |
|---|---:|---|
| right (grade = right) | **+1.0** | |
| warranted abstention (gold is "noaniq") | **+0.2** | small positive: honest, but never better than being right |
| lazy abstention (store has the answer, model said "noaniq") | **-0.25** | must lose to a good answer, must beat a wrong one |
| wrong and confident (including any answer to a gold-"noaniq" item) | **-1.5** | the most negative |
| broken format / over length | **-1.0** | worse than a lazy abstain, better than a confident error |

Break-even: for a binary question, answering beats abstaining when `p - 1.5(1-p) > -0.25`, i.e. `p > 0.5`. So the model has
no reason to answer a flip or in_force question at chance level, and answers once it has any edge. This is the designed
behaviour and the numbers are my judgment; adjust only if the abstain rate moves outside the guard bands in 2.6.
For gold-"noaniq" items the break-even is the model's belief that the question is unanswerable. Choi, Leskovec et al. warn
that RL can turn honest abstentions into confident wrong answers [abstract, from the playbook]; the -1.5 and the separate
unanswerable set are the defence.

### 2.4 Option (i): expert iteration (rejection sampling) on the single card

Loop: sample k answers per question, grade, keep the verified-correct, SFT on them, repeat. STaR (generate, keep the ones
that reach the right answer, fine-tune) [recalled]; ReST-EM (the same with binary feedback, repeated a few times, scales
with model size) [abstract]; RAFT (reward-ranked fine-tuning, same family) [recalled]; DeepSeek-R1 used rejection sampling
for its SFT stages [full, per the playbook]. The playbook already put 27B expert iteration at 40-60 GPU-hours for the full
version; this pilot is the 2-4 hour slice.

**Sampling.** vLLM (or the batched fallback in 3.3), non-thinking, temperature 1.0, top_p 0.95, max 24 new tokens for A/B
and ha/yo'q answers [judgment]. The abstain rate of the base is 54 % on flip; to get any correct samples the sampler uses a
**commit system prompt**: the exam's prompt without the sentence "Bilmasangiz ... noaniq deb yozing", so the model must pick.
The kept examples are then trained **under the real prompt** (with the abstain sentence), like STaR's "rationalization"
idea (re-prompt to reach the right answer, train without the hint) [recalled]. This is the step most likely to teach
guessing, so it sits behind the filters below.

**k and the keep rule (adaptive).**
- Screening: k = 8 per item (flip: 4 per twin). Items with 6 or more of 8 right get 8 more.
- **Keep an item only if 15 of 16 right, and for flip at least 6 of 8 on each twin.** A coin-flipper passes 15/16 with
  probability 17/65,536 = 0.03 % [derived]; a screen at 7/8 alone would pass 9/256 = 3.5 % of pure guessers [derived], which
  at a low true-knowledge rate would make a large share of kept data noise.
- A policy that always says "A" is right on gold-A twins and wrong on the swapped ones, so the per-twin rule drops it.
  This is the key protection against run 1's collapse.
- From each kept item take **two** distinct correct samples at most (the sampler gives different texts only for lookup; for
  A/B the answer is one token, so dedupe by prompt: one example per prompt).
- **Relabel to "noaniq"** (Gekhman: relabelling unknown examples "I don't know" kept 61.8 vs 25.8 accuracy [full, from the
  playbook]) only for (a) the constructed unanswerables and (b) twin-inconsistent items: right on one twin, wrong on the
  other, which is guessing by position. Items the model is consistently wrong about get **no** target and are only reported
  (relabelling them abstain would teach "abstain on yo'q questions" if the model is biased to "ha").
- Final kept set: each class (A, B, ha, yo'q, noaniq) at most 35 % of the kept set and at least 15 % (the 15 % rule from A is
  about the whole mix; here the kept set is small, so it is a floor and a ceiling).

**Headroom check (go / no-go before training anything):** after sampling, compute pass@1 and pass@8 on the pool. RL and
expert iteration sharpen what the model can already sometimes do; they do not create facts [recalled, general]. If
pass@8 minus pass@1 is under 10 points on flip and in_force, stop and say "no headroom: knowledge must come from CPT or
tools" (the playbook's own escalation rule for CPT).

**Training per round.** Restart from the law-school adapter L0 each round with the union of all kept data (ReST-EM
fine-tunes from the base each iteration [recalled; the abstract I read does not say, check before quoting]); this avoids
drift over rounds. LoRA continues r128, lr 5e-5, 2 epochs, 30 % replay (self-distilled chats from A's replay set).
Expected kept set 300-1,000 examples of 40-120 tokens each [estimate], under 5 minutes of pure training; model load and the
vLLM swap dominate.

### 2.5 Option (ii): online GRPO with TRL on one 96 GB card for the 27B

What the docs say [full for the pages read, which cover characters 0-100,000 of 116,449 of the GRPO page]:
- `use_vllm=True` with `vllm_mode="colocate"` runs vLLM inside the trainer process and shares the GPU; docs warn of "memory
  contention". `vllm_gpu_memory_utilization` defaults to 0.3 (colocate only). `vllm_enable_sleep_mode` offloads weights and
  cache during the optimizer step.
- `num_generations` default 8; `loss_type` default `"dapo"`; `beta` default 0.0 (no reference model loaded);
  `max_completion_length` default 512; `tools=[...]` and `max_tool_calling_iterations` give multi-turn tool rollouts;
  `environment_factory` is experimental and needs transformers 5.2 or later.
- Supported vLLM versions are 0.23.0 to 0.34.x. In server mode the trainer streams updated weights over NCCL and the doc says
  the server and the trainer must be on separate CUDA devices; for a shared GPU it names the `"ipc"` weight-transfer backend.
- I did **not** find, in the pages read, how LoRA weights reach vLLM (merge each step, or load the adapter), nor any
  statement about a 27B model on one GPU. Both are open [not found].

Feasibility on one 96 GB card [derived from the numbers above]:
1. **Colocate does not fit.** The trainer holds the bf16 weights (55.6 GB) and the LoRA training used 76.7 GB at 2,048
   tokens. vLLM's default share (0.3 x 96 = 28.8 GB) is below its own weights (55.6 GB). A second copy plus KV cache needs
   about 65-70 GB, so the sum is above 140 GB. Sleep mode does not free the trainer's own copy during generation.
2. **Server mode on the same card does not fit either**, for the same two copies.
3. **In-trainer HF generation** (`use_vllm=False`) fits in memory (no second copy). Speed is the problem: 15 tokens/s per
   sequence at batch 1 [ours]. If batching gives 10-20x, 150-300 tokens/s [estimate, unmeasured on this card], so a step of
   32 prompts x 8 = 256 completions of about 50 tokens = 12,800 tokens takes about 1-1.5 min to generate, plus the same
   again to train, about 2-3 min per step [estimate]. 100 steps = 3-5 hours, covering only 3,200 prompts. LegalSearch-R1
   needed 112 steps at batch 64 with 8 rollouts on 8 x H100 [full, per the recipe file]; we would get the same step count
   at half the batch in about the whole budget, with no room for a second try.
4. **A vLLM on the L40S (48 GB) as a generation server** would need a quantised copy (FP8 about 28 GB) and the L40S runs the
   crawl, OCR and demo (CLAUDE.md, playbook). Then the sampler policy is not the trainer policy (FP8 vs bf16), which hurts
   on-policy GRPO but not rejection sampling (only verified-correct samples are kept, then trained in bf16).
5. Reward-hacking arrives fast in RL: Anthropic's hack rate rose from about 0 to 0.8-1.0 in about 100 steps [full, playbook].
   With expert iteration we read the kept samples before any weights change; in online GRPO we cannot.

### 2.6 Recommendation for the 2-4 h pilot: **(i) expert iteration, two rounds**

Why, in one paragraph: it fits the card (sample and train in separate phases, 54 GB at a time), vLLM sampling is the speed
fix and the policy mismatch it might bring costs nothing here, every kept sample can be read and gated before training
(the twin rule is the anti-collapse step), and a failed round costs 45 minutes, not a whole run. Online GRPO stays the v2
plan for the **Qwen3.5-9B sibling** (the playbook's testbed; two bf16 copies are about 36 GB and fit colocated) after
this pilot shows there is headroom and the reward is not hacked.

| Setting | Value |
|---|---|
| Questions per round | 3,000 base items (section 2.2), 500 more in round 2 |
| k | 8, adaptive to 16 on items at 6/8 or better |
| Temperature, top_p | 1.0, 0.95 [judgment] |
| Rounds | 2 (a third only if round 2 still improves) |
| Policy | non-thinking, short answers, the exam's own prompts |
| Reward in selection | section 2.3, used for the logs and for the choice of what to keep; no gradient through it |
| Train | L0 + union of kept data, r128, lr 5e-5, 2 epochs, 30 % replay |

**Before / after measurement (all on the same code path as the exam):**
- MezonBench closed-book no-think, adapter vs L0: per family, **seen vs unseen**, right / wrong / abstain, Wilson 95 %,
  McNemar on pairs. What each pattern means: a gain on seen only is knowledge recall of the law-school lessons being
  unlocked; a fall in wrong-confident with right flat on unseen is calibration skill, which is the claim for B.
- Selective metrics: coverage (answered share), selective accuracy (right / answered), wrong-confident rate, and the mean
  reward under section 2.3 on the 400.
- Unanswerable test (40 items): warranted-abstain rate.
- Class collapse guards: share of "A" among flip answers (must stay 40-60 %), share of "ha" among in_force answers
  (40-60 %), share of the most common answer string over all 400 below 40 %.
- Forgetting: the same checks as A (held-out loss on web and instruction sets, 20 free-text prompts, tool-call format test
  on 20 items because B's training pushes toward short answers and could erase tool calls).
- Report pass@1 and pass@8 on the training pool at round 0 and round 1 (headroom).

---

## 3. Serving and sampling plumbing (shared by A and B)

1. **Sampler.** vLLM on the 6000 with the law-school adapter. Needs the cu130 build, `--max-lora-rank 128`, tool parser
   `qwen3_coder`, and `--mamba-cache-mode align` only if prefix caching is wanted (experimental) [playbook serving notes,
   from the old box; unverified on this card]. Smoke test with 10 prompts before anything else. vLLM and training cannot
   share the card (two copies of the weights), so the day runs in phases: serve, stop, train, serve.
2. **Fallback if vLLM will not serve the Qwen3_5 hybrid with LoRA:** merge the adapter into a bf16 copy for serving (about
   5-10 minutes and 55 GB of disk, [estimate]); if vLLM will not load the model at all, a batched HF sampler (batch 32-64,
   left padding; the KV cache is small because only 16 of 64 layers are full attention [playbook]). Budget in that case:
   B sampling drops from 3,000 items to 1,000 and the tools-on exam is scored on a fixed 200-item subset.
3. **Throughput guess** to be replaced in hour 0 by a 5-minute measurement: bf16 decoding is memory-bound; 55.6 GB read per
   token step at roughly 1.8 TB/s [hardware number, not verified here] gives a ceiling near 30 steps/s; at 64 concurrent
   sequences and 40 % efficiency about 800 tokens/s [estimate]. Everything in the runbook scales from that number.

---

## 4. Hour-by-hour runbook (one RTX PRO 6000, about 6 hours)

Both adapters **fork from the same law-school adapter L0**, so each stage is measured alone and the order of A and B can be
swapped if one fails. Composing them (A then B, or an adapter-scale test at 0.3 / 0.5 / 0.7 / 1.0 as the recipe proposes) is
a v2 step, only if there is time at the end.

**Before the clock (CPU only, can run while the law-school run finishes):** build A's 840 legal examples (Tier 1), build the
B pool, the 60-item OOD set, the 40 unanswerables, the dev sets; run the leak and balance gates; run the template round-trip
test on a CPU tokenizer. Back up L0 to R2 only with Boss's yes (never overwrite).

| Time | GPU is doing | CPU / me |
|---|---|---|
| **0:00-0:30** | Law-school result check: its own gate (law loss down, web and instruction loss not up). If the gate failed, both pilots fork from the base model instead and the report says so. Start vLLM with L0, 10-prompt smoke test, 5-minute throughput measurement. | Confirm template round-trip with the real tokenizer; freeze data files by hash |
| **0:30-1:15** | **Baselines on L0:** closed-book exam (400, about 2-5 min); tools-on exam (400, about 15-20 min [estimate]); OOD 60; unanswerable 40; forgetting set; generate the 200 self-distilled replay answers for A (10 min) | Score; this is the "before" |
| **1:15-1:45** | **B round-1 sampling** on the same server: 3,000 items x k = 8 with commit prompt, adaptive second pass (about 20-30 min [estimate]) | Compute pass@1 / pass@8: **headroom check**; apply keep rules; read 50 kept and 50 rejected samples by eye |
| **1:45-1:55** | Stop vLLM | A final build (add replay); balance gates; B kept set |
| **1:55-3:00** | **A training** (about 2.2M tokens, about 55 min at 660 tok/s, plus load) with val loss every 25 steps and a checkpoint every 30 min. Kill if the first 5 steps exceed 90 GB or loss goes under 0.01 before step 20 (collapse sign) | Watch; nothing else |
| **3:00-3:50** | **A eval:** start vLLM with A (5 min); tools-on exam, closed-book exam, OOD, dev audit smoke, forgetting set | Score A vs L0, paired; **decide A: go / no-go** |
| **3:50-4:20** | **B round-1 training** from L0 on kept set + replay (5-10 min train plus load) | |
| **4:20-5:05** | **B round-1 eval** (closed-book exam, unanswerables, forgetting, tool format) about 15 min; then **round-2 sampling** on B1 with the 500 extra items plus a re-screen of the failures, about 25 min | Score; read samples; decide whether round 2 is allowed (guards green) |
| **5:05-5:35** | **B round-2 training** from L0 on the union (kept1 + kept2) | |
| **5:35-5:55** | **B round-2 eval** (same set) | Final tables |
| **5:55-6:00** | Stop everything; copy adapters, logs, predictions off the card | Write the result file in `docs/proof/` style: every number from a script |

**Slack rules:** if anything runs over by 20 minutes, drop B round 2 (it is the last 55 minutes). If vLLM fails to serve,
apply the fallback in section 3 and drop the tools-on exam to 200 items and B sampling to 1,000 items. A is never cut,
because B depends on nothing in A and A is the claim most at risk of being unnecessary.

---

## 5. Go / no-go for scaling to v2

All thresholds are my judgment, set so a result is decided before looking at it; change them only now, not after.

**A (internship) goes to v2 only if all hold:**
1. Tools-on exam accuracy of A is at least **80 %** [judgment], at least **15 points above L0-tools** with exact McNemar
   p below 0.01 on the 400 paired items, and wrong-confident at most 8 %.
2. Lookup tools-on at least 70 % (it is 0/120 closed-book [ours]).
3. Citation validity 100 % on all quoting answers (exam, audit smoke); tool-call validity at least 98 %.
4. OOD phrasing accuracy within 15 points of the in-template exam.
5. Closed-book control not worse than L0 beyond the CI; top answer share below 40 %; free-text test 20/20.
6. Held-out web and instruction loss each within +5 % of L0 (relative) [judgment].
If L0-tools already meets 1-3 with margin (within 5 points of A), **skip A at scale** and spend the time on data
(resolving originals) instead.

**B (strict judge) goes to a larger run (the 9B online GRPO, then the 27B expert iteration) only if all hold:**
1. Headroom: pass@8 minus pass@1 at least 10 points on flip and in_force at round 0.
2. After the final round, on the 400 exam: wrong-confident falls by at least 30 % relative to L0 **and** the number right
   does not fall; selective accuracy up at least 5 points; McNemar on right/wrong pairs favours B.
3. Warranted-abstain on the unanswerable test at least 70 %; lazy-abstain on answerable items not above L0 + 10 points.
4. Unseen half shows the same direction as the seen half (if only the seen half improves, call it recall of taught law, not
   calibration, and do not scale RL for that claim).
5. Collapse guards green (A-share 40-60 %, ha-share 40-60 %, top answer string below 40 %); forgetting as in A.
6. Reading 100 random kept samples finds no systematic shortcut (always the older edition, always the longer text,
   always "A" on the first twin).

**v2 prerequisite either way:** at least 60 resolved real positives across the four triggers, with originals; a windowed
decision reader; the audit family on MezonBench with lawyer-graded gold (not rule-engine silver).

---

## 6. Main risks and mitigations

| Risk | Likelihood / damage | Mitigation |
|---|---|---|
| Template memorising: A scores high on exam-style prompts only | High. The exam and the training questions come from one generator | OOD set of 60 hand-written items; 8+ phrasings per template; report the gap; article-disjoint split |
| Another collapse (run 1: 0/400 with one answer) | Medium. The shape was the same: few classes, narrow format | Balance gates (15 % class cap, 2 % string cap, 3 % think-template cap); top-answer-share metric; loss alarm at under 0.01 before step 20; the closed-book control run |
| Real-case set too small to say anything (11 unique; golden and cluster removed leaves 5 train, 6 dev) | Certain | Counts only, never rates; v2 prerequisite of 60; no claim about audit skill from the pilot |
| Dev leakage through copied district templates | High if split by decision | Cluster split at similarity 0.90; golden cluster to dev; log drops |
| Expert iteration teaches guessing (commit prompt) | Medium | 15/16 rule plus twin rule (chance pass 0.03 %); unanswerable items and relabel; abstain and class-share guards; exam as the only judge |
| No headroom: the closed-book model simply does not know the dates | Medium to high for unseen articles | Headroom gate before training; the honest result "knowledge must come from CPT or tools" is a valid outcome and is what the playbook predicts |
| vLLM does not serve Qwen3_5 hybrid with LoRA r128 on this card | Medium. Unverified here | 10-prompt smoke test at 0:20; merge-and-serve fallback; batched HF fallback with reduced sets |
| Memory at 3,072 tokens above 96 GB | Medium. Only 2,048 measured | Check at step 5; fall back to 2,560 or r64; truncate tool responses |
| Loss mask wrong on multi-turn tool traces (training on tool output, or on nothing) | Medium. The old `encode()` is single-turn | New multi-span encoder; unit test on 20 rendered examples before GPU time; mask check printed at train start |
| Tool-call format differs from the guess (JSON vs XML) | Medium | Render only through the local chat template; round-trip test; no hand-written examples in the data |
| Thinking-mode multi-turn rollouts too slow | High if HF | Short thinks (15-60 words), caps at 6 turns, vLLM; B stays non-thinking |
| Benchmark gaming: the exam is the same family as the reward | Medium | Exam never trained, article-disjoint; separate unanswerable and OOD sets; report B's gains by seen and unseen; no claim of "beats model X" from this pilot |
| Time: 6 hours is tight | High | Fixed cut order: B round 2 first, then the OOD and forgetting extras, never the baselines and never A |
| Reward hacking on the abstain rate (abstain-heavy model looks safe) | Medium | Abstain is its own column everywhere; selective accuracy and mean reward reported; lazy-abstain on answerable items has a go/no-go line |
| The commit prompt inflates numbers because the sampling prompt differs from the exam prompt | Low to medium | Evaluation always uses the exam's real prompt; train data always uses the real prompt |

---

## 7. What I could not verify (so nobody quotes it)

- How TRL moves LoRA weights into vLLM, and any 27B-on-one-GPU report: not in the GRPO and vLLM pages I read (the GRPO
  page was read to character 100,000 of 116,449).
- vLLM support for the Qwen3_5 hybrid layers with LoRA on this machine; the exact Qwen3.8 tool-call template (the shape in
  1.2 is the Qwen3-coder style from the playbook, not read from the local `chat_template.jinja`).
- Real batched tokens per second on this card (all rollout times above are [estimate] from the measured 15 tokens/s at
  batch 1 and a bandwidth argument).
- ReST-EM's per-iteration restart rule, STaR's rationalization details, RAFT: [recalled]; only the ReST-EM and Search-R1
  abstracts were read today. Re-read before quoting. DeepSeek-R1 and LegalSearch-R1 figures are taken from the playbook
  and recipe files, which tag them [full] and [read through a summariser] respectively.
- Whether the 24 unresolved positives can be resolved on lex.uz at all (some may be scan-only or Cyrillic-only).

**Sources:** TRL GRPO trainer docs and vLLM integration page (huggingface.co/docs/trl/main/en/grpo_trainer and
.../vllm_integration, read 21 Nov 2026); ReST-EM (arXiv 2312.06585, abstract); Search-R1 (arXiv 2503.09516, abstract);
STaR, RAFT, DeepSeek-R1, Gekhman, Gupta, Biderman, Unsloth Qwen3.5 guide, LegalSearch-R1 as summarised in
`D:\10_projects\mezon\docs\research\00_PLAYBOOK_mezon_lm.md` and `law_school_recipe.md`.
