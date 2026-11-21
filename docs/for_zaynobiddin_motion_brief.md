# Mezon: brief for the motion video and the platform design

For Zaynobiddin, from Murodjon. Written 21 Nov 2026. Everything here is real and measured unless marked
**[target]**. Numbers marked [target] must not appear on screen as results. Show them only as goals, or wait for the
real number.

---

## 1. One sentence

**Mezon is an AI legal expert for Uzbek law. It knows every law as it read on any day, and checks local government
decisions against it, citing the exact article and the exact words.**

"Mezon" means *the balance / the criterion* (the scales of justice).

---

## 2. The problem (what hurts today)

1. **Uzbekistan has a huge, constantly changing body of law.** lex.uz holds **166,155 legal documents**, and
   **45,393** of them have been amended over time: **185,049 older versions** in total. A law can change several
   times a year. To check a decision correctly you need the law **as it read on that exact date**, not today's text.
2. **Local decisions are many and nobody watches most of them.** Hokims (governors) and local Kengashes (councils)
   adopt decisions every day. The E-qaror system holds **~908,000 local documents** since July 2021. Each new
   normative draft gets only **2-5 working days** of legal review at the regional justice department.
3. **The public rarely speaks up.** In our random sample of 92 recent drafts on regulation.gov.uz, **94.6 % got zero
   public comments**.
4. **Mistakes happen and get cancelled later, after they have already hurt people.** Real, public examples:
   - **Qarshi:** a decision copied an earlier one word for word, 15 days later, while the first was still in force,
     and repealed an act that was already repealed. Cancelled on a justice department representation.
   - **Yangiyo'l:** land-tax coefficients set without the required public discussion. Cancelled and re-adopted.
   - **Xatirchi:** a council decision put a burden on a period *before* it was adopted (retroactive). Cancelled on a
     justice department representation.
   - **A dead article:** article 25 of the Law on Local State Power **lost force on 19.10.2024**, yet **68 decisions
     adopted in 2025 still cite it**.
5. **General AI can't be trusted with this.** Stanford researchers (Magesh et al., 2024) found that the best
   commercial legal AI tools **make up or misstate the law 17-33 % of the time**, often by quoting a version that was
   no longer in force. General chat models don't have Uzbek law by date at all.
6. **Courts see the cost.** **61,049** administrative court cases are published; in **34.7 %** the citizen or
   business won against the authority.

---

## 3. The solution (what Mezon does)

**Three gates, like a security check for every local decision:**

| Gate | When | What Mezon does |
|---|---|---|
| **0 · Before** | while a draft is open for public discussion (10-15 days) | checks the draft and helps a lawyer file a review through the official portal |
| **1 · Slipped** | a decision appears with no draft, or before the discussion ended | flags the missing step |
| **2 · After** | the day a decision is published | full audit: legal basis, competence, form, conflicts with higher law, deadlines, duplicates, dead articles |

**Every finding comes with proof:** the law, the article, the edition on that date, and the exact quote, plus a link
to lex.uz. If Mezon can't prove it, it says **"unclear, needs an expert"**. A human expert always decides.

**The output looks like the justice department's own conclusion:** *positive* · *positive with fixable defects* ·
*negative*, each defect pointing to an article and a quote. The reviewer starts from a pre-filled conclusion instead
of a blank page.

**Then it routes the case** to the people who fix it (district justice department, Business Ombudsman, prosecutor,
court, the affected person) with a pre-filled appeal. Mezon never votes, never shames anyone, never calls a decision
"illegal": it says "possible violation, flagged for expert review".

---

## 4. The big goal: our own Uzbek legal AI model

**Mezon-LM: a free, local Uzbek legal expert model.**
- Built on an open model (Qwen, 27 billion parameters), trained on **all of Uzbek law**.
- Runs on our own computers: **decision texts never go to a foreign cloud AI**.
- Learns like a lawyer, in 4 schools:
  1. **Law school:** reads every law and every version (pre-training).
  2. **Internship:** learns from real cases: why decisions were cancelled, what courts decided.
  3. **Practice with a strict examiner:** reinforcement learning, where the reward is only for the right answer
     with an exact, correct-date citation.
  4. **Morning briefing:** each day it reads what changed in the law.
- **[target]** Beat the top general AI models (Claude Opus, GPT, Gemini, DeepSeek) on Uzbek law, proven on our own
  public exam. Not proven yet; see the benchmark scene below for what is measured today.

---

## 5. The data (opening scene material)

Real sources and real counts (as of 21 Nov 2026):

| Source | What it gives | Number for the screen |
|---|---|---|
| **lex.uz** (national legislation database) | every law, decree, resolution, local act, and every past version | **166,155** documents · **185,049** versions |
| **public.sud.uz** (court rulings) | administrative court cases and outcomes | **61,049** cases |
| **stat.sud.uz** (court statistics) | how often decisions lose in court | quarterly statistics |
| **e-qaror.gov.uz** (local decisions system) | hokim and Kengash decisions, adoption stages | **~908,000** documents in the system |
| **e-qaror-respublika** | ministry and agency acts (the "parent" acts) | national level |
| **regulation.gov.uz** (draft discussion portal) | drafts open for public comment | **40,383** drafts (31,390 local; portal statistics, 18 Nov) |
| **data.egov.uz** (open data portal) | official registers | open datasets |
| **OCR of scanned documents** | text from 2,074 scanned PDFs | **2,074** scanned PDFs |
| **gov.uz, my.gov.uz, official Telegram channels** | which body does what, citizen services, news | later |
| **Open training sets** (FineWeb-2 Uzbek, Tülu 3) | normal Uzbek and general skills | 3.3 GB |

Total on our machines today: **~120 GB of lex.uz pages**, plus courts and the rest.

**Logos:** use the official site logos only as *data source* labels, never in a way that suggests these bodies
partner with or endorse Mezon. Mezon is a LexHackathon 2026 project (Ministry of Justice, Track 1); no endorsement
unless it is in writing.

---

## 6. Benchmark scene: real results only

**MezonBench v1: our own exam, 400 questions,** generated from the official law texts and graded automatically by
those texts. No human or AI judge. Four kinds of questions:
- **hierarchy:** which act wins in a conflict?
- **in force:** did this article exist on this date?
- **which version:** which of two wordings stood on this date?
- **quote:** quote the article word for word as on this date.

**Measured on 20 Nov 2026, closed book (no lookup), Qwen 27B as downloaded:**

| | Score |
|---|---|
| All 400 questions | **25.3 %** |
| Hierarchy | **85 %** (knows how law works in general) |
| Which version stood on a date | **21 %** (worse than a coin flip when it guesses) |
| Quote an article | **0 %** (cannot quote a single Uzbek article) |
| With "thinking" on (100 questions) | hierarchy **100 %**, wrong answers 13 → 4, but it says "unclear" more |
| A naive first training attempt | **0 %**: it answered every question with the same sentence. That's why we built the exam. |

**The story to animate:** *a smart model that doesn't know Uzbek law → our exam reveals it → law school, practice,
morning briefing → the score climbs.* For the "beating other models" part, build the chart template (bars for
Mezon-LM, Claude Opus, GPT, Gemini, DeepSeek) but **leave the values empty**. Murodjon sends the real numbers when
the comparison is run on the same exam with the same tools. The law-school pilot is training now; its first score
comes on 21 Nov.

---

## 7. Real use cases (for scenes)

| Who | The moment | What Mezon shows |
|---|---|---|
| **Business owner** | "The hokim's new decision puts a duty on my shop from next week." | Law on Normative-Legal Acts, art. 40: a new business duty takes effect **no earlier than 3 months after publication** → "possible violation" + the quote + where to appeal |
| **District justice expert** | 2 days to review a draft | a pre-filled conclusion in their own format, each defect with article and quote |
| **Citizen** | "Can they take my land for a business centre?" | the law on taking land for public needs: a business interest is **not** on the list of public needs |
| **Prosecutor / reviewer** | "Which decisions cite dead articles?" | 68 decisions from 2025 citing an article that died on 19.10.2024 |
| **Lawyer** | "What did the Land Code say on 6 Dec 2020?" | the exact version of that day, with the link |

---

## 8. Motion video: suggested structure (60-90 s)

1. **Opening (0-10 s): "Data comes in."** Logos and icons of the sources fly in from the edges, playful, and land
   in the centre. A big counter climbs: **0 → 166,155 laws**, then **185,049 versions**, **61,049 court cases**,
   **~908,000 local decisions**. Then the counters merge into one glowing scale (the Mezon balance).
2. **Problem (10-25 s):** a stream of decisions; a calendar flipping; one article fading out ("lost force
   19.10.2024") while decisions keep citing it (**68**). Text: *"Laws change. Decisions don't notice."*
3. **Why not ChatGPT (25-35 s):** a chat bubble quoting a law; the quote cracks. *"Legal AI tools misstate the law
   17-33 % of the time."* (Stanford, 2024)
4. **Mezon (35-55 s):** a hokim decision scrolls in; Mezon highlights a clause; a side panel slides out: the
   article, the date stamp, the exact quote in a citation card, the verdict chip *"possible violation, expert
   review"*. Then the routing: one tap to the right office.
5. **The model (55-75 s):** the 4 schools as 4 steps; the exam score bar climbing from 25 %; empty bars for other
   models waiting (no fake values).
6. **Close (75-90 s):** *"Mezon. Every decision, measured against the law of its day."* LexHackathon 2026.

**Tone:** calm, precise, trustworthy, like a justice ministry tool, not a startup hype video. No accusations, no
faces of officials, no "bad hokim" imagery.

---

## 9. The platform (screens to design)

1. **Expert mode (web, the main product):** a queue of decisions ranked by review priority; open one → the decision
   on the left, the checks on the right; each finding is a card (title, article, date of the law version, exact
   quote, link); the conclusion at the top (positive / fixable defects / negative); buttons: approve, reject, edit,
   send.
2. **Side-by-side view:** the decision vs the higher act it implements, differences in red.
3. **Law time machine:** pick an article and a date → the exact text that day, with a timeline of versions.
4. **Region dashboard:** counts of flagged decisions by region and by kind of defect (no ranking of people).
5. **Lawyer review screen:** one flag per card, keys 1/2/3 to judge it (already exists in our prototype).
6. **Citizen app (thin):** "decisions that affect me", a plain explanation, one tap to the right official channel.

Design rules: **no emoji in the app UI**; Uzbek Latin first (Cyrillic and Russian later); every claim on screen has
its source one tap away; the words "illegal" and "corrupt" never appear.

---

## 10. What not to show

- Any number not in this file (ask Murodjon first).
- "Better than Claude / GPT" as a result before the comparison is measured.
- Real citizens' names, faces of officials, or anything that looks like an accusation.
- Logos arranged as if the government endorses Mezon.
