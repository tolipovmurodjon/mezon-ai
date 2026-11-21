# Mezon: the story (simple version, for design and video)

For Zaynobiddin. No technical words. Everything here is true; numbers are real.

---

## In one line
**Mezon checks local government decisions against the law, before and after they're adopted, and shows the
justice department's expert exactly where a decision may break the law, with proof.**

"Mezon" = the scales, the measure. Every decision gets weighed against the law of its day.

---

## 1. Why: the problem, as a story

**Meet Dilnoza.** She runs a small bakery in a district town.

One morning a new decision from the district hokimiyat puts a new duty on shops like hers, **starting next week**.
She has no time to prepare. She doesn't know that the law says a new duty on business can start **no sooner than
3 months** after it's published. She doesn't know where to complain. She just pays.

**Now meet Aziz.** He works at the regional justice department (adliya). Every local draft passes through his desk,
and he has **2 to 5 working days** to check each one against thousands of laws, which change all the time. He does it
**by hand**. He's good, but he's one person.

And the numbers behind them:
- **166,155 laws and legal documents** in Uzbekistan's legal database, many amended again and again
  (**185,049** older versions).
- **~908,000 local documents** in the E-qaror system since 2021.
- In our sample of 92 recent drafts, **94.6 % got zero public comments**: nobody outside reads them.
- **68 decisions in 2025 still referred to a law article that had been cancelled** in October 2024.
- Mistakes get cancelled **later**, after they've already affected people.

**The problem isn't bad people. It's too many decisions, too many laws, too little time.**

---

## 2. What Mezon does: the solution

Mezon is like a **spell-checker for law**. Spell-check doesn't write your essay, it underlines the mistakes.
Mezon underlines the possible legal mistakes in a decision and shows why.

**It watches at three moments:**
1. **Before:** while a draft is open for public discussion. A problem can be fixed before anyone is hurt.
2. **Skipped steps:** a decision that appears with no draft, or before discussion ended.
3. **After:** the day a decision is published.

**For each finding it shows:**
- the sentence in the decision that may be wrong;
- **the law and the article it may break, as the law read on that exact day** (laws change, so the date matters);
- the exact words of the law, with a link to the official source;
- a clear label: *"possible issue, for expert review"*. Mezon never says "illegal". **A human expert always decides.**

**Then it helps fix it:** a ready-made appeal goes to the right place (the justice department, the Business
Ombudsman, the court), so a business owner like Dilnoza can act in one tap.

---

## 3. How it helps the justice expert (Aziz)

Today Aziz starts from a blank page. With Mezon he opens a draft and sees:
- a **ready conclusion** in his own official format: *no issues* / *issues that can be fixed* / *serious issues*;
- each issue already linked to the article and the exact quote;
- the decision side by side with the higher law it's based on, differences highlighted.

He checks, agrees or corrects, and signs. **Mezon does the searching; Aziz does the judging.**
That's the point: more decisions checked, more carefully, in the same 2-5 days.

---

## 4. Real cases (all public, all were cancelled)

| Place | What happened | What Mezon would flag |
|---|---|---|
| **Qarshi** | A decision copied an earlier one word for word 15 days later, while the first was still valid, and "cancelled" a decision that was already cancelled. The justice department asked to cancel it; it was cancelled. | Duplicate of a valid decision + cancelling something already cancelled |
| **Yangiyo'l** | Land-tax rates were set without the required public discussion. Cancelled and adopted again properly. | The public discussion step was skipped |
| **Xatirchi** | A council decision put a burden on a period *before* it was adopted. Cancelled after the justice department's request. | A burden that applies to the past |
| **68 decisions (2025)** | Still citing a law article that stopped existing in October 2024 | "This article was not in force on that date" |

**How to talk about them:** "Mezon flagged a defect consistent with the justice department's finding." Never
"Mezon caught the hokim". It's about decisions, not people.

---

## 5. Our own AI: Mezon-LM

Big AI models (ChatGPT, Claude, Gemini) don't really know Uzbek law, especially **which version was valid on which
date**, and legal AI tools get the law wrong **17-33 %** of the time (Stanford study, 2024).

So we're building **our own Uzbek legal AI**, running on our own computers (decision texts never go to a foreign
cloud). It learns like a law student:
1. **Law school:** reads every law and every version.
2. **Internship:** studies real cases, why decisions were cancelled, what courts decided.
3. **Practice:** an examiner that only rewards answers with the exact, correct article.
4. **Morning news:** every day it reads which laws changed.

**Today:** a fresh model scored **25 %** on our 400-question Uzbek law exam. Law school is running now, and the
first results show it's learning (its "surprise" on new law lessons fell from 0.85 to 0.27). **The goal:** the best
Uzbek legal AI, proven on a public exam. (Don't show "we beat ChatGPT" until we've measured it.)

---

## 6. The product (screens)

1. **Expert desk** (for the justice department): a list of decisions to check, the most important first. Open one: the
   decision on the left, Mezon's findings on the right, the ready conclusion on top.
2. **Law time machine:** pick an article and a date and see exactly what it said that day.
3. **Region map:** how many decisions were checked and what kinds of issues, by region (no ranking of people).
4. **Citizen / business app:** "decisions that affect me", explained simply, with one tap to the right office.

**Design feeling:** calm, clean, trustworthy, like an official tool. Blue and white, the scales as the symbol. Every
claim on screen has its source one tap away. No emoji in the product, no red "guilty" stamps, no faces of officials.

---

## 7. Three taglines to choose from
- *"Every decision, weighed against the law of its day."*
- *"Mezon finds it. The expert decides."*
- *"Har bir qaror - qonun tarozisida."*

---

## 8. Don't
- Don't call anything "illegal" or "corrupt"; don't show officials' faces or names.
- Don't put government logos as if they endorse Mezon. They're data sources (lex.uz, courts, E-qaror), nothing more.
- Don't show numbers that aren't in this file, and no "better than ChatGPT" yet.
