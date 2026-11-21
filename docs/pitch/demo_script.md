# Mezon: demo script (LexHackathon 2026, Track 1)

Every number on screen comes from `research/scoreboard.md`, `/api/stats` or `/api/live-drafts` **on the day**. Re-read
the live numbers 10 minutes before going on stage; never say a number the screen does not show.

## The 60-second version (rehearse until boring)

> **(0-10 s)** "2023-yildan beri sudlar hokimlik qarorlari ustidan 3 182 ta da'voni qanoatlantirgan. Har biri — kimningdir
> yeri, biznesi yoki oilasi."
> **(10-25 s)** "Qonun har bir mahalliy qarorni qabul qilinishidan oldin tekshirishni talab qiladi. Lekin adliya
> mutaxassisiga 2-5 kun va 34 mingdan ortiq hujjat beriladi. Jamoatchilik muhokamasi esa ko'pincha bo'sh."
> **(25-45 s)** "Mezon har bir mahalliy qarorni o'sha kuni amalda bo'lgan qonun bilan tekshiradi. Mana, hozir: ochiq
> mahalliy loyihalarning [N] tasi qonunda belgilangan 15 kundan qisqa muhokamada — 24-modda, 3-qism, aynan."
> **(45-60 s)** "Har bir belgi — qonun matni va manba bilan. Qarorni inson qabul qiladi. Mezon adliyaga tekshiruvni
> qamrab olishda, tadbirkor va fuqaroga esa to'g'ri idoraga murojaat qilishda yordam beradi."

## 5-minute run of show

| Time | Say (gist) | Show / click |
|---|---|---|
| 0:00-0:40 | Hook: 3,182 claims satisfied since 2023 (34 % of 9,320 heard, to 2026 H1; stat.sud.uz, claims not decisions); 611 in 2025 alone; 2025 national report: every fourth draft act had corruption factors, and local hokimiyats are among the top sectors for corruption crimes (kun.uz 10.08.2026) | "Raqamlar" tab, first card |
| 0:40-1:20 | Why: the law requires the check (NLA art. 24, 40; order 3333 ¶6), but review is manual, 2-5 days; individual decisions are never posted | One sentence, no slide text |
| 1:20-2:10 | **Live, Gate 0:** today N of M open local drafts (budget-money allocations excluded: they spend, they do not set rules) close in under 15 days; read NLA art. 24 part 3 aloud from the screen; click one draft link to show it is real | "Jonli nazorat" tab, click a row |
| 2:10-3:10 | **Audit, Gate 2:** type `231-4-59-Q/24` → negative; open the duplicate flag (copy of 207, both quotes); click "Bugungi tahrir bilan solishtirish" on a Local State Power citation → "art. 25 is no longer in force" | "Qaror auditi" tab |
| (in the same slot) | **The chain:** "Adliya's representation cancelled 231 on 15 July. Six days later the same office adopted 269, with both defects again. Mezon flags it from the text alone." (`docs/cases/qarshi_chain.md`; re-check 207's status live first) | "Qaror auditi" tab: type `269-4-59-Q/24` (both defects again). Do NOT look for 231/269 in the queue: both have since lost force, and the queue lists only decisions still in force (Qashqadaryo top today: 416-4-57-Q/22, then Muborak's 332 and 282 with a dead article and a repeat repeal) |
| (same slot, 20 s) | **The dead article:** "68 decisions in 13 regions, signed after November 2024, rest on an article that had already lost force." Type `355-4-68-Q/25`: the decision's own words "Qonunining 6 va 25-moddalariga asosan" next to lex.uz's note "25-modda ... O'RQ-976-sonli Qonuniga asosan o'z kuchini yo'qotgan"; click "lex.uz da ochish" | "Qaror auditi" tab, the R_basis flag |
| (same slot, 20 s) | **Adliya's own form:** open "Xulosa loyihasi" on `265-4-60-Q/25`: the O'RQ-860 checklist with factor 24 marked and the norm quoted | Conclusion opens in a new tab |
| (same slot, 20 s) | **A 2025 case:** type `VII-3-1-5-77-K/25` (Xatirchi district Kengash): Mezon flags a retroactive burden (NLA art. 41). "The district adliya's representation No. 6/3-1 cancelled it on 21.02.2025. Mezon flags a defect consistent with it from the text alone." | "Qaror auditi" tab |
| 3:10-3:40 | **For citizens and business:** the "Siz uchun nima degani" box, the channels, "Tayyor murojaat matni" → copy | Same flag, scroll down |
| 3:40-4:20 | Proof + honesty: measured numbers with N; "flagged ≠ illegal"; lawyer precision (only if measured) | "Raqamlar" tab |
| 4:20-5:00 | Ask: one-region pilot for 90 days, an E-qaror export, a technical contact; KPIs per tranche | Closing line below |

Closing line: "Adliya har yili minglab kamchilikni topadi. Mezon ularni qaror imzolanishidan oldin ko'rsatadi; qarorni esa inson qabul qiladi."

## What we learned on 19 Nov (changes the answers)

- **90 % of officially cancelled decisions are individual, not normative** (255 of 282 with a type flag): re-registering
  a dehqon farm, allocating land, housing in place of demolished homes, guardianship. Citizens lose here. Procedure
  rules (discussion, expertise, 3 months) don't apply to them; the land rule (PF-6243 cl. 4) does.
- **The law-by-date proof:** PF-6243 cl. 4 removed "bekor qilish" (revoking land rights) from the ended district powers
  in the edition of 01.05.2026. Mezon applies the edition in force on the decision date: the same clause is flagged in
  2025 and not in June 2026. Show it with the "Bugungi tahrir bilan solishtirish" button.
- **Never say a recall number without saying how many texts it is measured on.** 273 of 287 "declared invalid" E-qaror
  records have no text; recall comes only from `eval/run.py`, both groups with N.
- 63 % of cancelling decisions state no reason (the representation itself isn't public): say "consistent with the
  representation", never "the reason was".

## Rules on stage

- Say "ehtimoliy qoidabuzarlik — ekspert ko'rib chiqishi uchun belgilandi", never "noqonuniy".
- Name bodies, never people. Only already-public cases.
- The design-code case only if the lawyer has confirmed NLA annex ¶102 applies to local drafts.
- The "business burden in force immediately" numbers only after the lawyer has checked a sample (they are title-based).
- If anything fails: switch to the backup video without comment.

## Backup

1. `docs/pitch/backup.mp4`: a 90-second screen recording of the run of show (record on Day 2 before 10:00).
2. Offline: the server runs on the laptop with no internet (all stores are local); only the lex.uz links need the network.
3. Printed one-pager with the three numbers and the NLA art. 24 part 3 quote.

## Top 5 jury questions

| Question | Answer (≤ 20 s) |
|---|---|
| E-qaror already shows skipped stages. | It records them one decision at a time; nobody aggregates them. We rank them, check them against the law as it read that day, and route them. |
| What if the AI is wrong? | Every flag carries the law's exact words and the decision's exact words; the citation is checked to exist and be in force on that date, or the flag is dropped. A human decides every flag (rules No. 3787). |
| Isn't this criticism of adliya? | It's your law and your portal. Mezon gives your experts a ranked queue in your own conclusion format, so the same people cover every decision. |
| Where does the data go? | Nowhere. Public sources only, processed on our own machines; the language model runs locally. |
| How many illegal decisions do you catch? | "On the cancelled decisions whose text we hold, Mezon flags X of N" (read X and N from `eval/report.md` on the day; 19.11: 10 of 20, 5 high-confidence; every one of 354 citations verified verbatim (run `python -m research.stage_numbers` on the day)). Never quote the 23 % flag rate on decisions in force as a false-alarm rate: ~90 % of it is the 3-month rule, which the lawyer is checking. Then: most cancellations are individual land decisions, which is exactly where our date-aware land rule works. |
| What does a regional adliya head get on Monday? | One page per region (`Adliya navbati` → choose a region → "Hudud hisoboti"): the review queue, decisions resting on a dead article, copies and repeat repeals, O'RQ-860 factors, and register clean-up. Qashqadaryo today: 40 decisions still in force flagged (read the live numbers from the page; run research.demo_check first). |
| How is this different from LexAI? / "We already have LexAI" | Respect first: "LexAI answers people's questions, and it does it well." Then the tested fact (docs/pitch/lexai_test_2026-11-19.md; say "in our test on 19 November"): asked whether LSP art. 25 was in force on 13.11.2025, and whether 355-4-68-Q/25's basis was right, LexAI's own advice was to check each cited article's edition of that date on lex.uz. "Mezon does exactly that step, automatically, for every local decision, every day, and drafts the conclusion." Close with the fit: ai.lex.uz lists draft expertise as in progress; Mezon can be its module for hokim and Kengash decisions. Never say LexAI is wrong or weak. |
| Laws change all the time; does Mezon keep up? | 193 new editions of our 38 core laws since 2023, about one a week. 977 of 1,066 decisions cite a law that changed after them; for 204 the cited article itself was reworded or removed. Last week (12.11.2026) article 6 of the Law on Local State Power changed: Mezon lists the 13 decisions in force that cite it for re-checking (`/api/law-changes`). A change is a re-check, never a violation (NLA art. 18 part 3; the amending act's final article orders bodies to bring their acts into line). |
| Is this real expertise or only a search? | Three of adliya's expertise types in one report: legal (14 checks, the law as of the date), anti-corruption (the O'RQ-860 checklist of 29 factors, 6 answered automatically today), linguistic (VMQ-662 cl. 9: words mixing Latin and Cyrillic letters, 112 of 1,066 decisions). The conclusion opens in Word for the expert to sign. |
