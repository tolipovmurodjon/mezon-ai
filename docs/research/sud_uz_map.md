# Map of the Uzbek court websites (sud.uz family), 21 Nov 2026

Method: public pages only, read through WebFetch and web search. No form was submitted, no login, no robot checkbox, no hidden API. Counts come from what the pages showed; everything else is marked "not verified". WebFetch reads static HTML only, so JS-only apps (public, stat, my, exsud, jadval2) showed just a title.

## 1. sud.uz (Supreme Court, WordPress)

- robots.txt: `User-agent: *`, `Disallow: /wp-admin/` (admin-ajax allowed), `Sitemap: https://sud.uz/wp-sitemap.xml`. No crawl-delay.
- Languages: Cyrillic Uzbek (default), `/ru/`, `/la/` (Latin). Footer says "site is in test mode".
- Sitemap index (19 files): posts (uz/ru/la), pages (uz/ru/la), post types `court`, `team`, `footer`, `header`, taxonomies `category`, `court_type`, `region`, users. Entry counts not verified (fetch the sub-sitemaps to count).
- Open, plain HTML, no bot check seen.

| Section | URL | Publishes | Count / years | Format | AI value |
|---|---|---|---|---|---|
| Plenum resolutions | /plenum/ -> 4 lists (criminal, civil, administrative, economic; e.g. /plenum/documents-civil/) | Plenum resolutions | we hold 4 lists already (part of 149 files) | PDF | (a) high |
| Practice reviews | /court-experiments/ -> crime / civil / administrative / economical | Reviews and generalisations of practice | administrative 32 items (2025:1, 2024:3, 2023:3, 2021-22:13, 2018-20:12); economic 31 (same split: 1/3/3/12/12); criminal and civil lists not read (not verified) | PDF 15, DOCX 13, ZIP 2, DOC 1 (economic page) | (a) high, (b) high: real cases with reasoning |
| Plenum / Presidium pages | /court-plenum/, /presedium/ | Composition, sessions | not verified | HTML | low |
| Statutes | /statutes/ | Regulations (nizomlar) | not verified | not verified | (a) low-medium |
| Attestation questions | /attestation-questions/ | Judge exam questions | not verified | not verified | (a) medium |
| Bulletin (Axborotnoma) | /printed-publications/supreme-court-newsletter/ | Oliy sud axborotnomasi | 14 issues: 2021 x6, 2022 x6, 2023 x2 (nothing newer on page) | PDF, no pagination, e.g. /wp-content/uploads/2022/09/1-2022.pdf | (a) high, (b) high |
| Journal "Odil sudlov" | /printed-publications/odil-sudlov-journal/ | Journal | 12 issues, 2021 only | PDF /wp-content/uploads/2023/01/N-OS-2021.pdf | (a) medium |
| Newspaper "Kuch - adolatda" | /printed-publications/kuch-adolatda-newspaper/ | Newspaper | 2021: 19 entries (issues 1-23); 2022: 48 entries (issues 1-52); one 2022 link is a duplicate of no. 19 | PDF | (a) low-medium |
| Open data, Supreme Court | /open-info/supreme-court-open-info/ | Budget, procurement, travel, vehicles, quarterly datasets (about 19-20 per quarter) | 2026, 2025, earlier, by quarter | xlsx, xls, xlsm, pdf | none for our goal |
| Department reports | /open-info/department-open-info/reports/ | Financial reports | 27 Excel files (2024 12m, 2024 9m, 2023) | xlsx, xlsm | none |
| Lower courts | /regional-courts-info/ -> general (12+ regional courts, truncated), administrative (14 courts), military | Contacts, chairs, panels, phones. No decisions on these pages | 14 administrative courts listed (Tashkent region, Tashkent city, Syrdarya, Jizzakh, Samarkand, Fergana, Namangan, Andijan, Kashkadarya, Surkhandarya, Bukhara, Navoi, Khorezm, Karakalpakstan) | HTML | none (directory only) |
| News | /news/, posts like /news-2026-10-21-1/ | Press items, some case outcomes | not verified; WP posts, probably paginated | HTML | (b) low-medium |
| Other | /about-us/, /structure/, /our-team/, /hr/, /faq/, /payment-details/, anti-corruption pages, gender pages, /vidoes/ | admin | n/a | HTML | none |
| Legal acts on courts | lex.uz /classifiers/7592 and lex.uz/docs/68425 (lost force) | links out | n/a | lex.uz | already in our lex.uz pipeline |
| Draft acts | regulation.adliya.uz/project?projectPassportSpecialityId=10 | court-related drafts | not verified | JS app | low |

## 2. Subdomains

| Host | What it is | Access | Notes |
|---|---|---|---|
| public.sud.uz | "Suд хужжатларини интернет тармоғида чоп этиш" (publication of court documents), logo "Adolat". Quick link `public.sud.uz/#!/sign/view` | JS-only app (static HTML has a title only). Robot check status not verified from here. Our CLAUDE.md says it is a simple HTML checkbox; this mapping did not touch it | robots.txt: none visible (page returned the title instead, so effectively no rules) |
| stat.sud.uz | "Sudlar faoliyati bo'yicha statistik ko'rsatkichlar". JS shell | open PDFs by direct link | Search found PDF reports under `/file/<year>/<dd.mm>/...`: "sayt ma'muriy 2024 yil 1-yarmi" (first-instance administrative public disputes, 2020 to H1 2024, regional breakdown, tables on decisions of administrative bodies declared invalid and on unlawful acts of officials), "2023 yil 9 oyi", "2023 yil 6 oyi" (cases by region and share satisfied). Current index and 2025 files: not verified. robots.txt: none visible |
| my.sud.uz | Interactive services, case tracking (`#onlinetracking`), claim samples `/claim-simples`, rules | JS, partly login | (b) low: claim templates only |
| cabinet.sud.uz | E-filing | login | skip |
| exsud.sud.uz/decisions | "Online court decisions", site name "Oliy sud" | JS-only; not verified what it lists | Possibly a second list of decisions. Needs a browser check |
| jadval2.sud.uz | Hearing schedule in four lists (criminal, civil, administrative, economic) | open, no filter text seen | hearings only, skip |
| billing.sud.uz, qabul.sud.uz, vka.sud.uz | Payments, reception booking, video link | login or service | skip |
| old.sud.uz | Previous site version | TLS certificate mismatch (cert covers only sud.uz, www.sud.uz) so fetch fails | Search results show old PDFs there, e.g. `/wp-content/uploads/2023/07/16_...PDF.pdf` (Plenum resolution 16). May hold older plenum and review files that the new site dropped. Needs Boss's browser or a verified fetch |
| qaraqalpaqstan.sud.uz | Karakalpakstan court site (linked from administrative page) | not fetched | not verified |
| Regional courts | No separate regional sites found; contacts use sud.uz email addresses | n/a | the whole lower-court layer publishes decisions only through public.sud.uz |
| Higher School of Judges | sudyalaroliymaktabi.uz (linked from sud.uz); root returned 404 on one try | not verified | find the real home page in a browser |
| Supreme Judicial Council | sudyalaroliykengashi.uz (linked) | not fetched | not verified |

## 3. public.sud.uz: what a published ruling holds

Not verified from public pages in this session (the app is JS-only and I did not open the robot gate). From our own holdings and project notes: the list row has case number, court, judge, outcome, PDF id and size (61,049 rows for the administrative category already held). A ruling PDF is the court's redacted decision text (parties anonymised); the project rule is to keep only number, date, court, outcome and cited act. Whether the list is reachable without the checkbox: not verified; do not test by ticking it without Boss. Other categories and their sizes: not verified. Expected from the Plenum and review structure, and from stat.sud.uz: criminal, civil, economic, administrative, plus possibly administrative offences and military. Sizes unknown; read the category counters in Boss's own browser (visible, no download needed).

## 4. Value for the legal AI

- (a) Law school: Plenum resolutions (have), practice reviews (administrative, economic, civil, criminal; about 30 per category), Bulletin 14 issues, Odil sudlov 12, old.sud.uz leftovers, attestation questions, statutes.
- (b) Internship (real cases with reasons): the practice reviews and bulletin quote cases with reasoning; the 61,049 administrative rulings on public.sud.uz are the big one (courts voiding decisions of administrative bodies are the closest to hokim decisions).
- (c) Labels and statistics: stat.sud.uz PDFs (administrative disputes, invalid decisions by region, half-year series 2020 to 2024). Counts only, proxy labels, not per-decision.

## 5. Download next (value x ease x allowed)

1. Administrative practice reviews, 32 files, /court-experiments/administrative-court-experiments/ (high value, trivial, open, robots allow). Then economic (31), civil, criminal lists (read them first for counts).
2. stat.sud.uz administrative PDFs (2023 to H1 2024 known by direct links; the full index needs Boss's browser to see the list). Gives evaluation numbers for the "invalid decisions" rate.
3. Bulletin (14) + Odil sudlov (12) PDFs: direct links, small, allowed. Kuch-adolatda (67 files) last, low value.
4. public.sud.uz other categories: Boss's browser first, read only the visible counters; then decide. Needs Boss's browser (robot gate, JS).
5. old.sud.uz PDFs: Boss's browser (certificate error); check for older plenum and review files missing on the new site.
6. exsud.sud.uz/decisions: Boss's browser, identify what it is before anything else.
7. sud.uz news posts with case outcomes: WP sitemap `wp-sitemap-posts-post-1.xml`, polite crawl; low value. Skip unless time.
8. Higher School of Judges and Supreme Judicial Council sites: Boss's browser to find the working address; may hold training material.
9. Skip: open-info Excel (finance), my/cabinet/billing/qabul/vka, jadval2, lower-court directories.
