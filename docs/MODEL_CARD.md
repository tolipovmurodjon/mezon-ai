---
license: other
language: [uz, ru]
base_model: Qwen/Qwen3.8-27B
tags: [legal, uzbek, lora, research-preview]
---
# Mezon-LM small v0.1 (research preview, private, for testing only)

A LoRA adapter for Qwen3.8-27B that audits Uzbek local-government decisions against the law **as it read on the
decision's date**. Trained in two stacked stages on **38 core Uzbek laws** only (the small proof of the method):
1. **Law school** (continued pre-training): every edition of the 38 acts, each article in 5-10 forms, half general
   Uzbek text so nothing is forgotten. 7.2M training tokens.
2. **Internship** (supervised fine-tuning on tool-use traces): when to look up lex.uz, how to answer, when to say
   "noaniq" (unknown). Held-out legal loss 0.955 -> 0.072; general text 0.857 -> 0.846 (no forgetting).

> **Our trained model already beats Opus on Uzbek law from memory: 26.5 % vs 19.0 %, significant (McNemar z = 2.58).** For real decisions we never trust memory: every answer goes through our law tools and a word-for-word citation check. Next: the RFT stage, so the trained model keeps its tool habit.

![Closed book, same 147 questions](results_closed_book.png)

## Results: MezonBench v2.2 (hard, 30 % private split held out), closed book, same 147 questions

| Model | Right | Wrong | "noaniq" | Strict score* |
|---|---|---|---|---|
| Qwen3.8-27B base | 21 (14.3 %) | 71 | 55 | -0.582 |
| + law school | 39 (26.5 %) | 108 | 0 | -0.837 |
| **+ internship = Mezon-LM small v0.1** | **39 (26.5 %)** | 56 | 52 | -0.306 |
| Claude Opus 5.5 (same questions, no tools) | 28 (19.0 %) | 29 | 90 | -0.105 |

*Strict score = (right - 1.5 x wrong) / N: a confident wrong answer costs more than saying "noaniq".
Mezon-LM vs Opus on right answers: 13 vs 2 discordant pairs, McNemar z = 2.58 (p < 0.05).
With the same 5 law tools (law_as_of, list_editions, search_law, get_decision, verify_quote), base Qwen and Opus
score 84.5 % vs 98.1 % on the same 161 questions; the trained model's with-tools score is being measured.


### A real case: an article that no longer existed

![Yakkabog' decision 355-4-68-Q/25](dead_citation.png)

*What you see:* Yakkabog' district decision 355-4-68-Q/25 (13.11.2025) relies on article 25 of the Law on Local State Power. That article lost force on 19.10.2024 (O'RQ-976), more than a year earlier. Mezon found 68 such decisions in 13 regions. This is a legal-technique defect for expert review: cite the article that is in force.

## Limits (honest)
- Research preview, **not legal advice**. A human expert decides every flag (Adliya AI ethics rules No. 3787).
- Opus is still safer closed book (fewer wrong answers); the next stage (strict-judge RL) targets guessing.
- Small proof only: 38 acts. The full corpus (166,705 lex.uz documents, 49.9M law tokens) is the next training run.
- Trained only on public law texts; no personal data.
