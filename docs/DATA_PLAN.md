# Mezon data plan v2: every source, why we need it, what to take, how, and when

Written Fri 20 Nov 2026, ~18:00 Tashkent, after the mentor meeting and Gemini's audit. Replaces the "download
everything" mode with a plan an expert would follow. Feature freeze Sat 10:00.

## The one idea that decides everything

Mezon checks a **local decision** against **the law as it read on that date**, and routes the problem to whoever fixes
it. So every source is one of four roles. A source that fits no role is "later".

| Role | Question it answers | Sources |
|---|---|---|
| **A · The law** (the ruler) | "What did the law say on date D?" | lex.uz (+ sharh.lex.uz commentary, if licensed) |
| **B · The decisions** (what we audit) | "What did the hokim / Kengash decide?" | E-qaror, lex.uz local decisions, regulation.gov.uz drafts |
| **C · The verdicts** (the answer key) | "Was it later found wrong, by whom, why?" | lex.uz cancellation notes, E-qaror "declared invalid", public.sud.uz, stat.sud.uz |
| **D · The world around it** (routing, competence) | "Which body may do this? Who fixes it? What can a citizen do?" | E-qaror-respublika, gov.uz, my.gov.uz |

**Training vs checking:** the model *learns* from A (language of law) and from B+C pairs (decision → verdict with the
reason). The *checker* uses A as ground truth. B is never trusted: E-qaror tags are noisy, which is exactly why we
check them against A.

## Source by source

### 1. lex.uz · Role A (+ B for local decisions, + C for cancellations) · MUST · running
- **Has:** 166,705 documents (4 languages), every edition by date, annexes inline, files (ZIP/PDF/DOC), images,
  amendment history, cites / cited-by, legal-analysis cards, cancellation notes ("LexUZ sharhi").
- **We take:** everything (pass 1 + pass 2). On the L40S, 20 workers, ~20 req/s.
- **What we may still miss:** (1) scanned PDFs with no text layer inside local-decision ZIPs → measure how many,
  then OCR (Tesseract uzb / uzb_cyrl / rus on the L40S, or Qwen's vision); (2) "HUJJATGA O'ZGARTIRISH KIRITILMOQDA"
  banner → mark the text `provisional`; (3) the twin-key bug (fixed 17:00, re-check running).
- **When:** pass 1 ~22:00 tonight by itself; pass 2 Saturday.

### 2. public.sud.uz · Role C · HAVE the list
- **Has:** published court rulings. Administrative category: 61,049 (all the list returns), each with court,
  instance, case number, category, judges, **result**, date. The ruling PDFs are behind "Robot emasman".
- **Your question, "can court decisions be wrong too?"**: yes, a first-instance ruling can be reversed on appeal or
  cassation (the list has the instance, so we can see that). But Mezon does **not** audit courts. For Mezon a court
  ruling is **evidence**:
  - "claim satisfied" (FULFILLED / PARTIALLY) against a hokim decision = strong label "this decision was found
    unlawful" (that is what lex.uz cancellation notes also cite: "hal qiluv qarori", "haqiqiy emas deb topil");
  - "claim refused" ≠ "decision is lawful" (the citizen may simply have lost on procedure). Weak signal only;
  - the ruling **text** is the most valuable part (it names the violated article), so the best training data
    for "why it's wrong" is in those PDFs.
- **We take:** the list (done). PDFs: only a **human** may tick "Robot emasman" (Boss, for a small sample, e.g. 100
  rulings on hokim decisions) or the Supreme Court gives an export. Claude never bypasses the check.
- **When:** done for the list; sample of PDFs only if Boss has time.

### 3. stat.sud.uz · Role C (numbers for the pitch) · SHOULD · tonight, small
- **Has:** quarterly court statistics (administrative cases: filed, satisfied, refused, by region, by body type).
- **We take:** the administrative tables, all quarters available, by region. These are **official numbers** for the
  stage ("in 2025 courts found N hokim decisions unlawful"), each with its URL.
- **How:** plain pages, a few dozen requests. Needs the laptop's Uzbek IP (or the tunnel).

### 4. e-qaror.gov.uz · Role B (+ C) · MUST (subset) · needs Boss's Chrome
- **Why it matters most:** it *is* the object Mezon audits (908,558 decisions), and the mentor confirmed its data is
  bad. Both training **and** checking:
  - **checking:** each decision's text (PDF) + its number → run all checks → this is the demo and the product;
  - **training:** decision text = input; verdict = output, where the verdict comes from C (cancellation reason,
    "declared invalid", court), **never from E-qaror's own tags**;
  - **its flaws are a finding** (declared-invalid under-filled 275 vs 933 court invalidations; green expertise stage
    without a real expertise; is_normative wrong): put them in the pitch as "why Mezon is needed".
- **Best subset (agree with Gemini):** (1) all `release=200` (declared invalid, ~275) + PDFs; (2) all `is_normative=1`
  (~11,000 list rows) + PDFs of the last 1-2 years or one pilot region (Qashqadaryo: Qarshi, Yakkabog'); (3) the full
  list (919k rows, ~19 h) only if time allows. All 919k PDFs = ~16 days → **ask Adliya for an export**; that request is
  itself a pilot step.
- **How:** Boss's Chrome console script + laptop receiver → L40S (800 rows so far). Needs free laptop memory.

### 5. e-qaror-respublika.gov.uz · Role D (parent acts) + future B · SHOULD
- **Has:** acts of ministries, agencies, collegial bodies, and **"Appelyatsiya kengashlari qarorlari"** (appeal-council
  decisions: verdicts on complaints against bodies; possibly good labels).
- **Why:** check 5 (mandate drift) needs the **parent act** a local decision says it executes; ministry orders are the
  roadmap's step 2.
- **We take:** the list (`e-res.ecdn.uz/v2/documents?page=N`), then the appeal-council decisions. Same Chrome script.

### 6. sharh.lex.uz · Role A (commentary) · MAYBE · licence first
- **Has:** article-by-article commentary to codes and laws (how lawyers read the article). Excellent for teaching legal
  reasoning.
- **Licence:** NOT verified (the site is a JS app; the fetch saw no terms). Earlier notes say training / publishing
  needs a licence. **Action:** open the site in Chrome, read the footer / "Foydalanish shartlari". If it says open
  (e.g. CC-BY), take it all; if "barcha huquqlar himoyalangan", ask Adliya (the same letter as the E-qaror export).

### 7. regulation.gov.uz (+ regulation.adliya.uz) · Role B (drafts) · MUST for Gate 0 and checks 9-11
- **Has:** drafts in public discussion (~118,000 ids; 31,390 local), discussion dates, proposals count, text (local
  drafts as PDF).
- **"Drafts are not the approved version"**: exactly why we need them. Check 9 (adopted before the discussion ended),
  10 (adopted with no draft), 11 (draft vs adopted: what changed after the public saw it). The live demo (draft
  118221) is a draft.
- **We take:** all local drafts since 2021 with dates + PDFs (we have 3,572 recent ones in the old store). Re-sync on
  the L40S via the tunnel (Uzbek IP) or the laptop.

### 8. gov.uz · Role D · LATER (roadmap), small slice now
- **Has:** every government body's page: structure, functions, territorial units, leaders, contacts, news.
- **Useful for Mezon:** (1) **routing**: which district adliya / body gets the case, with its address; (2)
  **competence**: what each body is for (supports check 2). That is a few thousand pages of structure and contacts.
- **Not useful for Track 1:** biographies of officials (personal data, no audit value; our rule is "no named-hokim
  shaming"). Skip them.
- **When:** after the freeze, unless routing in the demo needs real addresses.

### 9. my.gov.uz · Role D (citizen side) · LATER (roadmap)
- **Has:** the catalogue of public services: what each service is, who provides it, documents needed, fees, steps.
- **Useful:** the citizen app's "what can I do now?" (appeal routes, services), and your bigger idea: an assistant
  that teaches people the services they don't know exist. That is a **second product**, not Track 1's auditor.
- **When:** after the hackathon. Taking the catalogue is cheap (a few thousand pages) if you want it in the brain.

### 10. Government Telegram channels (and news on gov.uz) · Role D (early signals) · LATER
- **Has:** official channels of ministries, hokimliks, Adliya, courts: announcements, new decisions, drafts put to
  discussion, "a decision was cancelled" news, often days before lex.uz lists them.
- **Useful:** an **early-warning feed** (a hokimlik announces a new fee or a demolition → Mezon looks for the decision)
  and real-world cases for the pitch. Not law, not labels: every claim must be confirmed in lex.uz / E-qaror before a
  flag.
- **How:** Boss sends the list of channels (screenshots are fine); we read only **public** channels, keep posts with
  date + link, store no personal data of citizens. After the freeze.

## What wins on Saturday (Gemini is right here)
Judges look at a **live demo**, **lawyer-confirmed numbers** and **one output experts want every day**: the
**Order-3333 draft conclusion** (Word), with verbatim quotes from the edition in force on the decision date and the
O'RQ-860 checklist filled. Collecting 166k vs 117k documents does not change their decision.

**Tonight, in order:**
1. lex.uz finishes by itself (no action).
2. Rebuild the law store from it → point-in-time articles + change log.
3. E-qaror subset (declared invalid + normative) → join with lex.uz → labels.
4. stat.sud.uz numbers (small).
5. Independent exam: Bryusli + Asila write 40 questions not in the training data (10 higher-law conflict, 10 mandate
   drift, 10 O'RQ-860 factors, 10 clean controls); and finish `/review` (60 flags).
6. SFT on the L40S; report **rule-bench (N=149)** and **lawyer exam (N=40)** separately, never mixed.
7. The demo: Qarshi first (cancelled on adliya representation), Yakkabog' second (dead article 25 → 21¹, "fixable
   defect"), then draft 118221. Output = the Order-3333 conclusion document.
8. Laptop: clean restart; better, run the demo API from the L40S over an ssh tunnel so a frozen laptop can't kill it.

## Rules that stay
No captcha bypass · no hidden or blocked APIs from Claude's tools · polite rates (lex.uz ≤ 25 req/s, others ~1 req/s)
· no personal data (party names, biographies) · decision text never to a cloud AI · flagged ≠ illegal · no
endorsement claims · licences checked before training on a source.
