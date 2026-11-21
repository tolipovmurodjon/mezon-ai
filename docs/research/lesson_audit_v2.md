# Law-school v2 lessons: independent audit

Sample: 500 `law:lessons` rows (100 held-out + 400 random from the 6000 train file, seed 20261121, 16,583 lessons in the file). Script mix: 137 Latin, 156 Cyrillic, 207 Russian. Checker: `research/lesson_audit_v2.py` (does not import the generator; uses `mezon.tools.law_as_of` / `verify_quote` on the LawStore). Raw output: `data/interim/lesson_audit_v2.json`.

## Coverage limit (the main finding)
The LawStore holds 38 Latin acts. The lessons come from the refinery (about 300 core acts, `data/refinery/full`, present on neither the laptop nor the 6000; the box was unreachable). So only 15 of 500 lessons (3%) have an act in the store; 485 are uncheckable. Within those 15 lessons: 105 items, 31 correct, 0 wrong, 74 uncheckable (61 because the store history for the Tax Code starts 2020-01-01, 2 skipped editions, 11 no unit or parse).

| type | correct | wrong | uncheckable |
|---|---|---|---|
| addr2text | 4 | 0 | 10 |
| text2addr | 5 | 0 | 10 |
| cloze | 6 | 0 | 9 |
| inforce (Ha/Yo'q) | 3 | 0 | 12 |
| tf | 5 | 0 | 10 |
| since | 5 | 0 | 10 |
| verbatim | 3 | 0 | 8 |
| change | 0 | 0 | 5 |

Correct share on the store-checkable items is 31/31 = 100%, but N is small and 70% of items in those lessons could not be checked.

## Store-free consistency on all 500 (any script)
Verdict arithmetic and dates across items of one lesson: inforce 499/499 consistent, since 498/498, tf 497/499, change 313/319, cloze 245/245 where the lesson carries its own full text (243 not checkable).

## Wrong patterns
1. **Old and new edition have the same date (generator bug).** 6 change items and 2 tf items (1.9% of 319 change items, 8 lessons). Source `research/law_school_v2.py:541`: when `lesson_inputs` dropped the earlier unit, `prev` is None and `valid_from` falls back to the unit's own date, while `prev_text` still exists. Examples: `ls2_val.jsonl:305` (163-modda 2-qism, Xo'jalik protsessual kodeks: "2002-10-22 dan 2002-10-22 ga", answer «—» → «(protestini)»); `ls2_samp.jsonl:95` ("Сравните редакции 2025-02-21 и 2025-02-21", plus a tf that says "text of the previous edition" with the same date). Another lesson, `ls2_val.jsonl:91`, is the same bug on Cyrillic text.
2. **"kirish qismi N" / "преамбула N" addresses (suspect, not provable here).** 268 of 500 lessons (54%) use this address. For O'RQ-456 `116-kirish qismi` is a numbered amendment clause, not a preamble; for ЗРУ-600 `преамбула 205` is a body sentence. The label comes from the refinery path type (`human_path`, `WORDS['pre']`). It teaches addresses that do not exist on lex.uz. Needs a check against the refinery, which was not reachable.
3. **Store cannot confirm large-code lessons (store side, not a lesson error).** Tax Code 472-modda 1-qism: the lesson names an edition 2021-04-21; the store has one unit 2020-01-01..2025-06-17. 63 items fall here (e.g. 360-modda 6-qism, dates before 2020).

## Verdict on origin
Confirmed generator bug: pattern 1 (about 2% of change items). Pattern 3 is the store. Yes/no verdicts, stated dates and quotes were not found wrong in any of the 31 store-verified items, but the audit cannot vouch for the other 97% until the refinery `unit_versions` or a store with those 300 acts is available.

Next step: rerun `python -X utf8 -m research.lesson_audit_v2 OUT.json sample.jsonl` on the 6000 with a LawStore built from the refinery.
