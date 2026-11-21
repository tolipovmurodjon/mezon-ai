# DRAFT: ma'lumot so'rovi (Adliya vazirligi / "Adolat" milliy huquqiy axborot markazi)

> Draft for Boss to read and edit. Not sent. Nothing leaves without Boss's yes and the team lawyer's check.
> Names, phone and signature are left blank on purpose.

---

**Kimga:** O'zbekiston Respublikasi Adliya vazirligi
huzuridagi "Adolat" milliy huquqiy axborot markazi rahbariyatiga
(nusxa: Adliya vazirligining raqamlashtirish bo'yicha mas'ul bo'linmasi)

**Kimdan:** "Mezon" jamoasi, LexHackathon 2026 (Adliya vazirligi tashkil etgan), 1-yo'nalish ishtirokchisi
Rahbar: ____________ · Telefon: ____________ · Elektron pochta: ____________

**Mavzu:** Mahalliy davlat hokimiyati organlari qarorlarining qonuniyligini tekshirishga yordam beruvchi
"Mezon" tizimi uchun ochiq va anonimlashtirilgan ma'lumotlarni taqdim etish to'g'risida

---

Hurmatli rahbariyat!

"Mezon" jamoasi LexHackathon 2026 doirasida hokim va mahalliy Kengash qarorlarini qonun hujjatlariga
muvofiqligini tekshirishda adliya organlari mutaxassislariga yordam beruvchi tizim ishlab chiqmoqda. Tizim
qaror loyihasini qonunning qaror sanasida amalda bo'lgan tahririga solishtiradi va har bir ehtimoliy kamchilik
uchun aniq modda va iqtibos bilan dastlabki xulosa loyihasini tayyorlaydi. Yakuniy qarorni har doim mutaxassis
qabul qiladi (Adliya vazirligining sun'iy intellektdan foydalanish bo'yicha etika qoidalariga muvofiq).

Tizim to'liq O'zbekiston ichida, o'z serverlarimizda ishlaydi: qaror matnlari xorijiy bulut xizmatlariga
yuborilmaydi; fuqarolarning shaxsiy ma'lumotlari o'qitishdan oldin niqoblanadi.

Ishni sifatli va qonuniy asosda davom ettirish uchun quyidagilarni so'raymiz:

1. **lex.uz milliy bazasining to'liq eksporti** (hujjatlar matni, barcha tahrirlar sanalari bilan, hujjatlar
   o'rtasidagi bog'lanishlar). Hozir biz saytdan cheklangan tezlikda yuklab olmoqdamiz; rasmiy eksport serverga
   yuklamani kamaytiradi va ma'lumotning to'liqligini kafolatlaydi.
2. **Mahalliy qarorlar loyihalari bo'yicha adliya organlarining huquqiy ekspertiza xulosalari va
   taqdimnomalaridan namunaviy to'plam** (dastlab 100 ta, anonimlashtirilgan holda): xulosa turi (ijobiy /
   bartaraf etiladigan kamchiliklar bilan / salbiy), kamchiliklar va asos bo'lgan normalar.
3. **public.sud.uz dagi ma'muriy ishlar bo'yicha e'lon qilingan sud hujjatlari matnlari** (mahalliy organlar
   qarorlari ustidan nizolar toifasi), sudning o'zi e'lon qilgan anonimlashtirilgan ko'rinishda.
5. **regulation.adliya.uz (yangi loyihalar portali) dagi loyihalar ro'yxati va matnlari**, muhokama muddatlari va
   takliflar soni bilan (portal avtomatik so'rovlarni Cloudflare himoyasi orqali to'xtatadi; biz uni chetlab
   o'tmaymiz).
4. **E-qaror tizimidagi qarorlarning qabul qilish bosqichlari to'g'risidagi ma'lumotlar** (bosqichlar va sanalar,
   "haqiqiy emas deb topilgan" belgisi), shaxsiy ma'lumotlarsiz.

**Ma'lumotlardan foydalanish shartlari (biz o'z zimmamizga olamiz):**
- faqat qarorlarning qonuniyligini tekshirish vositasini ishlab chiqish va baholash uchun foydalanish;
- uchinchi shaxslarga bermaslik, xorijiy bulut xizmatlariga yubormaslik;
- shaxsiy ma'lumotlarni niqoblash ("Shaxsga doir ma'lumotlar to'g'risida"gi Qonun talablariga muvofiq);
- talab qilinganda ma'lumotlarni o'chirish va bu haqda yozma tasdiq berish.

**Biz nima beramiz:**
- adliya mutaxassislari uchun bepul sinov versiyasi va natijalar hisoboti (qancha qaror tekshirildi, qancha
  ehtimoliy kamchilik topildi, mutaxassislar ularning qanchasini tasdiqladi);
- lex.uz ma'lumotlaridagi texnik nomuvofiqliklar ro'yxati (masalan, saytda mavjud bo'lmagan havolalar),
  agar bu foydali bo'lsa.

Hurmat bilan,
____________ (F.I.Sh.), "Mezon" jamoasi rahbari
Sana: ____________

---

### Notes for Boss (not part of the letter)
- Facts behind item 1: lex.uz pass 2 is at 160K+ documents with 0 errors at 45 req/s; 5,572 ids return 404 on
  lex.uz itself (useful to offer as a data-quality finding).
- Item 2 is the most valuable raw material we do not have (we have 35 labelled cancellations, 11 unique with text).
- Item 3: public.sud.uz rulings sit behind a robot check; we do not bypass it. The 1,714,883 case cards we hold have
  outcomes but no reasons.
- Legal basis to name (check with the lawyer before sending): the open-data rules and the personal-data law; do not
  cite article numbers until the lawyer confirms them in the law store.
- Who signs and who receives: the hackathon organisers can tell us the right office; ask them first.
