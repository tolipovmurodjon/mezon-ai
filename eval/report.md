# Mezon eval (2026-11-19)

Printed by `python -m eval.run`. Flagged ≠ illegal: every flag is a possible violation for expert review.

| Group | N | Any flag | Possible violation (high-confidence) |
|---|---|---|---|
| cancelled, with text | 20 | 10/20 = 50.0% | 5/20 = 25.0% |
| cancelled, E-qaror stages only | 268 | 8/268 = 3.0% | 4/268 = 1.5% |
| in force, not cancelled | 987 | 279/987 = 28.3% | 90/987 = 9.1% |
| draft | 497 | 20/497 = 4.0% | 1/497 = 0.2% |

**Citation validity** (quote is verbatim in the law edition in force on the decision date): 354/354 = 100.0%

**Lawyer precision:** not measured yet (0 reviewed flags).

Flags per rule and group:

| Group | Rule | Flags |
|---|---|---|
| cancelled, E-qaror stages only | R_discussion | 8 |
| cancelled, E-qaror stages only | R_expertise | 5 |
| cancelled, with text | R_business_3m | 6 |
| cancelled, with text | R_corruption_factor | 1 |
| cancelled, with text | R_discussion | 4 |
| cancelled, with text | R_double_repeal | 1 |
| cancelled, with text | R_duplicate | 1 |
| cancelled, with text | R_expertise | 4 |
| cancelled, with text | R_retroactive | 1 |
| cancelled, with text | R_tax_timing | 1 |
| draft | R_business_3m | 1 |
| draft | R_discussion_short | 19 |
| draft | R_draft_window | 1 |
| in force, not cancelled | R_basis | 60 |
| in force, not cancelled | R_business_3m | 184 |
| in force, not cancelled | R_competence_land | 2 |
| in force, not cancelled | R_corruption_factor | 19 |
| in force, not cancelled | R_discussion | 1 |
| in force, not cancelled | R_double_repeal | 4 |
| in force, not cancelled | R_duplicate | 10 |
| in force, not cancelled | R_retroactive | 4 |
| in force, not cancelled | R_tax_timing | 20 |

Read with care: 'cancelled' = cancelled on an official trigger (adliya, prosecutor, court) or E-qaror 'declared invalid'; most are individual decisions that procedure rules don't cover. 'In force' flags are not errors until a lawyer reviews them.
