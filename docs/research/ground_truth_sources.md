# Ground-truth and legal-interpretation sources (research, 21 Nov 2026)

Method: public pages only, read through WebFetch/WebSearch. No datasets downloaded, no forms, no bot checks, no hidden APIs. Where I could not check something it says "not verified". The tooling could not open constcourt.uz (DNS failure) or supcourt.uz (TLS protocol error), so those were not read directly.

## 0. sud.uz (Boss's pointer): what it is [verified by fetch]
- sud.uz is the Supreme Court's own website (WordPress, Cyrillic Uzbek default, /ru/ and /la/ Latin versions in the sitemap). Banner says "site is running in test mode". Old site: old.sud.uz (still serving PDFs from 2019-2023). The older domain oliysud.uz appears in a 2021 PDF header (redirect not verified). supcourt.uz: not verified (TLS error); treat as an alias or old name.
- Menu: General info (court system, Plenum, Presidium, judicial panels, lower courts); Documents (Plenum resolutions, court-practice generalisations and reviews, statutes, draft regulations); E-services; Open data; Anti-corruption; Press. Footer links to a "court decisions collection" and the hearing schedule.
- Relation to the other sites (from the footer and earlier project work; subsites not re-fetched, so current content not verified): public.sud.uz = published rulings and case cards (our 61,049 admin cases); stat.sud.uz = quarterly statistics; my.sud.uz = citizen e-service; jadval sites = hearing schedules. All belong to the same Supreme Court / court-system family.
- robots.txt (verified): `User-agent: *`, `Disallow: /wp-admin/`, `Allow: /wp-admin/admin-ajax.php`, `Sitemap: https://sud.uz/wp-sitemap.xml`. No crawl-delay. No terms-of-use page seen.
- Sitemap: 18 sub-sitemaps (posts, pages, custom types court/team, taxonomies court_type/region, in uz, ru, la). No URL counts shown.
- Plenum section https://sud.uz/plenum/ has four plain-HTML listing pages, no pagination:
  - /plenum/documents-criminal/ : 59 rows, 1996-2026 (54 link to lex.uz, 5 to sud.uz PDFs)
  - /plenum/documents-civil/ : 44 rows (43 distinct), 1991-2026 (38 lex.uz, 5 PDFs)
  - /plenum/documents-administrative/ : 7 rows, 2018-2026 (4 lex.uz, 3 PDFs)
  - /plenum/documents-economical/ : 33 rows, 2002-2026 (27 lex.uz, 6 PDFs)
  - Total listed: 143 rows (some joint amendments may appear in several lists, so roughly 135-140 distinct). Latest are dated 3 Jul 2026 (Nos. 18, 19, 20). Link quirks: double slash `lex.uz//docs/`, trailing `%20`, one duplicate.
- Generalisations and reviews of court practice exist as PDFs under /wp-content/uploads/YYYY/MM/ (search found an Economic panel review for Q3-2024, a Criminal panel review for Q4-2024, and an old.sud.uz 2021 review). Count not verified. Many generalisation findings sit inside plenum resolutions on lex.uz.

## Colleague's numbers
- "~200 plenum documents": NOT confirmed. sud.uz lists 143 rows (about 135-140 distinct). Our lex.uz catalogue count of ~225 titles mentioning the plenum is a different measure (includes acts that cite or amend plenum resolutions).
- "~500 Constitutional Court documents": NOT verified (site unreachable, no source found).

## 1. Supreme Court plenum resolutions
- Exists: yes, sud.uz/plenum. Format: HTML list + lex.uz links + some PDFs (Cyrillic). Access: plain HTTP, no login or bot check seen.
- Overlap with lex.uz: very high. 123 of 143 rows link to lex.uz (54+38+4+27); the PDF-only rows (about 20, mostly 2024-2026 amendments) are probably also on lex.uz, not verified one by one. Diff the lex.uz ids against our crawl.
- Value: (a) labels low (general rules, no cases). (b) interpretation HIGH: authoritative reading of statutes. The administrative-justice resolutions (2018 No. 35, 2022 No. 8, 2024 No. 22) matter most for hokim decisions. Small corpus: use as gold teaching text.

## 2. Constitutional Court
- Official site: not verified. constcourt.uz did not resolve. Search found only lex.uz acts, the archived older domain ksu.uz, and a presidential decree on digitising the court. Likely domain constitutionalcourt.uz: not verified.
- Decisions appear as acts on lex.uz (our catalogue: ~128 titles). Count on the court's own site: not verified.
- Value: (a) low-medium (few cases touch local acts; constitutional complaints are new). (b) medium-high for constitutional reasoning; small.

## 3. Prosecutor General (prokuratura.uz)
- Site exists (title "Bosh prokuratura"); fetch returned only a title, so structure, counts, robots: not verified. Searches found only aggregate press figures (about 112,000 supervisory documents and 322,000 citizens' rights restored in H1 2026 per UzA/Kun snippets; originals not opened, unverified) and nothing about protests against hokim decisions.
- Prosecutor protests against local acts mostly surface as cancelling acts on lex.uz, which we already mine. Value: (a) medium for aggregate stats, case-level unlikely; (b) low.

## 4. Ombudsmen
- Human Rights Ombudsman (Oliy Majlis): ombudsman.uz verified. Uz Cyrillic/Latin, Ru, En; "test mode"; Publications > Reports; news tagged "murojaat" (appeals). Footer asks users of its materials to contact the site (a reuse condition; no formal terms; robots not visible). Report years and counts: not verified.
- Business Ombudsman: biznesombudsman.uz loaded only partly (news, announcements). Official URL, report section, robots: not verified. Press snippets (UzA, Spot, Yuz): a Jan 2026 headline says 220 unlawful local hokimiyat decisions were annulled (snippet only, NOT verified); other totals conflict between outlets (7,629 vs 10,740 appeals in nine months; 250 vs about 300 bn soms over seven years).
- Value: (a) medium: narratives of restored rights against hokim decisions are good positives, but few carry a decision number. (b) low-medium.

## 5. Ministry of Justice (gov.uz/oz/adliya; not adliya.uz)
- Sections seen: key indicators and statistics, expertise of normative act drafts, study of law enforcement practice, ministerial orders, lost-force acts, open data. Fetched pages gave only menus, so contents, years and formats: not verified.
- Press leads (snippets only, unverified): Nov 2020, minister said about 10,250 unlawful acts cancelled in about 2.5 years, over 2,000 of them hokimlik decisions (Kun.uz); another UzA item cites 55,984 representations (date unconfirmed).
- Value: (a) high for base rates (denominators for precision claims), low for case labels; (b) low. Case-level data is already in the lex.uz cancelling acts.

## 6. Linking E-qaror decisions to public.sud.uz cases
- NOT verified. I did not open case cards or ruling PDFs. Hypothesis to test on 20 cases: administrative rulings cite the contested act by number and date in the text, so matching by registration number (regnum.parse) needs the PDF text. Our 61,049 records have case number, court, date, outcome and PDF id only. Extract only act number, date, court, outcome (project rule: no personal data). No prior art found.

## 7. Norms table (article -> norm -> addressee -> obligation -> sanction)
- Not researched with sources in this pass (no search run). From general knowledge, unverified here: LegalRuleML (OASIS), Akoma Ntoso for structure, Hohfeldian/deontic classes (obligation, permission, prohibition), CUAD/LegalBench-style clause annotation, obligation extraction work on EU law. No Uzbek dataset known. Suggested next step: a proper literature search, then label about 200 articles with Qwen plus a lawyer check.

## 8. Other sources (suggestions, not verified here)
- Supreme Court panel reviews and generalisations on sud.uz (exist, see section 0).
- Higher Economic Court archives (court merged into the Supreme Court; archive location not verified).
- "Qonunchilik ma'lumotlari milliy bazasi" is lex.uz itself (already crawled). Adliya "Huquqiy axborot" bulletins: not verified.
- data.egov.uz datasets and regulation.gov.uz drafts are already in the plan.

## Ranked: what to get first (value x ease)
1. Plenum resolutions (administrative, civil, economic) from sud.uz lists. Value high for (b); ease very high (4 static pages, 143 rows). In lex.uz crawl: mostly yes; only about 20 PDF-only rows to add.
2. Act numbers and outcomes from the 61,049 administrative ruling PDFs. Highest value for (a) and (b); ease medium (PDF ids in hand, project approvals apply). Not in the lex.uz crawl.
3. Ministry of Justice statistics and review pages (gov.uz/oz/adliya). Value high for base rates; ease medium. Not in crawl.
4. Cancelling acts already on lex.uz (adliya, prosecutor, court): keep mining. In crawl.
5. Supreme Court panel reviews and generalisations (sud.uz PDFs). Value medium-high for (b); ease medium. Not in crawl.
6. Business and Human Rights Ombudsman reports. Value medium; ease medium (sites partly broken or in test mode). Not in crawl.
7. Constitutional Court decisions. Value medium; mostly on lex.uz already; find the official site first.
8. Prosecutor General reports. Value low-medium; ease unclear. Not in crawl.
9. Norms-table method: design work, no download.

Sources used: sud.uz (home, /plenum/ and four category pages, robots.txt, wp-sitemap.xml), ombudsman.uz, gov.uz/oz/adliya pages, and web-search snippets (uza.uz, kun.uz, lex.uz).
