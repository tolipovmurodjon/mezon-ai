# Mezon north star: a legal engine that reads every word, knows the law as it read on any day, and proves every claim

## Context

Boss wants an agent that understands Uzbek law like a top lawyer, works in real time, and beats LexAI. Below:
the north-star design, then the cut we can ship by Sat 21 Nov 10:00. Built on 3 research reports (19 Nov):
the Uzbek legislation system, the legal-AI state of the art, and the live data sources. Earlier measured work
(research/, data/interim/, 53 tests) is reused.

Why we can win: every rival is Q&A only. LexAI (Adliya, Dec 2024) answers questions; Tuzuk drafts contracts; KOICA's
$14.5M project (2026-30) does consultations and drafting. **Nobody audits a government decision against the law as it
stood on that day, and nobody verifies every citation.** The best Western tools still hallucinate on 17-33% of
queries, often by citing law that was no longer in force (Stanford, Magesh 2024). Our design attacks exactly that.

## The law, in one picture (what the engine must encode)

- **Staircase:** Constitution > laws (incl. codes, constitutional laws) > Oliy Majlis chamber resolutions > President
  (PF, PQ, F) > Cabinet (VMQ) > ministry acts (registered by Adliya) > local acts (hokim, Kengash). NLA Law O'RQ-682 art. 6.
- **Conflicts (NLA art. 18):** higher force wins; equal force → later wins; doubt between a person and the state →
  the person wins (part 6, since 2024).
- **A local normative decision is valid only if:**
  1. it is a **qaror**, not a farmoyish (NLA art. 16; order 3333 ¶1-2);
  2. it is adopted and registered in **E-qaror**, or it has no legal force (Local State Power art. 6; VMQ 390 ¶2);
  3. it has a **positive regional adliya conclusion** (order 3333 ¶6, ¶92: 2 / 5 working days);
  4. it went to **public discussion for ≥ 15 days** (NLA art. 24);
  5. if it burdens business, it takes effect **≥ 3 months after publication** (NLA art. 40) and is agreed with the
     **Business Ombudsman** (NLA annex ¶102, to re-verify);
  6. it stays within **competence** (Local State Power arts. 6, 21-1, 24) and doesn't regulate a matter reserved to
     law (NLA art. 11);
  7. it is **not retroactive** in a burden (NLA art. 41).
- **Who cancels:** a higher hokim (art. 21-1, except land and property rights already created), the Kengash (art. 24),
  the Senate (art. 26), the President or Cabinet, a prosecutor protest (art. 29), a court (Admin Procedures art. 59),
  or an adliya representation.
- **How law changes:** amendments are inline ("…tahririda") with links to earlier editions. lex.uz keeps every
  edition (`?ONDATE=dd.mm.yyyy 00`; ~38 editions for the Law on Local State Power). A red "o'zgartirish kiritilmoqda"
  banner means an amendment is in force but not yet merged. Bills wait 4-6 months between the Senate and the
  signature, so they are *pending*, not law.

## North-star architecture: 7 layers

1. **Sync (real time).**
   - lex.uz RSS `/uz/rss` (new acts, polled every few hours);
   - a daily check of the editions and banner of ~30 core acts;
   - the respondents panel of the Law on Local State Power (2,727 citing acts: a free feed of new local decisions);
   - regulation.gov.uz + regulation.adliya.uz drafts;
   - E-qaror (slow sample, or an export from Adliya);
   - public.sud.uz (67,547 administrative rulings in the decisions-of-bodies category, with outcomes);
   - parliament and Senate channels as *pending law*.
2. **Point-in-time law store.**
   - Every edition of every core act, split by article / part / clause using lex.uz element ids, with `valid_from`
     and `valid_to` and a provisional flag while a banner shows.
   - Edges: amends / repeals / cites / implements, typed from titles and "tahririda" notes.
   - SQLite + FTS5 now (one file, no server); pgvector embeddings later on the box.
3. **Reader.**
   - A decision parser: preamble basis citations, numbered clauses, annex (research/textnorm.py).
   - A norm frame per clause: who · must / may / must-not · what · deadline · condition · exception · sanction ·
     money. The LLM proposes JSON; the schema plus a verbatim-quote rule accept it or drop it.
4. **Legal compiler (deterministic rules, zero hallucination).** The 7 validity conditions above, the conflict rules,
   time travel (the law as on date D), duplicates and double repeals, the draft window, and the 3-month business rule.
   Each rule returns a Flag with evidence and citations (`mezon/report.py`).
5. **Reasoner (local Qwen on the box, never from memory).** Only for open questions: does clause X conflict with
   retrieved norm Y as on date D? Mandate drift against the parent act? Is a business burden added? It must return a
   verdict plus two verbatim quotes, or "unclear".
6. **Verifier (the UZEX checker, legal version).** Every citation must exist in the store, in the edition in force on
   the decision date, and its quote must be a verbatim substring of that edition. The hierarchy must be right.
   Otherwise the claim is dropped and marked "unclear — needs expert". Errors are measured with Stanford's labels:
   ungrounded / misgrounded / fabricated.
7. **Output and routing.**
   - Adliya's own format: positive · positive with fixable defects · negative, each defect → article → quote.
   - Expert queue ranked by legality risk (never "corruption %").
   - A side-by-side view; a plain explanation for the affected business or citizen; one-tap routing to the existing
     channels.

**Evaluation (the trust weapon: publish the exam, which LexAI doesn't):**
- **Labels:** lex.uz cancellation triggers, court ruling outcomes (satisfied = the decision lost), and E-qaror
  "declared invalid".
- **Answer key:** lawyer keys from two annotators, with kappa.
- **Tests:** consistency ×3 and paraphrase.
- **Metrics:** recall on cancelled decisions; precision on lawyer-reviewed flags; 100 % citation validity.

## The cut we ship by Sat 10:00

| Day | Build | Proof |
|---|---|---|
| Thu 19 | (a) Law store: ~30 core acts × all editions (NLA, Local State Power, E-qaror VMQ 390, order 3333, Land Code, Tax Code local parts, Budget Code art. 99, Ombudsman law, Admin Procedures, Constitution, PQ-3666). (b) The compiler: rules 1, 3, 4, 5 (3-month), 6 (form) + duplicates + draft window + "cited act in force on date". (c) Verifier. (d) Court rulings: 300 PDFs (needs Boss's yes) → outcome labels. (e) Lawyer reviews the flags | pytest on golden cases; store answers "art. 6 of 913-XII as on 21.06.2024" with the right edition |
| Fri 20 | Reader + reasoner on the box (Qwen3.8-27B FP8, already installed) for norm frames + conflict + mandate drift; FastAPI; expert web UI (static HTML, our taste); RSS + respondents watcher | end-to-end report on Qarshi, 118221, the design-code; live feed shows today's new local decisions |
| Sat 21 | Eval run → `eval/report.md`; consistency ×3; backup video; freeze 10:00 | numbers printed by scripts only |

Demo: open 7,066 (claims satisfied) → live: a decision published this week, audited in seconds → Qarshi (blind) →
draft 118221 (before adoption) → close on the design-code if the lawyer cites ¶102.

## Critical files

- **Reuse:** `research/textnorm.py`, `research/regnum.py`, `research/polite_http.py`, `research/duplicates.py`,
  `research/regulation_window.py`, `mezon/report.py`, `mezon/config.py`.
- **New:** `mezon/lawstore/{fetch,parse,store}.py`, `mezon/rules/*.py`, `mezon/verify.py`,
  `mezon/reader/{frame,llm}.py`, `mezon/sync/{rss,respondents}.py`, `mezon/api/main.py`, `mezon/web/`, `eval/run.py`.

## Verification

- pytest: point-in-time lookup (an article's text differs across two editions; a 404 date resolves to the latest
  edition on or before it).
- Each rule on its golden case and a clean control.
- The verifier rejects a fabricated article, a repealed edition and a non-verbatim quote.
- An end-to-end report for 3 golden decisions; the eval script prints recall, precision and citation validity with N.
