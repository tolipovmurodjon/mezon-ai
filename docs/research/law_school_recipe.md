# Law-school recipe for a Qwen 27B Uzbek-law model (research, 20 Nov 2026)

Public sources only. No Mezon data was sent anywhere. The one local measurement (tokenizer) ran on this laptop.

Tags: **[full]** = I read the paper or page text for that claim (targeted sections, not every page); **[abstract]** = abstract page only; **[snippet]** = search-result summary only; **[derived]** = my arithmetic from tagged numbers; **[estimate]** / **[judgment]** = mine, not from a source. "not found" = I looked and the source did not say.

Naming caveat: the model cards I found call this model **Qwen3.5-27B** (64 layers, Gated DeltaNet + gated attention, 262,144 default context, Apache-2.0 per listings) [snippet]. The brief says "Qwen3.8". I treat them as the same model. Whether a separate pure-base checkpoint exists was not verified; check before CPT (CPT on a post-trained thinking model is a different, riskier job than CPT on a base).

## 0. Where we start (our own numbers)

- First LoRA SFT: 917 answers, 672 identical, one JSON shape for every question: 0/400 on our exam. Base: 25% (hierarchy 85%, in_force 35%, flip 21%, lookup 0%).
- Closed-book check, 25 items per family (coordinator, 20 Nov): base without thinking 38/100 right (13 wrong, 49 "unclear"); with thinking 27/100 right (4 wrong, 69 "unclear"). Thinking took hierarchy 21/25 to 25/25 but made the model abstain more on in_force and flip.
- Reading of this: the model already reasons about hierarchy; what it lacks is **facts** (lookup 0%, in_force 35%) and **calibration** (it says "unclear" instead of retrieving or committing). The 25% and 38% base figures differ (different harness or scoring of "unclear"); reconcile before comparing stages. [judgment]
- Tokenizer, measured locally with the Qwen3.5-27B tokenizer.json on 22 Uzbek-Latin decision texts from our cache (16,085 words): **4.03 tokens per word**; 1 Russian text (1,219 words): 4.44. Sample is tiny and legal-register; re-measure on 500+ docs per script before budgeting. Uzbek Cyrillic: no sample in the cache (0 docs).

## 1. Domain CPT / mid-training: what experts did

| Model | Base | Tokens and mix | LR / schedule / epochs | Full or LoRA | Gain and forgetting |
|---|---|---|---|---|---|
| SaulLM-7B [full] | Mistral-7B | >30B legal tokens (after dedup, from larger crawl); replay ~2% (Wikipedia, StackExchange, GitHub from SlimPajama) plus Super-NaturalInstructions and FLAN put into the pretraining mix | LR not found in text I read; 256 MI250 for CPT, DeepSpeed ZeRO-3 | full | SaulLM-7B-Instruct LegalBench-Instruct avg 0.61, +11% relative over best open 7B instruct; Legal-MMLU +5 points abs. DPO underperformed SFT. |
| SaulLM-54B / 141B [full] | Mixtral | 500B tokens before cleaning (400B legal web, 30B other, rest small collections; total table 520B); replay ~2% general + 5% math; annealing on high-quality legal instruction data (LawInstruct commercial part) | CPT LR 2e-5, AdamW; IFT 1 epoch LR 1e-5; DPO 1e-6; dedup similarity threshold 0.5; perplexity filter (KenLM) at normalized ppl 1500; NFKC normalisation; >160,000 MI250-hours total project | full | They report repeated synthetic IFT data hurt; math 5% kept reasoning. Forgetting numbers: not extracted. |
| Meditron-70B [full] | Llama-2 | 48.1B-token GAP-Replay: guidelines + PubMed + PMC + replay 1% of corpus (420M tokens of RedPajama) | peak LR 1.5e-4 (70B) and 3e-4 (7B/13B), 2000 warmup steps, cosine to 10%, global batch 512, ctx 4096; 128 A100 at 40,200 tok/s (42.3% MFU) | full | Gains reported on medical QA; forgetting not isolated in what I read. |
| BioMistral [full] | Mistral-7B-Instruct | PubMed Central subsample, **1.5 epochs** within a 20 h cluster limit | LR 2e-5, no warmup, batch 1,024 sequences (32 A100 80GB, FSDP), ctx 2048 | full | Merging pretrained model with base by SLERP was best of the merge methods tried in their tables (TIES and DARE also tested); SFT then adds most of the gain. |
| PoliLegalLM (Apr 2026) [full] | "a strong general-purpose foundation" (not named) | 140B CPT tokens: Chinese 100B (judgments 50B, general 35B, news 11B, statutes/interpretations 2B, books 2B), English 40B; general 55B vs domain 85B [derived 39:61]; Stage I 8K ctx on 90%, Stage II 16K ctx on 10% | LR values not given; ~786K tokens per step | not stated | CPT ablation on a 30B-A3B: LawBench 60.63 to 60.94 (+0.31), LexEval 57.38 to 59.53 (+2.15), PoliLegal 84.45 to 86.85 (+2.40). Small gains for 140B tokens. SFT 1.83M samples (general ~66% / domain ~34% by table). |
| Llawa (Taiwan/German law) [full] | TAIDE (Llama-3 based) | 107B tokens (Taiwan law 56B, German law 41B, other 10B), one epoch, ~8 days on 16 H100 | not extracted | full CPT then full SFT | Modest: Task A 24.92 to 28.55; no gain on B; did not beat Llama-3-8B-Instruct; DPO/ORPO lowered scores; LoRA-only tuned models mixed (some below base). Authors: CPT adds knowledge, does not uniformly help tasks. |
| BloombergGPT [abstract] | trained from scratch | 363B finance + 345B general tokens (~51/49), 50B params | not found | n/a | not found |
| DISC-LawLLM [snippet] | Baichuan-13B-base | SFT only: 403K total incl. Alpaca-GPT4 48K + Firefly 60K general (~27%), legal pair ~256K, triplet 39K | LR 5e-5, 2 epochs, batch 256, 8xA800, ctx 2048; LoRA not confirmed | likely full | not extracted |
| InternLM-Law [snippet] | InternLM2-Chat | no CPT; >1M queries, two-stage SFT (legal+general, then high-quality legal) | not extracted | not extracted | beats peers on 14/20 (zero-shot) and 15/20 (one-shot) LawBench tasks |
| Lawyer LLaMA [abstract] | LLaMA | continual training on legal corpora + SFT + retrieval of statutes | not found | not found | "hundreds of expert-written examples beat tens of thousands of ChatGPT-generated ones" |
| ChatLaw [abstract] | not specified on abstract page | multi-agent + mixture-of-experts, retrieval | not found | not found | +7.73% on LawBench vs general models incl. GPT-4 (as claimed) |
| LegalSearch-R1 (May 2026) [full] | Qwen2.5-7B-Instruct | RL only: 3,584 training samples (512 per task x 7 tasks), 16 statutes in all historical versions with validity windows (t_from, t_to) | GRPO, LR 1e-6, global batch 64, 8 rollouts, 112 steps, no KL; 8 H100, VERL + FSDP offload | full | In-domain avg 55.90 vs 50.56 DeepSeek-V3.2; article recitation ROUGE-L 96.73 vs 63.30; removing the local statute RAG dropped training reward 0.561 to 0.469. |
| MediTron / others not read: LawLLM, FinGPT | | not found | | | |

Takeaways with numbers:
- Replay in law CPT papers is small (Saul 2%, Meditron 1%) because the base is strong in English and the domain is English. Our shift is much larger (new languages and scripts), so the closer anchors are the language-adaptation papers (Section 3) and Gupta et al. (Section 4): 25-50% replay, not 1-2%. [judgment grounded on tagged numbers]
- CPT gains in 2025-26 legal work are small and uneven (+0.3 to +2.4 points PoliLegalLM; mixed in Llawa). The big wins came from task data and retrieval/RL (LegalSearch-R1: 3,584 samples). [full]
- Everyone uses full-parameter CPT on clusters (256 MI250, 128 A100, 32 A100, 16 H100). Nobody I found did 27B CPT of legal text on one GPU.

## 2. Turning raw documents into training signal

- **AdaptLLM, reading comprehension (Cheng et al., ICLR 2024)** [full, targeted]: raw domain text hurts prompting ability (their finding); fix = turn each raw text into reading-comprehension tasks (mined patterns, input-output templates, task reversal), then mix with general instructions (LIMA, WizardLM, Orca). Best raw-comprehension : general-instruction ratios: **1:1 biomedicine, 1:2 finance, 1:1 law** (LLaMA-7B; law corpus = FreeLaw opinions). A 7B model reached domain performance comparable to far larger domain models (claim in abstract).
- **Instruction Pre-Training (Cheng et al. 2024)** [full, targeted]: an instruction synthesizer (Mistral-7B tuned) writes instruction-response pairs from raw text; 200M pairs synthesized; **500M model on 100B tokens matched a 1B model on 300B tokens** (their claim); for domain CPT they convert the whole raw corpus to instruction-augmented text and mix general instructions as in AdaptLLM; Llama3-8B finance/biomed matched or beat Llama3-70B (their claim). Takeaway: keep the raw text **and** the task pairs attached to it, not replace it.
- **EntiGraph (Yang et al., 2024)** [full, targeted]: 1.3M real tokens (QuALITY books) to **455M synthetic tokens** by entity-pair relation generation (gpt-4-turbo), CPT of Llama 3 8B; gets about **80% of the accuracy gain** of having the source in context; RAG on top of the CPT model beats RAG on base. Lesson: plain paraphrase saturates; build synthetic text around entities/relations (acts, bodies, articles, dates) so it stays diverse. Constraint for us: they used a cloud model; our rule is no decision text to a cloud API, so generation must use local Qwen.
- **Allen-Zhu and Li, Physics of LMs 3.1** [full, targeted]: knowledge can be memorised but not extractable unless the pretraining text is augmented (paraphrase, sentence shuffling, translation); mixed training (QA data present during pretraining) enables extraction; instruction-finetuning alone does not (unless data were augmented); augmenting a subset ("celebrities") helps the rest. Their "2 bits per parameter" and exposure counts: not extracted by me.
- **Ovadia et al., Fine-Tuning or Retrieval** [full, targeted]: RAG consistently beats unsupervised fine-tuning for knowledge injection; multiple paraphrases per fact help fine-tuning. **Gekhman et al.** [full, targeted]: fine-tuning on facts the model does not know is learned slowly, and once fitted it increases hallucination; early stopping helps; composition of "known" vs "unknown" examples matters.
- **Lawyer LLaMA** [abstract]: small expert-written set beats large distilled set.

Generating diverse task families from statutes without one template (practice from the above; the exact numbers are ours to tune) [judgment]:
1. Define 15-25 task families from the exam families and real jobs: lookup (article text by number and date), in-force-on-date, edition diff ("what changed between editions X and Y"), hierarchy conflict, flip (cancelled or amended?), cites/cited-by, competence, procedure checks, citation-with-quote, abstain-with-reason, tool-call to fetch the article.
2. For each family use >=8 surface forms (question phrasings, Uzbek Latin / Cyrillic / Russian / English, formal vs plain), >=3 output formats (short answer, answer + quote, JSON only for tool/structured tasks, free explanation). Never one JSON shape for everything (our run 1 error).
3. Dedup on the full prompt+answer pair and on answer text per family; cap any single answer string at <2% of a family; balance labels (yes/no/unclear) near the real mix the verifier will see; keep "unclear" only where the source truly cannot decide.
4. Answers come from the corpus structure (relations, dates, edition metadata) so they are verifiable, not from a model's opinion. Keep negatives: wrong article numbers, wrong dates, near-miss acts.

## 3. Low-resource language adaptation (Uzbek, Kazakh, Turkic)

| Work | Facts |
|---|---|
| Sherkala-8B (Llama-3.1-8B) [full, targeted] | 45.3B CPT tokens: Kazakh 19.45B (76% open web, rest machine-translated English Wikipedia), English 19.45B (43%), Russian+Turkish 6.4B. Small-scale ablation best ratio Kazakh : Russian+Turkish : English = **3:1:3**. Vocab 128,256 to 159,766 (+25%). Fertility Kazakh 4.73 to 2.04 tokens/word, Russian 2.56 to 2.21, Turkish 2.23 to 1.82. CPT peak LR 1.5e-4, 4M-token batch, ctx 8192, warmup 1%, cosine to 10%. New embeddings: WECHSEL-style, top-5 similar old tokens weighted. SFT ~3.5M Kazakh + 3.8M English + 263K Russian pairs, 3 epochs, peak LR 7.5e-5. English average 59.1 vs Llama-3.1-Instruct 60.1 (small loss). Licence of the chat model: cc-by-nc-sa-4.0 [snippet]. |
| alloma-8B (Llama 3.1, Uzbek) [full, model card] | 3.6B CPT tokens, 67% English / 33% Uzbek, ctx 4096; less-useful non-ASCII tokens swapped for Uzbek tokens (vocab size unchanged); init = mean of old subtoken embeddings; **~1.7 tokens per Uzbek word vs ~3.5 for Llama**; recommends replacing apostrophes with "APST" to keep fertility low. Results vs Llama-3.1-8B-Instruct: FLORES BLEU Uz-En 31.16 vs 24.23, En-Uz 15.58 vs 8.28; MMLU-uz 41.89 vs 40.51; but English MMLU 53.35 vs 60.59 and news classification 65.65 vs 73.63 (authors blame forgetting). |
| NeuronAI-2B/-Uzbek [snippet, model cards, self-reported] | 2B-token CPT; stock Qwen3.5 needs 1.42x tokens for same Uzbek text; cards disagree internally; treat as anecdotal. |
| behbudiy Mistral-7B-Instruct-Uz [snippet] | CPT+SFT on mixed Uzbek/English public and synthetic data; token count not found; a third-party benchmark found invalid-output rates 5.71% on TUMLU-Uzbek. |
| UzBERT (2021) [snippet] | encoder pretraining for Uzbek; details not read. |
| KazLLM, Tilmoch | not found / not read in this pass |

Our Qwen tokenizer: 4.03 tokens/word on Uzbek-Latin legal text (22 docs, local measurement); that is Sherkala-before-extension territory. Cost: a 1B-word Uzbek corpus is ~4B Qwen tokens, and context and compute are eaten ~2x versus a 2.0 tokens/word tokenizer. Options [judgment]: (a) keep the tokenizer (safe, no embedding surgery, loses ~2x efficiency); (b) alloma-style in-place vocabulary swap (keeps vocab size; needs embedding init and a retrain of embeddings/LM head, which LoRA must then include and costs memory); decide after measuring on 500 docs per script. Do not extend the vocabulary before the exam baseline is stable.

Script mixing: Uzbek Latin and Cyrillic are separate scripts for the model; our crawl has both plus Russian and English versions of the same act. This is parallel data: use it deliberately as translation and alignment signal (Sherkala used machine-translated English Wikipedia as 24% of its Kazakh). Normalise the five apostrophe characters (CLAUDE.md textnorm) before training, as alloma's "APST" finding shows apostrophes change fertility.

Public Uzbek web data: FineWeb-2 covers >1,000 languages, 1,868 language-script pairs, licence **ODC-By**, per-language MinHash dedup with duplicate-count "rehydration" [full]. The Uzbek (uzn) row sizes: not found (dataset card table not retrievable here). CulturaX Uzbek: not verified.

## 4. Collapse and forgetting prevention

- **Gupta et al., Simple and Scalable Strategies** [full, targeted]: re-warm LR to the peak, then re-decay (cosine) when starting CPT; "even as little as 1%" replay mitigates forgetting to a large extent; their combined recipe used **5% replay for a weak shift (SlimPajama) and 25% for a strong shift (German)**; recommends trying several replay fractions on a small token budget because differences show early. Follow-up use: Glorioso et al. used LR re-warm, re-decay and **60% replay** in a 50B-token decay phase. [full]
- **Biderman et al., LoRA Learns Less and Forgets Less** [full, targeted]: Llama-2-7B; CPT on code (StarCoder-Python up to 20B tokens) and math (OpenWebMath 14.7B tokens); standard low-rank LoRA (r=16, 64) clearly underperforms full fine-tuning on CPT; best LoRA r=256 peaked at 16-20B tokens (e.g. GSM8K 0.203 at 16B vs full 0.224 at 4B and 0.293 at 20B); in instruction fine-tuning, high rank closes most of the gap; **LoRA forgets less than full fine-tuning**, and forgetting is controlled by rank; full fine-tuning learns perturbations with rank 10-100x higher than typical LoRA; LoRA is sensitive to learning rate and target modules (all linear layers recommended).
- **Unsloth Qwen3.5 guide** [full]: to keep reasoning ability keep at least **75% of SFT data in reasoning style**; QLoRA (4-bit) **not recommended** on Qwen3.5 (larger-than-normal quantization error); needs transformers v5; 27B bf16 LoRA about **56 GB** VRAM; example r=16, alpha=16, ctx 2048, all projections.
- **Merging**: BioMistral [full, targeted] merged the CPT model with the base by SLERP (TIES and DARE also tried) and the SLERP merge was a strong choice before SFT; MergeBench (2505.10833) compares 8 merging methods for forgetting but I did not read it [snippet]. Judgment: after each LoRA stage, test a linear interpolation of the adapter weight (scale 0.3, 0.5, 0.7, 1.0) against the exam and the general benchmark; it is a free forgetting dial.
- **Diversity metrics** (not from one source; standard checks) [judgment]: fraction of unique prompts and unique answers per family; max share of any answer string; template entropy per family; per-label balance; n-gram self-BLEU on answers. Gate: a SFT set where >5% of answers are identical must not train (run 1 had 73%).

## 5. Practical recipe on one 96 GB GPU

What fits [full unless noted]:
- bf16 weights 27B = ~54 GB [derived]. LoRA bf16 at 2K context: Unsloth says 56 GB; headroom ~40 GB for activations, so long sequences need gradient checkpointing (Unsloth's own mode) and packing at 4-8K, not 262K.
- Full fine-tuning: Unsloth says ~4x the LoRA VRAM (so >200 GB) [full]; with AdamW 16 B/param = ~430 GB [derived]. Does not fit on 96 GB even with CPU offload at reasonable speed; do not plan it on this machine.
- QLoRA: Unsloth recommends against it for Qwen3.5 [full]. Skip.
- Qwen3-32B Unsloth on RTX PRO 6000 Blackwell Max-Q (Fixstars) [full]: LoRA batch size 2 max (batch 4 exceeded 96 GB), Unsloth ran batch 32; Wikipedia 1,000 samples: Unsloth ~17 min, LoRA ~31 min, QLoRA ~40 min; ~3,600 samples/hour on the long-text dataset. Tokens per sample unknown, so no tokens/s figure from this source. Qwen3.5's Gated DeltaNet kernels need Triton compilation at first run (Unsloth note).
- Published tokens/s anchors: Meditron-70B 40,200 tok/s on 128 A100 = ~314 tok/s per A100 at 42.3% MFU [full]; scaled by parameters to 27B = ~815 tok/s per A100-equivalent [derived].

Throughput and cost on our hardware (all [estimate]): training FLOPs = 6 x 27e9 = 1.6e11 per token (LoRA with checkpointing is about the same). Assume the RTX PRO 6000 delivers about 250 TFLOPs bf16 dense (not verified here) at 28-60% MFU: 430-930 tokens/s per GPU. Therefore:

| Token budget | GPU-hours (1x 96 GB) | Calendar |
|---|---|---|
| 50M (task SFT) | 15-32 h | 1-2 days |
| 0.5B (CPT) | 150-320 h | 6-13 days |
| 1B (CPT) | 300-650 h | 13-27 days |
| 2B (CPT) | 600-1,300 h | 25-54 days |

So a 0.5-2B-token CPT on one card is a 1-8 week job; the L40S (48 GB) cannot hold the 27B bf16 for training, so use it for data generation with a small model, evals, and verifier runs. If we want >1B CPT tokens, renting a multi-GPU node is the honest answer (no price researched). Given Biderman (LoRA learns less in CPT) and Ovadia (retrieval beats fine-tuning for knowledge), **budget 0.5-1B CPT tokens of LoRA r=256 as a "fluency and structure" stage, and keep retrieval/tools as the source of truth for article text**. [judgment]

Sequence packing and long documents: pack to 4,096 (stage I) then 16K on ~10% (PoliLegalLM used 8K on 90% and 16K on 10%) [full]; acts exceed this, so split at article boundaries with the metadata header repeated on each chunk. Training at full 262K is out of scope on 96 GB.

## 6. Data engineering

- **Dedup**: FineWeb-2 style MinHash, 5-gram word shingles, 14 buckets x 8, done per language, with duplicate-count-aware upsampling instead of blind removal [full]. Saul used a similarity threshold of 0.5 with their dedup tool [full]. **Warning for editions**: consecutive editions of one act are near-identical by design; a 0.5 MinHash will delete all but one. Dedup within each (act, edition) and across unrelated documents; keep editions as intended near-duplicates and control repetition by sampling instead. [judgment]
- **Quality filtering**: Saul: NFKC, regex removal of page and line numbers, KenLM perplexity filter trained on a small clean legal set [full]. For us: filter OCR text (2,074 scanned decisions) by character error proxy and script purity, and drop page headers (textnorm.split_decision).
- **Editions of the same act**: no paper found that trains on all editions. The closest evidence: LegalSearch-R1 attaches validity windows (t_from, t_to) to every article version, filters retrieval by the query year, and gets large gains on temporal queries (502 in-domain temporal queries; baselines 97-227 answered) [full]. Recommendation [judgment]: train on **all editions**, each as its own document with a header, plus synthetic **diff documents** ("on 12.11.2026 article X changed from ... to ..."), and in-force-on-date tasks in SFT. Never train on an edition without its date in the header, or the model will blend versions (a likely cause of in_force 35%).
- **Metadata header** (proposal): `[ACT] <title> | number | type | body | adopted | in force from | edition valid from-to | status | language/script | lex.uz id`, then text split at article boundaries. Put the header on every chunk. Mask loss on the header for ~half of the samples so the model learns to use it, not just copy it. [judgment]
- **Curriculum / ordering** [judgment, no source]: (1) replay-heavy warm-up with Uzbek web text and parallel act versions, (2) current-edition national acts, (3) all editions + diffs, (4) local decisions, cases, cancellations, drafts, (5) final annealing 10% of tokens on the highest-quality clean text and task-augmented text with LR decayed to 10% (Saul-54B annealed on high-quality legal instruction data [full]; Gupta: re-decay [full]). Shuffle within each stage.
- **Exam leakage control**: split by act family and time. Any decision used as an exam item, its cancelling act, and its registration number must be removed from CPT and SFT; run n-gram overlap (13-gram) of every training chunk against exam prompts; keep a time-cut holdout (acts adopted after a cutoff date) that no stage sees.

## 7. Which data goes into which phase

Phases: **P1 law school** = continued pre-training; **P2 internship** = diverse task SFT on real cases; **P3 practice** = RL with our verifier; **P4 morning briefing** = daily change digest in context + periodic retraining.

Roles: K = knowledge, T = task signal, R = reward/verifier, E = eval only.

### 7a. Our sources

| Source | Phase | Role | Format | Risks |
|---|---|---|---|---|
| lex.uz acts, all editions | P1 (bulk), P2 (task source), P3 (verifier ground truth), P4 (daily delta) | K, T, R | P1: header + article-chunked text, all editions + diff docs, 4 languages. P2: lookup, in-force, diff, citation tasks. P3: in-force-on-date and relations used as exact-match rewards. P4: new act + diff to the old edition in context | licence/terms of lex.uz text for model training: not checked; editions near-duplicate (dedup trap); exam items drawn from it (leakage) |
| lex.uz relations (amends, cancels, cites) | P2, P3 | T, R | graph facts become tasks: "which act cancelled X", "does Y cite Z"; reward = graph match | incomplete or noisy "Korrespondentlar" pages; do not treat missing relation as proof |
| lex.uz cancellation notes ("LexUZ sharhi" note naming the cancelling act) | P2, P3, E | T, R, E | label source: in_force / lost_force flips | the same notes build the exam labels: hold out the exam items' notes entirely |
| public.sud.uz administrative cases (outcomes) | P2 (outcome and cited-act tasks), P1 only for the stripped legal reasoning text if added later, E | T, E | extract only: decision number, date, court, outcome valid/invalid, normative act cited (CLAUDE.md rule); task: "was act X upheld, on which ground" | personal names must be stripped, never stored; outcomes under-represent individual decisions (CLAUDE.md); PDFs later; leakage if exam positives come from the same cases |
| stat.sud.uz counts | E only | E | numbers for eval narrative and sanity checks | aggregate counts, not text; no training value |
| e-qaror.gov.uz and e-qaror-respublika (stages, Asos basis lines, declared-invalid labels) | P2, P3, E | T, R, E | stage tracker as structured fields to tasks ("was public discussion done?"); declared-invalid as reward label | declared-invalid is under-filled (275 rows) per CLAUDE.md, so absence is not validity; throttling; no text for most rows |
| regulation.gov.uz / regulation.adliya.uz drafts (draft vs adopted) | P1 (draft text), P2 (draft-vs-adopted diff tasks, check 9/10/11), P3 | K, T, R | draft + adopted pair with dates; task: what changed after discussion | local drafts show `***` and PDF text may drop apostrophes; no link draft to adopted act (match by title/body, noisy) |
| sharh.lex.uz commentary | **not trained**; P4/RAG or E only until licence is known | K (retrieval), E | keep out of weights; retrieve at answer time with source shown | licence unknown (coordinator); commentary phrases would also leak into exam answers |
| data.egov.uz Adliya registers | P2, P3, E | T, R, E | registers become lookup and status tasks and sanity-check labels | schema drift; no text; verify freshness |
| gov.uz / my.gov.uz (bodies, citizen services) | P1 (small), P2, P4 | K, T | body names, competences, service descriptions as short factual docs and "who handles X" tasks | pages change; marketing tone; keep small |
| Government Telegram channels | P4 only | K (fresh), T | daily digest items with date and channel, as context not weights | terms of use unclear; noise; unreliable for law text; never use as label |
| OCR text of scanned PDFs | P1 (after filter), P2 | K, T | same header as typed text, flagged `ocr=true`; use clean OCR only | OCR errors teach wrong spellings; Cyrillic/Latin mix; exclude pages below a quality score |
| Lawyer reviews | P2 (gold), P3 (reward calibration), E (held-out half) | T, R, E | review = question, flag, article, quote, verdict | few samples; each used in training must be removed from eval; Lawyer LLaMA: hundreds of expert items beat tens of thousands of distilled [abstract] |

### 7b. Public open datasets experts would add

| Dataset | Licence | Phase and role | Amount (anchor) | Notes |
|---|---|---|---|---|
| FineWeb-2 Uzbek (uzn Latn/Cyrl), Russian | ODC-By [full] | P1 replay, K (language) | Uzbek share of replay 10-15% of P1 tokens [judgment]; anchors: Sherkala 3:1:3, alloma 33% Uzbek | uzn size: not found; check script split and toxicity |
| CulturaX Uzbek | licence not verified | P1 replay | as above | verify licence before use |
| FineWeb-Edu or similar English edu text | ODC-By in my memory, unverified | P1 replay | English+Russian general ~10% of P1 tokens [judgment]; anchors: Gupta 25% for strong shift; Glorioso 60% in a decay phase; Saul 2%; Meditron 1% | |
| Math/reasoning text | varies | P1 replay | ~5% (Saul-54B used 5% math to keep reasoning) [full] | |
| Tulu 3 SFT mixture, 939,344 samples | ODC-BY-1.0 overall; subsets differ (No Robots CC-BY-NC-4.0; FLAN v2 licence not listed on the card) [full] | P2 general mix, T | general : legal ~ 2:1 by count in PoliLegalLM SFT (66/34) [full]; DISC-LawLLM ~27% general [snippet]; AdaptLLM 1:1 domain : general instruction for law [full] | drop NC subsets; use the multilingual Aya part (100,000, Apache-2.0) for non-English instruction |
| OpenThoughts3 (1.2M examples, teacher QwQ-32B), OpenThoughts2-1M | licence: not found | P2/P3 reasoning, T | keep reasoning style >=75% of SFT per Unsloth when preserving thinking [full]; our scale: tens of thousands of samples, not 1M | long traces; distil from our own model with the verifier instead where possible |
| Tool-use / function-calling sets | not researched | P2 | enough to keep tool-call tokens working; amount not found | the model has native tool-call tokens; keep our tools' schema in all tasks |
| Self-generated base-model answers (thinking and non-thinking, tool calls) | ours | P1 replay and P2 | 5% of P1 [judgment] | preserves the exact output habits the base had (self-distillation) |

Mixing ratios used in the sources: Sherkala Kazakh : Russian+Turkish : English = 3:1:3 (small-scale ablation optimum) [full]; AdaptLLM 1:1 law [full]; PoliLegalLM CPT 61% domain / 39% general [derived]; Saul 2% general replay [full].

## 8. Mezon law-school recipe

### Stage 0. Baseline and eval harness (1-2 days)
- Freeze MezonBench families (hierarchy, in_force, flip, lookup, plus the new families) with held-out acts and a time-cut. Report per family: right / wrong / unclear (not only accuracy), for base no-think and base think: today 38/100 and 27/100. Add a general benchmark for forgetting (English MMLU-style subset, a Russian and an Uzbek QA subset, tool-call format test).
- Fix: score "unclear" separately; an abstention-heavy model must not look safe.

### Stage 1. Data build (before any GPU)
- Corpus tokens: not yet counted. Compute with the Qwen tokenizer once the crawl ends; planning figure: tokens = words x ~4.0 (Latin legal Uzbek, measured). Train set = P1 corpus (all editions with headers, diffs, local decisions, cases, drafts, OCR clean) plus replay.
- Sizes to start from [estimate]: 0.5-1B CPT tokens total. Mix: 45% law acts (current + all editions with headers; editions downsampled so no act exceeds a cap), 8% diff documents, 7% cases/cancellation/drafts, 8% reading-comprehension / instruction-augmented text generated locally from the same docs (AdaptLLM / Instruction Pre-Training style), 32% replay (12% Uzbek and Russian web from FineWeb-2, 10% English edu, 5% math, 5% self-distilled outputs). Gupta says search the replay fraction on a small budget: run 4 mixes (15/25/35/50% replay) at 20M tokens each first.
- No decision text to a cloud API; use local Qwen for generation. Dedup per Section 6; leak check against the exam.

### Stage 2. CPT / mid-training with replay (LoRA on the 96 GB card)
- Start values [judgment from Biderman, Gupta, Sherkala, Meditron]: LoRA r=256 (try 64 vs 256 on 20M tokens), alpha=r, all linear layers (and embeddings only if the tokenizer changes), bf16 (no QLoRA), LR peak 1e-4 (LoRA tolerates higher than full 2e-5 to 1.5e-4 used in the papers; **sweep 5e-5 / 1e-4 / 2e-4 on 20M tokens**), warmup 1-3%, cosine decay to 10%, AdamW, weight decay 0.1, ctx 4,096 packed (10% at 16K), 1 epoch (BioMistral 1.5 epochs, Llawa 1 epoch), gradient checkpointing, batch ~0.5M tokens/step.
- Cost: 0.5B tokens = 150-320 GPU-hours, 1B = 300-650 [estimate].
- Checks every ~50M tokens: MezonBench (lookup and in_force should climb first), general benchmark (stop if English MMLU subset drops more than 3 points or tool-call format breaks), loss on a held-out law set, abstention rate. Run the adapter-scale interpolation test (0.3-1.0) at the end.
- Escalation: if lookup stays <30% after 0.5B tokens, the honest conclusion is that knowledge goes through retrieval/tools (Ovadia, LegalSearch-R1), and the model is trained to use them; do not push CPT beyond 1B on one card.

### Stage 3. Diverse task SFT ("internship")
- Data: 50-200K examples [estimate; Lawyer LLaMA and LegalSearch-R1 show small, high-quality sets matter: 3,584 samples sufficed for RL stage], 20+ task families, each with >=8 phrasings, >=3 output formats, 4 languages; all verifiable from the corpus; add tool-call turns for fetching the article by number and date; mix general instructions 1:1 with legal (AdaptLLM law ratio) or ~2:1 general-heavy (PoliLegalLM 66/34) and keep >=75% in reasoning style when thinking is kept (Unsloth).
- Calibration: include correct "unclear" only where truly undecidable, and "retrieve first" demonstrations where the answer lives in the store; this targets the thinking-mode abstention seen in the closed-book check (69/100 unclear).
- Hyperparameters [judgment]: LoRA r=64-128 (IFT closes the gap at high rank, Biderman), LR 1e-4 (Saul IFT 1e-5 full; Sherkala SFT 7.5e-5 full; LoRA ~10x higher), 1-2 epochs (Saul: one epoch best), cosine, ctx 4-8K, thinking on and off samples both present.
- Cost: 50M tokens ~ 15-32 GPU-hours [estimate].
- Checks: MezonBench per family and per format; answer-diversity gates (<5% identical answers, no answer >2% of a family); general benchmark; thinking vs non-thinking gap; the old JSON-collapse test (does a free-text question still get free text?).

### Stage 4. Reasoning / RL with our verifier ("practice")
- Rewards from exact graph and date facts (in-force on date, which act cancelled which, hierarchy winner), citation-validity check (article exists and was in force), format; abstention penalised when the verifier knows the answer, rewarded when truly undecidable; no reliance on an LLM judge where an exact match exists. LegalSearch-R1 anchors: GRPO, 8 rollouts, batch 64, LR 1e-6, no KL, 112 steps, 3,584 training samples, reward 0 for broken format [full].
- Rejection-sampling SFT from the model's own correct verified traces is the cheap first step and fits one GPU; full GRPO on 27B on one card is a stretch (their run used 8 H100), so start with best-of-n + SFT and small-scale GRPO on a LoRA. [judgment]
- Cost: not found for our case; guess 50-150 GPU-hours [estimate, wide].
- Checks: verifier pass rate on held-out acts, MezonBench, general benchmark, hallucinated-citation rate (must be 0 to ship).

### Stage 5. Morning briefing
- Daily: sync delta, new acts, amendments, cancellations as dated items with a diff to the previous edition, put in context (262K window) or retrieved; evaluate yes/no on "what changed" questions; retrain adapters monthly or quarterly, replaying the previous set; never let Telegram text enter weights.

### The 5 mistakes that killed run 1, and the fix for each
1. **Near-duplicate data**: 672 of 917 answers were identical, so the model learned the one answer. Fix: dedup on prompt+answer, cap any answer string, balance labels, diversity gates before training (Section 4).
2. **One output shape (JSON) for every question**. Fix: >=3 output formats per family; reserve JSON for tool and structured tasks; check free-text still works after training.
3. **SFT on facts it did not have** (lookup 0%). Gekhman: fitting unknown facts is slow and raises hallucination; Ovadia: retrieval beats fine-tuning for knowledge. Fix: CPT with replay first for knowledge/language, tools for exact text, SFT teaches procedure with retrieval in the loop.
4. **No replay or reasoning-style data**, so format and abstention habits shifted (cf. closed-book check, abstention 49/100 and 69/100). Fix: replay 25-50% in CPT (Gupta, Sherkala), >=75% reasoning-style in SFT (Unsloth), self-distilled base outputs, and score abstention separately.
5. **No stage gates**: trained to the end and looked at the exam once (0/400). Fix: eval every 50M tokens or 500 steps with a stop rule, a general-benchmark forgetting check, per-family right/wrong/unclear, and an adapter-scale interpolation test before accepting a stage. (Hyperparameters of run 1 are not in this brief; if LR or rank was extreme, add that as a sixth hypothesis.)

## 9. Not found or not done
- Token counts and quality of the whole lex.uz corpus (crawl unfinished); tokenizer measurement on Cyrillic and larger samples.
- Saul-7B LR/epoch, forgetting numbers for most models; Meditron/BioMistral merge numbers beyond the SLERP row; KazLLM, Tilmoch, UzBERT details; LawLLM, FinGPT; MergeBench numbers.
- Real tokens/s on RTX PRO 6000 for Qwen3.5-27B (Unsloth/ms-swift/LLaMA-Factory/axolotl/torchtune): not found; the table above is derived from FLOPs and from Meditron's published throughput.
- FineWeb-2 Uzbek size; CulturaX licence; OpenThoughts licence; tool-use dataset choice.
- Source of the "Qwen3.8" name; sources show Qwen3.5-27B.
