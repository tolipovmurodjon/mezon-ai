# Source ledger: every data source, what it is allowed to do, and where it goes

Started 21 Nov 2026, 04:05 Tashkent. Counts are the latest printed by a command (date in brackets). Update this file
whenever a source changes; the full refinery reads only sources marked "train: yes".

| # | Source | Count (when) | Licence / terms | Personal data | Role: law school / internship / exam | Train? |
|---|---|---|---|---|---|---|
| 1 | lex.uz documents (texts) | 166,155 docs, pass 1 (20 Nov) | official public legal texts | local decisions name citizens -> mask citizens, keep officials | law school | yes |
| 2 | lex.uz editions | 185,049 editions / 45,393 acts | same | same | law school (latest + original + change notes); exam flip / in_force | yes (unseen exam half held out) |
| 3 | lex.uz files -> text | 16,647 pdftext + 3,157 doctext + OCR 1,019/2,074 docs (21 Nov 03:46) | same | same | law school | yes |
| 4 | lex.uz relations (pass 2) | 127,373 fully done, 39,310 left (21 Nov 03:46) | same | none | law graph; internship (what cites / cancels what) | yes |
| 5 | Cancelling acts (inside #1) | 35 labelled rows, 11 unique cases with original text | same | mask citizens | internship / exam (test set only until >= 60) | test only |
| 6 | sud.uz plenums + practice reviews | 149 files (20 Nov) + full-site crawl 755 URLs (21 Nov) | public court publications | reviews may name parties -> mask | law school + internship | yes |
| 7 | Constitutional Court | 5 PDFs + ~128 on lex.uz | public | none | law school | yes |
| 8 | public.sud.uz case cards | 1,714,883 rows (other session, 20 Nov) | public cards | judge names (officials) kept; party names masked | internship labels (category, outcome); eval base rates | labels only |
| 9 | public.sud.uz ruling texts | 0 | behind a robot check | heavy (citizens) | internship gold | no: needs an official export |
| 10 | regulation.gov.uz drafts | 16,046 (21 Nov 03:46) | public drafts | officials only | internship (draft -> adopted); Gate 0 | yes |
| 11 | E-qaror | 800 rows | browser only | some | procedure labels; exam ("declared invalid") | after Boss's export |
| 12 | data.egov.uz legal datasets | downloading (~175 sets: Adliya 33, Supreme Court 12, Prosecutor 12+10+9, ...) | CC BY-SA 4.0 | registers of lawyers/notaries name professionals (public registers) | registers for tools; ministry-acts register = completeness check for #1 | registers: tools, not text training |
| 13 | gov.uz | 1,335 URLs (21 Nov 03:46) | public government portal | officials' bios (public role info) | who-does-what; morning briefing | yes (structure pages) |
| 14 | my.gov.uz | 950 URLs | public service catalogue | none | citizen-facing answers (services, fees, steps) | yes |
| 15 | ombudsman.uz | 886 URLs | public | officials | law school (reports), routing | yes |
| 16 | prokuratura.uz | 8 static endpoints + 20,425 news (downloading) | public | officials; news may name suspects -> mask | morning briefing; legality context | news: masked |
| 17 | FineWeb-2 uzn_Latn | 3.3 GB replay (with #18) | ODC-By | web text | replay (anti-forgetting) | yes |
| 18 | Tulu 3 SFT mix | in the 3.3 GB | ODC-By (no_robots CC-BY-NC and hard-coded rows dropped) | none | replay | yes |
| 19 | MezonBench v1 | 400 items (151 recent) | ours | none | exam only; unseen half never trained | never |
| 20 | sharh.lex.uz | 0 | paid product, login | n/a | commentary | no: needs a written licence |
| 21 | stat.sud.uz | 41 files listed in its app (queued) | public statistics | none | eval base rates, pitch numbers | yes (tables) |

**Null baselines (MezonBench v1, 21 Nov 04:05):** always-A flip 49.2 %, always-ha in_force 50.0 %, random ~50 %;
a model that always answers A / ha / B and abstains on lookup scores 35.0 % overall. Every score is reported against
this line. Pilot v1: 38.5 % (flip 48.3 %, in_force 49.2 %: at the baseline; hierarchy 92.5 %: real).

**Next completeness check:** match the Adliya register of ministry acts (data.egov.uz 1-014-0016, 1,266 rows,
registration number + date) against lex.uz pass 1; report found / missing with N.
