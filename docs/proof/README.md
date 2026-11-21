# Mezon-LM: the full record of how we trained, what we measured, and the proof

Folder: `D:\10_projects\mezon\docs\proof\`
- `logs/`: the raw logs and answers exactly as the machines wrote them (`sft.log`, `sft_result.json`,
  `bench.log`, `bench_think.log`, `cpt_pilot.log`, `preds_*.jsonl` = every answer the model gave).
- `charts/`: matplotlib charts drawn from those logs by `research/proof_charts.py`. Rerun it to redraw; nothing
  in a chart is typed by hand.
- `mezonbench_v1.jsonl`: the exam itself (400 questions with their answers).

Every number below comes from a file in `logs/` or from a script that printed it.

---

## 1. Words you need, ELI5

| Word | ELI5 | In our project |
|---|---|---|
| **Model / LLM** | a giant autocomplete that learned language by reading | Qwen3.8-27B, free and open (Apache-2.0) |
| **Parameters / weights** | the model's "brain cells": numbers it adjusts while learning | 27 billion |
| **Token** | a piece of a word, the unit the model reads | Uzbek costs ~4 tokens per word |
| **Training** | showing examples and nudging the weights so right answers become more likely | done on the RTX PRO 6000 (96 GB) |
| **LoRA / adapter** | instead of rewriting the whole brain, add thin "sticky notes" on top | run 1: 116.7M numbers (0.43 %); pilot: rank 128 |
| **Loss** | how surprised the model is by the right answer; lower = better. Loss 2.38 ≈ it gave the right next token ~9 % chance; 0.23 ≈ 79 % | the curves in the charts |
| **Held-out** | examples hidden during training, used only to check honestly | 91 in run 1; 100 per kind in the pilot |
| **Step** | one small update after reading a group of examples | run 1: 8 examples per step; pilot: 16 rows per step |
| **Epoch / pass** | reading the whole training set once | run 1: 2 passes = 208 steps; pilot: 1 pass = 1,012 steps |
| **SFT** | "copy the teacher's homework": learn to write given answers | run 1 |
| **CPT / law school** | reading lots of text so the knowledge goes in | the pilot now |
| **Replay** | mixing general lessons in so it doesn't forget other skills | 25 % Uzbek web (FineWeb-2) + 25 % instructions (Tülu 3) |
| **RL** | practice with a strict examiner: reward only correct, checkable answers | planned (stage 3) |
| **Benchmark / exam** | a fixed test to compare versions honestly | MezonBench v1, 400 questions |
| **Mode collapse** | the model learns one answer and says it to everything | what run 1 did |
| **Closed book** | answering from memory, no lookups | all exam runs so far |

---

## 2. What we did, in order (20-21 Nov 2026)

1. **Collected the data** onto our own AWS machines: all of lex.uz (166,155 documents, 185,049 old editions,
   ~120 GB), 61,049 court cases (list), replay sets (3.3 GB). OCR of 2,074 scanned PDFs runs.
2. **Run 1 (SFT), 52.8 min:** 825 examples written by our rule engine, 91 held out.
   - Held-out loss 2.382 → 0.0253 (pass 1) → 0.0232 (end). Chart `01_run1_sft_loss.png`.
   - It looked perfect, **but 672 of the 917 answers were the same "no defects" line.**
3. **Built the exam (MezonBench v1):** 400 questions generated from the law store and graded by it.
   Self-check: perfect answers score 100 %, all-wrong answers 0 %.
4. **Measured** (chart `02_mezonbench_results.png`):
   - Base Qwen: **101/400 = 25.3 %** (hierarchy 34/40, in_force 42/120, flip 25/120, lookup 0/120;
     238 "noaniq").
   - **Run-1 adapter: 0/400.** It answered every question with `{"xulosa": "positive", "kamchiliklar": []}`
     (mode collapse + forgetting) → retired.
   - Base with thinking (same 100 questions): 27 right / 4 wrong / 69 "noaniq", against 38 / 13 / 49 without:
     more careful (hierarchy 25/25), but not more knowledgeable.
5. **Research before the next step:** 8 research reports in `docs/research/` (LegalSearch-R1, Qwen family, open-lab
   recipes, frontier-lab guidance, keeping knowledge current, expert reasoning, law-school recipe, corpus
   refinery). Playbook: `docs/research/00_PLAYBOOK_mezon_lm.md`.
6. **Law-school pilot (running):** 4,601 law lessons (law text + 7 kinds of exact questions) + 1,730 Uzbek web
   documents + 10,019 instruction chats = **7,165,012 trained tokens**, LoRA rank 128, 1 pass = 1,012 steps,
   ~3 h. Chart `03_law_school_pilot_loss.png` (redraw for the latest).
   - Held-out before: law 0.8475, web 1.6968, instructions 1.7365.
   - Success = law falls, web and instructions don't rise; then the same exam.
7. **Next:** the refinery turns all 120 GB into clean dated text → lessons for all 166K documents → full law
   school → internship (real cases) → RL with the citation checker.

---

## 3. Why we trust these numbers

- The exam is **graded by the official law text**, not by a person or another AI.
- **Half the exam's articles are never taught** (hash rule `unseen()` in `research/mezonbench.py`), so we can tell
  "learned the law" (seen half) from "learned to reason" (unseen half).
- Every answer the model gave is saved in `logs/preds_*.jsonl`: anyone can re-grade it with
  `python -m research.mezonbench score <file>`.
- We report the bad results too (run 1 = 0 %). That is the proof the exam works.
