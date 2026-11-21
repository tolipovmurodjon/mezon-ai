# Decision rule for scaling to v2 (written 21 Nov 2026, 06:45 Tashkent, BEFORE the v1.1 and tools results)

Pre-registered so tonight's numbers cannot be read to fit a wish. Applied mechanically when the results land.

## Inputs (all from `python -m research.mezonbench score`, CLEAN set, N printed)
- B0 = base closed book (preds_base.jsonl, already known: CLEAN 25.5 %, N=396)
- V1 = pilot v1.1 closed book (preds_cpt_v11.jsonl)
- BT = base + tools, 30 per family (preds_base_tools30.jsonl)
- VT = v1.1 + tools, 30 per family (preds_v11_tools30.jsonl)
- Baselines: trivial overall 35.0 %; always-majority per binary family ~0.50-0.525.

## Gate 1: did v1.1 learn something real (closed book)?
PASS only if ALL hold:
1. No "COLLAPSE?" flag: on flip and in_force no single answer > 65 % of predictions.
2. flip accuracy > 55 % AND in_force accuracy > 55 % (above the ~50 % majority baseline).
3. "noaniq" on at least 10 % of binary items (honest abstention kept).
4. hierarchy >= 90 %.
5. CLEAN accuracy above the 35.0 % trivial line by >= 5 points AND above B0 with a paired McNemar p < 0.05 on the
   same items.
Warning (checked 07:15 on pilot v1): McNemar vs base alone was p < 0.0001 for a model that had collapsed to one
answer, because base abstains on most items. Never pass Gate 1 on condition 5 alone.
Tool: `python -m research.bench_compare <A> <B>`.
If Gate 1 fails: no full-corpus law school; fix the lesson recipe (find which family failed) and rerun a pilot.

## Gate 2: is training worth it compared with tools?
On the 120 items scored for both BT and VT (and the same 120 from B0 and V1):
- If BT >= VT (no significant gap): tools carry the skill; spend the next GPU hours on tool use (internship traces,
  strict-judge RL on tool calls), not on a bigger law school.
- If VT > BT by >= 10 points (McNemar p < 0.05): training adds on top of tools; scale the law school to the full
  refinery corpus (v2) on the same recipe.
- Lookup (verbatim quotes) is judged with tools only: closed-book lookup is memory, the product never relies on it.

## Gate 3: no forgetting
Held-out web and instruction losses at the end of v1.1 must not be above their step-0 values (v1.1 step 744: web
1.624 < 1.735, instr 1.096 < 1.738: passing so far).

## Reporting
Every number with N and a 95 % CI; the always-majority and trivial lines printed beside it; the decision written as
one of: SCALE LAW SCHOOL / FIX RECIPE / INVEST IN TOOLS.
