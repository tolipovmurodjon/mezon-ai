# Mezon film: creative brief (shared by builder and checker)

One standalone HTML file, `D:\10_projects\mezon\docs\pitch\film\mezon_film.html`, a 56-second brand film synced by hand
to `music.mp3` in the same folder (Pixabay "mrclaps - stomp and clap", 56.27 s). The owner rejected two drafts as
"AI slop": too small, too busy, the stage off-centre and cropped, controls covering the film. Start from scratch.

## Creative standard (from the owner's reference brief)
Act as an internationally acclaimed motion-graphics director and kinetic-typography designer. It must feel like an
expensive brand film for a giant conference screen: typography is the main character; originality over complexity;
timing over excess movement; precision over randomness; restraint over clutter. Every scene introduces a different
typographic idea inside one coherent visual language. Concise copy: every phrase earns its place. The film must read
without narration. Reference feel: the best ChatGPT / Apple kinetic-type films: huge type, a hook in the first seconds,
then real use cases, text that lines up, breaks into character particles and re-forms, all landing on the sound.

## What Mezon is
An AI auditor of local hokim and Kengash decisions in Uzbekistan, built for Adliya (Ministry of Justice). It watches
lex.uz / E-qaror / regulation.gov.uz every day, checks each decision against the law AS IT READ ON THAT DAY, flags a
possible defect with the exact article and a verbatim quote, and a human expert decides. Judges: senior Adliya
officials. Then businesses and citizens.

## Music (measured; use these times)
148 BPM, beat 0.405 s, bar 1.622 s, first beat 0.296 s; bar n starts at 0.296 + n*1.622 s.
- bars 0-1 (0.30-3.53): claps only, quiet. bar 2 (3.53): build. bars 3-7 (5.15-13.26): full beat.
- bars 8-9 (13.26-16.51): BREAK, near silence. bar 10 (16.51): build. bar 11 (18.12): DROP, peak, bars 11-15 (to 26.24).
- bars 16-18 (26.24-31.10): dip. bar 19 (31.10): build. bars 20-31 (32.72-52.18): high, sustained.
- bar 32 (52.18): quiet tail; silence from 53.80 to 56.27.
Hits on downbeats; stillness in the break; the biggest moment on the drop; rapid one-per-beat sequences in high parts.

## Story (Uzbek, ASCII apostrophe ' only; ONE idea on screen at a time)
1. HOOK 0.3-5.15: type on the claps: “...Qonunining 6 va 25-moddalariga asosan” + small caption
   "Yakkabog' tumani hokimi · 355-4-68-Q/25 · 13.11.2025".
2. 5.15 downbeat: strike "25-moddalariga" (ember). Then alone, one per bar: "Bu modda bir yil oldin kuchini yo'qotgan."
   → "Qaror esa imzolangan." → "907 624 hujjat" (E-qaror, 2021-yildan) → "2-5 kun · har biri qo'lda" → "611"
   (hokimlik qarori sudda qonunga zid deb topildi · 2025).
3. BREAK 13.26-16.51: stillness: "Buni kim ko'radi?"
4. DROP 18.12: MEZON forms from flying characters (digits/letters of registration numbers like 231-4-59-Q/24,
   VI-76-4-10-146-K/24) and snaps exactly on 18.12. "mahalliy qarorlar auditori".
5. 18.12-26.24 USE CASE 1, watch 24/7: "lex.uz · E-qaror · regulation.gov.uz" → clock 00:00→23:59 "har kuni" →
   decisions arriving one by one, each matched "→ qonun, o'sha kundagi tahriri".
6. 26.24-31.10 USE CASE 2, the agent: "Nega bu qaror belgilandi?" typed; steps ONE AT A TIME: decision_text → rules
   (14 ta tekshiruv) → law 6-modda: amalda → law 25-modda: KUCHINI YO'QOTGAN (ember) → verify_quote: iqtibos aynan bor.
7. 32.72-~40 USE CASE 3, the expert: decision quote vs lex.uz quote, side by side, big; "Ekspert: [x] tasdiqlanadi";
   "Inson hal qiladi."
8. ~40-46 USE CASE 4, the region head: "Adliya navbati" list re-sorting (416-4-57-Q/22, 332-4-64-Q/25, 282-4-64-Q/25,
   355-4-68-Q/25, 265-4-60-Q/25) → "Viloyat hisoboti: dushanba, bir sahifa". Optional quick beat for citizens and
   business: "Tadbirkor uchun: 3 oy muddat bormi?" / "Fuqaro uchun: bu qaror menga nima degani?"
9. ~46-52.18 PROOF, one per beat group: "354/354 iqtibos aynan" → "10/20 bekor qilingan qaror oldindan belgilandi" →
   "2 ta adliya taqdimnomasi bilan mos: Qarshi, Xatirchi".
10. 52.18-56.27 into silence: "AI taklif qiladi." → "Inson hal qiladi." → "MEZON" + "Belgilangan ≠ noqonuniy".
Facts are fixed; never invent numbers. Never call a decision "illegal"/"noqonuniy" (the 611 line is a court finding).

## Look
- Paper-white background (warm off-white, about #f6f5f0), ink type, a small deliberate accent palette: ember for
  defects, one Mezon colour (teal or electric green), one violet for the agent. No glassy cards, no decorative
  gradients, no emoji, no icons, no stock "AI glow".
- Distinctive MONOSPACE-led custom fonts from Google Fonts (e.g. Martian Mono display; Geist Mono / Fragment Mono /
  Azeret Mono small; Instrument Serif italic allowed for the human lines). Verify they load and cover the glyphs used.
- BIG: main lines 120-260 px on the 1920x1080 stage, captions at least 30 px. Generous negative space, strict grid.
- Motion varied and art-directed: letter-by-letter typing, mask reveals, tracking collapse, splits and strikes, text
  lining up then breaking into character particles and re-forming, re-sorting lists, slot-roll digits, real stillness
  in the break. Never the same transition twice in a row; intentional easing (expo, back, cubic).

## Technical
- Stage 1920x1080: `position:absolute; left:50%; top:50%; transform: translate(-50%,-50%) scale(s)`,
  s = min(innerWidth/1920, innerHeight/1080). Body background = paper.
- `<audio src="music.mp3">`; every frame is a pure function of `audio.currentTime` (works on file://).
- Controls (play/pause, restart, fullscreen, clean mode H) hidden by default, small, bottom-right, shown 2 s on mouse
  move; a centred "Boshlash" click-to-start. `?t=SECONDS` freezes at that time without audio; `?clean` hides UI.
- Optional WebM record via getDisplayMedia + MediaRecorder with a graceful message on failure.

## How to check (both builder and checker)
Render frames with headless Chrome (one process at a time; the laptop is low on memory and disk):
`"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 --virtual-time-budget=4000 --screenshot=<scratch>\f_<t>.png "file:///D:/10_projects/mezon/docs/pitch/film/mezon_film.html?t=<t>&clean"`
Frames to capture at least: 2, 4.5, 6, 9, 12, 15, 17.5, 18.3, 21, 24, 28, 30, 34, 38, 43, 48, 51, 54, 55.5.
Open each PNG with the Read tool. Judge: readable at a glance from across a room, one idea per frame, aligned, nothing
clipped or overlapping, fonts really loaded, palette restrained, the frame matches the music section it sits in.
Syntax-check the script with `node --check` on the extracted JS. Delete screenshots when done. No other browser
automation.

## Checker criteria (the owner's words, 19.11): judge it as the Adliya jury would
- The pitch talks and shows screenshots; the FILM must do what the talk cannot: carry the tempo and push the idea
  straight into the jury's head in 56 seconds. After one viewing a senior Adliya official must be able to say:
  (1) the problem (local decisions slip past manual review; real case: a decision resting on a dead article),
  (2) the solution (Mezon reads every decision against the law as it read that day, 24/7, and shows its steps),
  (3) why it is different from everything else (law as of the decision date, a verbatim quote for every flag, an
  agent whose every step is visible, a human signs), (4) that it is usable right now for Adliya's own job (the queue,
  the draft conclusion, the region report), and (5) that it is proven on real cases (Qarshi, Xatirchi, 354/354).
- Big numbers must land as proof, each staged uniquely and huge, never as a list.
- Real cases, named, on screen: they are what wows Adliya, not slogans.
- Show how the agent works and how a person uses it, in seconds, without small UI.
- Every weak or "simple-looking" part gets a bolder, concrete replacement idea, not a vague note.
