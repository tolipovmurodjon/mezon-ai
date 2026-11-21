# Knowledge freshness: how to add new knowledge to an LLM and keep it current (research, 20 Nov 2026)

Scope: any field (medicine, finance, news, code APIs, law). Public sources only. Evidence labels:
- **[full]** = I read the paper text (PDF converted with pdftotext) and the number is copied from it.
- **[abstract]** = read the arXiv abstract page only (no tables).
- **[snippet]** = seen only in a search-result summary, not verified against the paper. Re-check before quoting on stage.
- **not found** = I looked and did not find it. Nothing here is invented.

## 1. Fine-tuning vs retrieval for knowledge injection

| Source | Finding | Numbers | Label |
|---|---|---|---|
| Ovadia et al. 2023, "Fine-Tuning or Retrieval?" (arXiv 2312.05934) | RAG beats unsupervised fine-tuning (FT) for both old and brand-new knowledge. FT on many paraphrases of the same text helps, and accuracy rises monotonically with the number of paraphrases. | Current-events task (events Aug-Nov 2023, after the models' cutoff), Mistral 7B: base 0.481, base+RAG 0.875, FT on raw text 0.504, FT on paraphrases 0.588, FT-par+RAG 0.830. Llama2 7B: base 0.353, RAG 0.585, FT-reg 0.219 (worse than base), FT-par 0.392. Orca2 7B: base 0.456, RAG 0.876, FT-par 0.566. On MMLU topics FT gave small gains (e.g. Mistral anatomy 0-shot 0.556 base, 0.681 RAG, 0.570 FT). Combining FT and RAG did not beat RAG alone in most cells (Mistral current events: RAG 0.875 vs FT-par+RAG 0.830). | [full] |
| Gekhman et al. 2024 (EMNLP), "Does fine-tuning on new knowledge encourage hallucinations?" (2405.05904) | Examples whose answer the model does not already know are learned much more slowly, and once fitted they raise hallucination roughly linearly with their share. Fine-tuning mostly teaches the model to use knowledge it already has. Early stopping or filtering Unknown examples helps. Relabelling Unknown examples as "I don't know" reduced the damage. | Accuracy on Unknown test items is 3.2% or less after FT (so they truly were unknown). From early stop to convergence: WeaklyKnown 39.2 -> 35.4, Unknown 37.5 -> 25.8 (their metric on the dev/test mix, see paper Fig/Table for the exact setting). Relabelled-IDK variant stays at 61.8 at both stopping points vs 43.0 -> 38.8 for the plain variant. | [full] |
| Soudani et al. 2024, "Fine Tuning vs. RAG for Less Popular Knowledge" (2403.01432) | FT helps across popularity; RAG beats FT "by a large margin" on the least popular facts; better retrieval and data augmentation help both. | no numbers read | [abstract] |
| RAFT, Zhang et al. 2024 (2403.10131) | Train the model on (question, retrieved documents including distractors, chain-of-thought answer that quotes the right passage). Beats domain fine-tuning with and without RAG. | LLaMA2-7B: HotpotQA 35.28 (DSF+RAG 4.41, RAG 0.03); HuggingFace 74.00 (DSF+RAG 42.59); PubMed 73.30 (DSF+RAG 71.6); TorchHub 84.95 (DSF+RAG 82.80); TensorFlow 86.86 (DSF+RAG 60.29). Default recipe: 1 gold document + 4 distractors; best share of examples that include the gold document ranged 40-100% by dataset (paper is inconsistent on exact values). Note the table was fetched through a summariser. | [snippet-quality table, abstract confirmed] |
| Self-RAG, Asai et al. 2023 (2310.11511) | One model trained with "reflection tokens" to decide when to retrieve and to critique passages and its own output; beats ChatGPT and retrieval-augmented Llama2-chat on QA, reasoning, fact checking, and improves citation accuracy (7B and 13B). | no numbers read | [abstract] |
| Xie et al. 2023/ICLR 2024, knowledge conflicts (2305.13300) | Models are often receptive to coherent retrieved evidence even when it contradicts their memory, but show confirmation bias when evidence mixes memory-consistent and conflicting content. Meaning: old law in weights can leak when the retrieved text is ambiguous. | none | [abstract] |

Takeaway: for facts that change, retrieval wins; fine-tuning on raw text barely learns facts (Llama2 got worse), and training on unknown facts can raise hallucination. What fine-tuning is good at is teaching format, behaviour and how to use documents (Gekhman; RAFT).

## 2. Synthetic continued pre-training and paraphrase augmentation

- **EntiGraph (Yang et al. 2024, 2409.07431) [full].** Source corpus: 1.3M tokens of QuALITY articles/books. Generated 455M synthetic tokens with gpt-4-turbo, continued pre-training of Llama 3 8B for 2 epochs with replay at rate 0.1 (10% of batches are RedPajama data, 1B tokens available). Closed-book QuALITY accuracy 39.49% -> 56.22% (+16.73 points), log-linear in synthetic tokens up to 455M. RAG on the base model: 39.49% -> 60.35% (+20.86). So EntiGraph gives more than 80% of RAG's gain with no documents at test time, and the gains compose with RAG. The abstract states a model may need "hundreds to thousands of diverse representations" of a fact. Caveat: one reading-comprehension corpus, one 8B model, and the generator (gpt-4-turbo) is far stronger than the student, so some of the gain may be distillation (the authors argue closed-book results beating GPT-4 rule out distillation alone).
- **Allen-Zhu and Li, "Physics of Language Models 3.1" (2309.14316) [abstract].** On a controlled biography dataset a model can memorise facts yet get 0% extraction accuracy unless the training text was varied (paraphrase, sentence shuffle, translation) during pre-training. Recommended: rewrite data with small models, put instruction data into pre-training. Numbers beyond the 0% were not read.
- **Ovadia (above) [full]:** paraphrase count correlates monotonically with accuracy, a smaller-scale confirmation.
- Cost note: EntiGraph's 455M-token generation is a large run for a 1.3M-token corpus (about 350 synthetic tokens per source token). A daily law change set is orders of magnitude smaller.

## 3. Continual learning, forgetting, editing

- **Ibrahim et al. 2024, "Simple and scalable strategies to continually pre-train LLMs" (2403.08763) [abstract].** Learning-rate re-warming + re-decaying + replay of old data matches full retraining from scratch on all data, tested on a 405M model (hundreds of billions of tokens; English to English and English to German) and on a 10B model for the weak shift. Replay percentage not read.
- **Biderman et al. 2024, "LoRA Learns Less and Forgets Less" (2405.09673) [full].** In code and math at 20B-token scale, LoRA at typical ranks underperforms full fine-tuning (best LoRA r=256 peaked at 20B tokens; HumanEval full-FT reaches 0.263 at 20B tokens per their text), but forgets the source domain less, and forgets less than weight decay or dropout. Full fine-tuning learns perturbations with rank 10-100x higher than typical LoRA configs. In instruction fine-tuning, high ranks can match full FT. Implication: LoRA is the safer tool for behaviour changes, a poor tool for stuffing in many new facts.
- **Model merging:** not researched in depth; no sourced numbers. not found.
- **ROME/MEMIT editing.**
  - Gupta et al. 2024 (2401.07453) [snippet]: at scale, ROME and MEMIT show gradual then sudden catastrophic forgetting; MEMIT forgets less than ROME; edits are less localised than assumed.
  - MEMIT paper (2210.07229) [snippet]: performance declines past about 100 edits (less than ROME).
  - Gupta and Anumanchipalli 2024 (2403.07175) [snippet]: "disabling edits" can collapse ROME; a reimplementation (r-ROME) avoids it.
  - MQuAKE (2305.14795) [snippet]: after editing, GPT-J with ROME answered 7.4% of multi-hop questions vs 40.5% before the edit (v1 reports 7.6% vs 43.4%); recall of the edited fact itself is fine. A memory-plus-decomposition method (MeLLo) works better.
  - AKEW (2402.18909) [snippet]: editing methods struggle to use updates given as natural text, as real updates are.
  - Why not production: edits are fact triples, degrade under many sequential edits, and break multi-hop consequences. A law amendment is a rewritten paragraph with consequences across other articles, which is the hard case. I found no public report of editing used in a production always-current system: **not found**.

## 4. Temporal knowledge and "as of date D"

- **Dhingra et al. 2022, TempLAMA / "Time-aware LMs as temporal knowledge bases" (2106.15110) [snippet].** T5-CBQA scored 17.8 on the 2010-18 temporal slice vs 28.5 on Natural Questions; training with timestamps on news improved temporally scoped knowledge. A later critique says TempLAMA is biased to long-duration facts (70.69% of questions have the most frequent answer for the subject).
- **Zhao et al. 2024, "Set the Clock" (2402.16797) [snippet].** TAQA, about 20K time-sensitive questions covering 2000-2023. Llama2 (2022 cutoff) mostly answered with knowledge from around 2019. Fine-tuning on TAQA improved 2022 answers by up to 62.2% relative, and aligning to 2010 reached up to 2.8x the unaligned model.
- **Cheng et al. 2024, "Dated Data" (2403.12958) [snippet].** Effective knowledge cutoffs often differ greatly from the reported ones (cause: temporal misalignment and deduplication in CommonCrawl). Example in a secondary summary: RedPajama reported March 2023 Wikipedia but effective around mid-2019. So never trust a model's own sense of "latest".
- **Temporal blind spots (2401.12078) [snippet].** Instruction-tuned LLMs do poorly on detailed questions about the past and on very recent information.
- **FreshQA / FreshLLMs, Vu et al. (2310.03214) [snippet].** LLMs of any size struggle with fast-changing knowledge and false premises; putting search results into the prompt (FreshPrompt) beat other search-augmented methods and Perplexity. A third-party summary says GPT-4 + FreshPrompt gained about 49 points under strict evaluation; unverified.
- **Retrieval has its own time problem [snippet for all].**
  - HoH (2503.04800): 96,124 QA pairs, 219,463 documents with current and historical versions; outdated content lowers accuracy even when current content is also retrieved.
  - TempRAGEval/MRAG (2412.15540): off-the-shelf retrievers struggle to find documents that need temporal reasoning.
  - Re3 (ACL 2026): strict time metadata filters miss relevant documents; stale but topically similar versions mislead the generator.
  - ChronoQA (2508.12282) is a temporal-sensitive RAG benchmark.
  - I found no benchmark that tests an explicit "as of date D" instruction directly: **not found**.
- Practical meaning: "as of D" is best solved outside the model, by filtering the corpus to editions valid on D before retrieval, then checking the answer's citations against D. The model should be trained to respect the dates it is shown.

## 5. Production patterns for always-current systems

What I could source:
- **Retrieval quality:** Anthropic's Contextual Retrieval post (anthropic.com/engineering/contextual-retrieval) [snippet]: top-20 retrieval failure rate 5.7% -> 3.7% with contextual embeddings (-35%), -> 2.9% with contextual BM25 as well (-49%), -> 1.9% with reranking (-67%); averaged over codebases, fiction, research papers; critics note teams already on hybrid search plus reranking will see less.
- **RAG is not a guarantee of correctness in law:** Magesh et al., "Hallucination-Free?" (J. Empirical Legal Studies 2025, arXiv 2405.20362) [snippet]: commercial legal RAG tools hallucinated at least 17% of the time; Lexis+ AI answered 65% of queries accurately, Westlaw AI-Assisted Research 42%; hallucination counts both wrong content and false claims that a source supports a statement. Upper bound of the range not confirmed.
- **Daily refresh, change logs, cache invalidation, citation verification as lab practice:** I found no lab-published numbers or architecture documents for "weights = intuition, database = facts". **not found.** The sourced version of the idea is the research above: weights learn skills and format (Gekhman), documents carry facts (Ovadia, FreshLLMs), and training on retrieved-context format (RAFT, Self-RAG) joins the two. Patterns such as daily index rebuilds and citation checks are standard engineering but I have no source with numbers for them.

## 6. For Mezon

Context: lex.uz editions by date (point-in-time store), a daily change log, an existing citation validator ("no flag without a valid source"), local LLM on our own machines (no cloud). Each recommendation is tied to a source.

**A. What stays in retrieval (all facts about law).**
1. Article text, dates, cancellations, and which edition applies. Why: FT on raw text gave Llama2 0.219 vs 0.353 base on new events while RAG gave 0.585 (Ovadia [full]); FT on unknown facts raises hallucination (Gekhman [full]); weights have an effective cutoff far from the stated one (Dated Data [snippet]).
2. Point-in-time filtering before ranking: pick the edition valid on the decision date `D`, then retrieve inside it. Never let the ranker choose between editions by similarity, because stale near-duplicates mislead generators (HoH, Re3 [snippet]). Our `ONDATE` edition store already allows this.
3. Cite-or-drop validator stays as is: every quote must exist in the dated edition. Even commercial legal RAG hallucinated at 17%+ (Magesh [snippet]), so retrieval alone is not proof.

**B. What goes into weights (skills, not statutes).**
1. Behaviour: read a dated edition, compare to the decision, quote exactly, say "unclear, needs expert", output the three conclusion types, Uzbek legal terminology and the five apostrophe spellings. Source: fine-tuning mostly teaches use of existing knowledge (Gekhman [full]); RAFT trains on question + retrieved documents + distractors + quoting chain of thought and beat plain domain fine-tuning (RAFT table).
2. Recipe: LoRA first (forgets less, Biderman [full]), with high rank only if quality is short. Mix about 10% general/replay data (EntiGraph used replay rate 0.1 [full]; Ibrahim [abstract] shows re-warm + re-decay + replay matches full retraining).
3. Cadence: retrain the behaviour adapter rarely (suggest quarterly, or when the base model changes or the eval below drops), not weekly. Facts change weekly, skills do not. This is a judgement from the sources, not a number from them. Do not put new amendments into weights.
4. Optional stable-law injection (only if wanted): a small, rarely changing core (Constitution, NLA O'RQ-682, Local State Power law) could use paraphrase or EntiGraph-style augmentation, because EntiGraph reached 56.22% vs 60.35% for RAG closed-book on a 1.3M-token corpus [full] and paraphrase count raises accuracy [Ovadia full; Allen-Zhu abstract]. But the amended articles then risk becoming stale inside weights. My recommendation is not to do this for v1; retrieval of the edition is the source of truth, and weights-memory of an old edition is exactly the failure to test for.
5. Do not use ROME/MEMIT: sequential edits degrade, multi-hop consequences collapse (MQuAKE 40.5% -> 7.4% [snippet]), and amendments are paragraphs not triples.

**C. How to generate training data so the model learns HOW to use dated law.**
1. Build examples from our own store, as RAFT does: question about a decision + the right edition (gold) + 4 distractors, where distractors include the older and newer editions of the same article (RAFT default 1 gold + 4 distractors [snippet-quality]; stale-version distractors address HoH/Re3 failures [snippet]). Use gold in 40-100% of examples as in RAFT, and keep the rest with no gold so the model learns to answer "unclear" (relabelling unknown as "I don't know" held accuracy at 61.8 vs 43.0 -> 38.8 in Gekhman [full]).
2. Counterfactual date pairs: for each article with an amendment, create two prompts with identical question but `D` before and after the amendment, and different correct answers with the quote from the matching edition. The model is trained to follow the text and date it is given, not memory (Xie: models accept coherent context but show confirmation bias with mixed context [abstract]).
3. Train on text where the in-context edition contradicts what the base model "remembers" (e.g. an edition with changed numbers), with the answer taken from the context and quote-validated. Same source as 2.
4. Use the real cancelled/positive labelled cases only as the exam, never as training answers, to keep the existing rule ("labels are the exam").
5. Paraphrase questions (several phrasings per item), not facts, because varied rephrasing is what makes knowledge extractable (Allen-Zhu [abstract]; Ovadia [full]).
6. Filter synthetic answers with the citation validator before they enter training, so the model never learns a quote that does not exist.
7. Teacher model: generation of the synthetic data must run on our machines under the project's rule (no decision text to cloud APIs); EntiGraph used gpt-4-turbo, so this is a deviation to check for quality.

**D. How to test freshness (build these tests; thresholds are mine to set after a first run).**
1. "Changed yesterday" test: take the previous day's change log, for each changed article ask the same question with `D` = day before and `D` = today; require different answers matching each edition and a valid quote. Pass = 100% quote validity and answer follows the edition (the same logic as HoH's current-vs-outdated and Set-the-Clock's per-year questions [snippet]).
2. Weights-leak test: ask without retrieval and with a stale edition injected; if the model answers from "memory" against the injected text, the adapter learned facts instead of use (confirmation bias risk, Xie [abstract]).
3. Stale-distractor test: retrieve with both editions present; measure how often the wrong edition is cited (HoH/Re3 failure modes [snippet]).
4. Refusal test: article whose edition is missing or not in force on `D` must give `unclear - needs expert`.
5. Pre-demo gate stays `python -m research.demo_check` (Qarshi, Yangiyo'l, Xatirchi). Add a fourth golden case built from a real amendment (for example the Law on Local State Power change of 12.11.2026) once its editions are in the store.
6. Always report N and per-check precision; do not cite any number from this file on stage unless it is labelled [full] or re-verified.

## 7. Gaps and what to verify before quoting
- Re-read in full: Soudani, Self-RAG, Allen-Zhu & Li, Ibrahim (replay %), Gupta (editing), Dhingra, Zhao, Cheng, FreshLLMs, HoH, Magesh. Everything marked [snippet] or [abstract] is unverified detail.
- Not found: lab-internal freshness architectures; model merging numbers; any benchmark of an explicit "as of D" instruction; production use of knowledge editing.
- Fetched via a summariser (treat as one step less certain than pdftotext): the RAFT table.
- Source URLs: arxiv.org/abs/{2312.05934, 2405.05904, 2409.07431, 2309.14316, 2403.10131, 2310.11511, 2403.01432, 2305.13300, 2405.09673, 2403.08763, 2401.07453, 2210.07229, 2403.07175, 2305.14795, 2402.18909, 2106.15110, 2402.16797, 2403.12958, 2401.12078, 2310.03214, 2503.04800, 2412.15540, 2508.12282, 2405.20362}; anthropic.com/engineering/contextual-retrieval.
