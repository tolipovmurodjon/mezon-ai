"""
python manage.py seed_demo [--reset] [--days 180]

Fills the database with SYNTHETIC demonstration data: 14 regions, ~180 days of
requests from hokimliks with documents, AI analyses, expert decisions and the
activity log. Hokim names are invented. Laws are referenced by name only.
"""
import datetime as dt
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings
from django.conf import settings
from django.utils import timezone

from regulations import services
from regulations.ai.demo import DemoAnalyzer
from regulations.models import Analysis, Decision, Document, Event, Region, RegulationRequest

R = random.Random(2026)
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

REGIONS = [
    ("Qoraqalpog‘iston Respublikasi", "Qoraqalpog‘iston", "QQR", 1, 1, ["Nukus shahri", "Xo‘jayli tumani", "Beruniy tumani", "To‘rtko‘l tumani"]),
    ("Xorazm viloyati", "Xorazm", "XOR", 1, 2, ["Urganch shahri", "Xiva shahri", "Hazorasp tumani", "Shovot tumani"]),
    ("Navoiy viloyati", "Navoiy", "NAV", 2, 1, ["Navoiy shahri", "Zarafshon shahri", "Karmana tumani", "Xatirchi tumani"]),
    ("Buxoro viloyati", "Buxoro", "BUX", 2, 2, ["Buxoro shahri", "Kogon shahri", "G‘ijduvon tumani", "Vobkent tumani"]),
    ("Jizzax viloyati", "Jizzax", "JIZ", 3, 1, ["Jizzax shahri", "Zomin tumani", "G‘allaorol tumani"]),
    ("Samarqand viloyati", "Samarqand", "SAM", 3, 2, ["Samarqand shahri", "Urgut tumani", "Kattaqo‘rg‘on shahri", "Pastdarg‘om tumani"]),
    ("Qashqadaryo viloyati", "Qashqadaryo", "QAS", 3, 3, ["Qarshi shahri", "Shahrisabz shahri", "Kitob tumani", "Yakkabog‘ tumani", "G‘uzor tumani"]),
    ("Toshkent viloyati", "Toshkent v.", "TSV", 4, 1, ["Nurafshon shahri", "Chirchiq shahri", "Angren shahri", "Yangiyo‘l tumani", "Zangiota tumani"]),
    ("Sirdaryo viloyati", "Sirdaryo", "SIR", 4, 2, ["Guliston shahri", "Yangiyer shahri", "Sirdaryo tumani"]),
    ("Surxondaryo viloyati", "Surxondaryo", "SUR", 4, 3, ["Termiz shahri", "Denov tumani", "Sherobod tumani"]),
    ("Toshkent shahri", "Toshkent sh.", "TSH", 5, 1, ["Yunusobod tumani", "Chilonzor tumani", "Mirzo Ulug‘bek tumani", "Yashnobod tumani"]),
    ("Namangan viloyati", "Namangan", "NAM", 6, 1, ["Namangan shahri", "Chust tumani", "Kosonsoy tumani"]),
    ("Farg‘ona viloyati", "Farg‘ona", "FAR", 6, 2, ["Farg‘ona shahri", "Qo‘qon shahri", "Marg‘ilon shahri", "Quva tumani", "Rishton tumani"]),
    ("Andijon viloyati", "Andijon", "AND", 7, 1, ["Andijon shahri", "Asaka tumani", "Xonobod shahri", "Shahrixon tumani"]),
]
WEIGHT = {"TSH": 1.5, "FAR": 1.35, "SAM": 1.3, "AND": 1.2, "QAS": 1.2, "NAM": 1.1, "TSV": 1.2, "SUR": 0.9, "BUX": 0.9,
          "XOR": 0.9, "QQR": 0.8, "JIZ": 0.7, "SIR": 0.6, "NAV": 0.6}

FIRST = ["Akmal", "Bahodir", "Jasur", "Sherzod", "Otabek", "Ulug‘bek", "Farrux", "Rustam", "Zafar", "Anvar", "Dilshod",
         "Sardor", "Nodir", "Shuhrat", "Olimjon", "Murod", "Botir", "Ilhom", "Komil", "Hamid", "Nilufar", "Gulnora", "Dilfuza"]
LAST = ["Yusupov", "Rahimov", "Toshpo‘latov", "Ergashev", "Sobirov", "Qodirov", "Nazarov", "Xolmatov", "Abdullayev",
        "Mahmudov", "Sultonov", "Ismoilov", "Jo‘rayev", "Usmonov", "Hamroyev", "Saidov", "To‘xtayev", "Mirzayev", "Bozorov"]

L_MDH = "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonunning"
L_TADB = "“Tadbirkorlik faoliyati erkinligining kafolatlari to‘g‘risida”gi Qonun"
L_YER = "O‘zbekiston Respublikasi Yer kodeksi"
L_TALIM = "“Ta’lim to‘g‘risida”gi Qonun"
L_SOLIQ = "O‘zbekiston Respublikasi Soliq kodeksi"
L_REKLAMA = "“Reklama to‘g‘risida”gi Qonun"

# Each template: category, title, extra law, purpose, problem, benefit, clauses, flags
TEMPLATES = [
    dict(cat="Savdo va xizmat ko‘rsatish", title="Hududda savdo shoxobchalari faoliyatini tartibga solish to‘g‘risida",
         law=L_TADB, purpose="aholiga savdo xizmatlari ko‘rsatish sifatini oshirish", business=True,
         problem="savdo shoxobchalarining bir qismi piyodalar yo‘lagida faoliyat yuritmoqda",
         benefit="piyodalar harakati xavfsizligi ta’minlanadi va savdo madaniyati oshadi",
         clauses=["Savdo shoxobchalari faoliyatini joylashtirish sxemasi 1-ilovaga muvofiq tasdiqlansin.",
                  "Tadbirkorlik subyektlari savdo shoxobchasi oldidagi hududni obodonlashtirish va tozaligini ta’minlashi majburiy etib belgilansin.",
                  "Tuman savdo bo‘limi bir oy muddatda shoxobchalar ro‘yxatini yangilasin."]),
    dict(cat="Yer munosabatlari", title="Yer uchastkalarini ijaraga berish tartibini takomillashtirish to‘g‘risida",
         law=L_YER, purpose="yer uchastkalaridan foydalanish shaffofligini ta’minlash", business=True,
         problem="bo‘sh turgan yer uchastkalari bo‘yicha yagona ro‘yxat yuritilmaydi",
         benefit="yer uchastkalari faqat ochiq elektron auksion orqali ijaraga beriladi",
         clauses=["Bo‘sh turgan yer uchastkalarining yagona ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Yer uchastkalari yuridik shaxslar va tadbirkorlarga faqat elektron onlayn-auksion orqali ijaraga berilsin.",
                  "Kadastr bo‘limi ro‘yxatni har chorakda yangilab, rasmiy veb-saytda e’lon qilsin."]),
    dict(cat="Obodonlashtirish", title="Ko‘p qavatli uylar hududini obodonlashtirish bo‘yicha qo‘shimcha chora-tadbirlar to‘g‘risida",
         law=None, purpose="ko‘p qavatli uylar hovlilarini obodonlashtirish", budget=True,
         problem="38 ta ko‘p qavatli uy hovlisida bolalar maydonchasi va yoritish yo‘q",
         benefit="aholi uchun qulay va xavfsiz yashash muhiti yaratiladi",
         clauses=["Obodonlashtiriladigan ko‘p qavatli uylar manzilli ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Obodonlashtirish ishlari uchun 2 400 mln so‘m mablag‘ ajratilsin{src}.",
                  "Uy-joy kommunal xizmat ko‘rsatish bo‘limi ishlarni 2027-yil 1-iyungacha yakunlasin."]),
    dict(cat="Transport", title="Jamoat transporti yo‘nalishlarini optimallashtirish to‘g‘risida",
         law=None, purpose="jamoat transporti qatnovi muntazamligini oshirish",
         problem="7 ta mahallaga muntazam avtobus qatnovi yo‘lga qo‘yilmagan",
         benefit="aholining bekatgacha bo‘lgan o‘rtacha yo‘li 600 metrga qisqaradi",
         clauses=["Shahar ichki avtobus yo‘nalishlarining yangi sxemasi 1-ilovaga muvofiq tasdiqlansin.",
                  "Transport bo‘limi yo‘nalishlar harakat jadvalini bekatlarda va elektron xaritalarda e’lon qilsin.",
                  "Yo‘nalishlar bo‘yicha yo‘lovchilar oqimi har oyda tahlil qilib borilsin."]),
    dict(cat="Ijtimoiy himoya", title="Kam ta’minlangan oilalarga moddiy yordam ajratish tartibi to‘g‘risida",
         law=None, purpose="ijtimoiy yordamning manzilliligini oshirish", budget=True, rights=True,
         problem="moddiy yordam olish uchun murojaatlar qog‘oz shaklida qabul qilinmoqda",
         benefit="yordam “Ijtimoiy himoya yagona reyestri” asosida 10 kunda tayinlanadi",
         clauses=["Kam ta’minlangan oilalarga bir martalik moddiy yordam ajratish tartibi 1-ilovaga muvofiq tasdiqlansin.",
                  "Moddiy yordam {rights_aid}.",
                  "Moddiy yordam uchun mablag‘lar ajratilsin{src}."]),
    dict(cat="Reklama", title="Tashqi reklama vositalarini joylashtirish qoidalari to‘g‘risida",
         law=L_REKLAMA, purpose="shahar ko‘rinishini yaxshilash", business=True,
         problem="ruxsatsiz o‘rnatilgan reklama vositalari soni 140 tadan oshgan",
         benefit="reklama vositalari yagona dizayn kodi asosida joylashtiriladi",
         clauses=["Tashqi reklama vositalarini joylashtirish qoidalari 1-ilovaga muvofiq tasdiqlansin.",
                  "Reklama tarqatuvchi tadbirkorlik subyektlari reklama vositasini joylashtirish uchun ruxsatnoma olishi majburiy etib belgilansin.",
                  "Ruxsatsiz o‘rnatilgan reklama vositalari egalariga 30 kun muddatda ularni olib tashlash to‘g‘risida xabar berilsin."]),
    dict(cat="Ta’lim", title="Maktabgacha ta’lim tashkilotlariga bolalarni qabul qilish tartibi to‘g‘risida",
         law=L_TALIM, purpose="maktabgacha ta’lim tashkilotlariga qabulni shaffof tashkil etish", rights=True,
         problem="davlat bog‘chalariga navbat qog‘oz shaklida yuritiladi",
         benefit="qabul elektron navbat asosida, ochiq tartibda amalga oshiriladi",
         clauses=["Davlat maktabgacha ta’lim tashkilotlariga bolalarni qabul qilish tartibi 1-ilovaga muvofiq tasdiqlansin.",
                  "Bolalar {rights_kg}.",
                  "Maktabgacha ta’lim bo‘limi bo‘sh o‘rinlar soni haqidagi ma’lumotni har oyda e’lon qilsin."]),
    dict(cat="Bozorlar", title="Dehqon bozorlarida savdo joylari uchun to‘lovlar miqdorini belgilash to‘g‘risida",
         law=L_TADB, purpose="bozorlarda savdo joylaridan foydalanish tartibini yagonalashtirish", business=True,
         problem="bozorlarda bir xil savdo joyi uchun turli miqdorda to‘lov undirilmoqda",
         benefit="savdo joylari uchun to‘lovlar oldindan e’lon qilingan yagona miqdorda olinadi",
         clauses=["Dehqon bozorlarida savdo joylaridan foydalanganlik uchun to‘lovlarning eng yuqori miqdorlari 1-ilovaga muvofiq tasdiqlansin.",
                  "Bozorlar ma’muriyati to‘lov miqdorlarini kirish joylarida va elektron to‘lov tizimida e’lon qilsin.",
                  "Savdo joylari uchun to‘lovlar faqat naqd pulsiz shaklda qabul qilinsin."]),
    dict(cat="Qishloq xo‘jaligi", title="Sug‘oriladigan yerlardan foydalanish samaradorligini oshirish to‘g‘risida",
         law=L_YER, purpose="sug‘oriladigan yerlardan samarali foydalanish",
         problem="sug‘oriladigan yerlarning 6 foizi ikki yildan beri ekilmayapti",
         benefit="ekilmayotgan yerlar qayta ekin aylanishiga kiritiladi",
         clauses=["Ekilmayotgan sug‘oriladigan yer maydonlari ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Qishloq xo‘jaligi bo‘limi yer maydonlarini qayta ekin aylanishiga kiritish rejasini ikki oy muddatda ishlab chiqsin.",
                  "Suv xo‘jaligi bo‘limi sug‘orish tarmoqlarini ta’mirlash ishlarini 2027-yil 1-aprelgacha yakunlasin."]),
    dict(cat="Kommunal xizmatlar", title="Ichimlik suvi ta’minotini yaxshilash bo‘yicha qo‘shimcha chora-tadbirlar to‘g‘risida",
         law=None, purpose="aholini toza ichimlik suvi bilan uzluksiz ta’minlash", budget=True,
         problem="12 ta mahallada ichimlik suvi kun ora beriladi",
         benefit="ichimlik suvi bilan ta’minlanish darajasi 94 foizga yetadi",
         clauses=["Ichimlik suvi tarmoqlarini rekonstruksiya qilish manzilli dasturi 1-ilovaga muvofiq tasdiqlansin.",
                  "Dasturni amalga oshirish uchun 5 800 mln so‘m mablag‘ ajratilsin{src}.",
                  "Suv ta’minoti korxonasi ishlar borishi haqida har oyda hokimlikka axborot bersin."]),
    dict(cat="Jamoat tartibi", title="Tungi vaqtda savdo va xizmat ko‘rsatish faoliyatini tartibga solish to‘g‘risida",
         law=L_TADB, purpose="turar-joy hududlarida jamoat tartibini ta’minlash", business=True,
         problem="turar-joy binolari yonidagi ayrim muassasalar tungi vaqtda shovqin bilan ishlamoqda",
         benefit="aholining dam olish huquqi ta’minlanadi",
         clauses=["Turar-joy binolarining birinchi qavatida joylashgan umumiy ovqatlanish shoxobchalari soat 23:00 dan 06:00 gacha ovoz kuchaytirgich uskunalaridan foydalanmasligi majburiy etib belgilansin.",
                  "Qoidani buzgan tadbirkorlik subyektlariga nisbatan qonunchilikda belgilangan choralar ko‘rilsin.",
                  "Ichki ishlar bo‘limi bilan birgalikda reydlar jadvali tuzilsin."]),
    dict(cat="Transport", title="Avtoturargohlardan foydalanganlik uchun to‘lov joriy etish to‘g‘risida",
         law=L_TADB, purpose="shahar markazida avtoturargohlardan tartibli foydalanish", business=True,
         problem="shahar markazidagi avtoturargohlarda joylar uzoq muddat band qilinmoqda",
         benefit="avtoturargohlardan aylanma foydalanish ikki baravar oshadi",
         clauses=["Shahar markazidagi pullik avtoturargohlar ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Avtoturargohlardan foydalanganlik uchun soatbay to‘lov miqdori 2-ilovaga muvofiq belgilansin.",
                  "To‘lovlar mobil ilova va to‘lov terminallari orqali qabul qilinsin."]),
    dict(cat="Yer munosabatlari", title="Yer solig‘i bo‘yicha tuzatish koeffitsientlarini belgilash to‘g‘risida",
         law=L_SOLIQ, purpose="yer solig‘i bo‘yicha soliq yukini hududlar o‘rtasida adolatli taqsimlash", business=True, tax=True,
         problem="tuman ichidagi turli zonalarda yer solig‘i bir xil koeffitsientda hisoblanmoqda",
         benefit="soliq yuki yer uchastkasining joylashuviga mos ravishda belgilanadi",
         clauses=["Yuridik shaxslar uchun yer solig‘i bo‘yicha 0,7 dan 3,0 gacha tuzatish koeffitsientlari 1-ilovaga muvofiq belgilansin.",
                  "Moliya bo‘limi koeffitsientlarni davlat soliq inspeksiyasiga yetkazsin.",
                  "Davlat soliq inspeksiyasi tadbirkorlarga yangi koeffitsientlar haqida tushuntirish ishlarini olib borsin."]),
    dict(cat="Sog‘liqni saqlash", title="Oilaviy poliklinikalar faoliyatini qo‘llab-quvvatlash to‘g‘risida",
         law=None, purpose="birlamchi tibbiy yordam sifatini oshirish", budget=True,
         problem="4 ta oilaviy poliklinikada laboratoriya uskunalari eskirgan",
         benefit="aholi asosiy tahlillarni o‘z mahallasidagi poliklinikada topshira oladi",
         clauses=["Laboratoriya uskunalari bilan ta’minlanadigan oilaviy poliklinikalar ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Uskunalar xarid qilish uchun 1 150 mln so‘m mablag‘ ajratilsin{src}.",
                  "Xaridlar “Davlat xaridlari to‘g‘risida”gi Qonun talablariga muvofiq amalga oshirilsin."]),
    dict(cat="Tadbirkorlik", title="Kichik biznes subyektlariga subsidiya ajratish tartibi to‘g‘risida",
         law=L_TADB, purpose="hududda yangi ish o‘rinlari yaratishni rag‘batlantirish", business=True, budget=True,
         problem="kichik biznesni qo‘llab-quvvatlash bo‘yicha ajratilgan mablag‘lar to‘liq o‘zlashtirilmayapti",
         benefit="har yili kamida 300 ta yangi ish o‘rni yaratiladi",
         clauses=["Kichik biznes subyektlariga subsidiya ajratish tartibi 1-ilovaga muvofiq tasdiqlansin.",
                  "Subsidiya olish uchun tadbirkorlik subyektlari biznes-reja va soliq qarzi yo‘qligi haqidagi ma’lumotnomani taqdim etishi talab etilsin.",
                  "Subsidiyalar uchun 3 000 mln so‘m mablag‘ ajratilsin{src}."]),
    dict(cat="Madaniyat va sport", title="Bolalar sport maydonchalarini qurish va saqlash to‘g‘risida",
         law=None, purpose="bolalar va yoshlarning sport bilan shug‘ullanishi uchun sharoit yaratish", budget=True,
         problem="15 ta mahallada ochiq sport maydonchasi mavjud emas",
         benefit="har bir mahallada kamida bitta ochiq sport maydonchasi bo‘ladi",
         clauses=["Sport maydonchalari quriladigan mahallalar ro‘yxati 1-ilovaga muvofiq tasdiqlansin.",
                  "Maydonchalar qurilishi uchun 1 900 mln so‘m mablag‘ ajratilsin{src}.",
                  "Mahalla fuqarolar yig‘inlari maydonchalarning saqlanishi ustidan jamoatchilik nazoratini olib borsin."]),
]

VAGUE_CLAUSE = "Zarur hollarda mas’ul bo‘lim boshqa hujjatlarni ham talab qilishi mumkin."
SOURCES = [" tuman byudjetining qo‘shimcha manbalari hisobidan", " mahalliy byudjet hisobidan", " viloyat byudjetining zaxira jamg‘armasi hisobidan"]
RIGHTS_AID_OK = "kam ta’minlangan oilalar yagona reyestriga kiritilgan oilalarga tayinlansin"
RIGHTS_AID_BAD = "faqat shu hududda doimiy ro‘yxatda turgan fuqarolarga tayinlansin"
RIGHTS_KG_OK = "elektron navbat asosida, ariza berilgan sana tartibida qabul qilinsin"
RIGHTS_KG_BAD = "faqat tumanda doimiy ro‘yxatda turgan ota-onalarning farzandlari qabul qilinsin"
CYR = {"a": "а", "e": "е", "o": "о", "A": "А", "E": "Е", "O": "О", "T": "Т"}


def d_uz(d):
    return f"{d.year}-yil {d.day}-{MONTHS[d.month - 1]}"


def first_of_month(d, months_ahead):
    m = d.month - 1 + months_ahead
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def issuer_for(region_name, region_code, district, rng):
    if district is None:
        title = "Toshkent shahar hokimi" if region_code == "TSH" else f"{region_name} hokimi"
    elif district.endswith(" shahri"):
        title = district.replace(" shahri", " shahar hokimi")
    else:
        title = f"{district} hokimi"
    return title


class Command(BaseCommand):
    help = "Sintetik namuna ma’lumotlarni yaratadi (hududlar, so‘rovlar, hujjatlar, tahlillar, qarorlar)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Avval barcha so‘rovlarni o‘chirish")
        parser.add_argument("--days", type=int, default=180)

    def handle(self, *args, **opts):
        if opts["reset"]:
            RegulationRequest.objects.all().delete()
        if RegulationRequest.objects.exists():
            self.stdout.write(self.style.WARNING("Ma’lumotlar allaqachon bor. Qaytadan yaratish uchun: seed_demo --reset"))
            return
        with override_settings(MEZON_AI={**settings.MEZON_AI, "DEMO_SPEED": 0}):
            self._seed(opts["days"])

    # ------------------------------------------------------------------
    def _seed(self, days):
        User = get_user_model()
        me, created = User.objects.get_or_create(username="ekspert", defaults={
            "first_name": "Dilnoza", "last_name": "Rahimova", "is_staff": True, "is_superuser": True})
        if created or not me.has_usable_password():
            me.set_password(__import__("os").environ.get("MEZON_DEMO_PASSWORD", "change-me"))
            me.save()
        team = [me]
        for u, f, l in (("b.aliyev", "Bobur", "Aliyev"), ("m.qosimova", "Madina", "Qosimova"), ("s.tursunov", "Sanjar", "Tursunov")):
            usr, _ = User.objects.get_or_create(username=u, defaults={"first_name": f, "last_name": l})
            if not usr.has_usable_password():
                usr.set_unusable_password()
                usr.save()
            team.append(usr)

        regions = {}
        for name, short, code, col, row, districts in REGIONS:
            reg, _ = Region.objects.update_or_create(code=code, defaults={"name": name, "short": short, "grid_col": col, "grid_row": row})
            regions[code] = (reg, districts)

        # a stable invented hokim for every (region, district)
        hokims = {}
        names = [(f, l) for f in FIRST for l in LAST]
        R.shuffle(names)
        i = 0
        for code, (reg, districts) in regions.items():
            for dist in [None] + districts:
                f, l = names[i]
                i += 1
                last = l if f not in ("Nilufar", "Gulnora", "Dilfuza") else (l + "a" if l.endswith("v") else l)
                hokims[(code, dist)] = (f"{f} {last}", issuer_for(reg.name, code, dist, R))

        now = timezone.now()
        analyzer = DemoAnalyzer({**settings.MEZON_AI, "DEMO_SPEED": 0})
        codes = list(regions.keys())
        weights = [WEIGHT[c] for c in codes]
        made = 0

        plan = []
        for day in range(days, 0, -1):
            date = timezone.localtime(now - dt.timedelta(days=day)).date()
            weekday = date.weekday()
            trend = 1 + (days - day) / days * 0.35
            lam = (3.4 if weekday < 5 else 0.5) * trend
            n = self._poisson(lam)
            for _ in range(n):
                hour = R.choice([9, 9, 10, 10, 10, 11, 11, 12, 14, 14, 15, 15, 16, 16, 17, 18])
                at = timezone.make_aware(dt.datetime(date.year, date.month, date.day, hour, R.randint(0, 59)))
                plan.append(at)
        # today so far
        today = timezone.localtime(now)
        hours_so_far = list(range(9, min(today.hour, 18)))
        for h in sorted(R.sample(hours_so_far, k=min(3, len(hours_so_far)))):
            plan.append(timezone.make_aware(dt.datetime(today.year, today.month, today.day, h, R.randint(0, 59))))
        plan.sort()

        curated = self._curated_scenarios()
        used = set()
        n_plan = len(plan)
        for idx, at in enumerate(plan):
            # the newest few requests are hand-picked scenarios so the queue shows every kind of finding
            scenario = curated[n_plan - idx - 1] if n_plan - idx - 1 < len(curated) else None
            code = scenario["region"] if scenario else R.choices(codes, weights)[0]
            reg, districts = regions[code]
            dist = scenario.get("district") if scenario else (None if R.random() < 0.22 else R.choice(districts))
            hname, htitle = hokims[(code, dist)]
            if scenario:
                tpl = TEMPLATES[scenario["tpl"]]
            else:
                # real duplicates are rare: avoid repeating a topic in the same place, except ~4% of the time
                for _ in range(8):
                    tpl = R.choice(TEMPLATES)
                    if (code, dist, tpl["title"]) not in used or R.random() < 0.04:
                        break
            used.add((code, dist, tpl["title"]))
            defects = scenario["defects"] if scenario else self._defects(tpl)
            with transaction.atomic():
                req = self._make_request(reg, dist, hname, htitle, tpl, defects, at)
                self._lifecycle(req, at, now, analyzer, team, scenario)
            made += 1
            if made % 50 == 0:
                self.stdout.write(f"  … {made} ta so‘rov")

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {made} ta so‘rov, {Analysis.objects.count()} ta tahlil, {Decision.objects.count()} ta qaror."))
        self.stdout.write("Kirish: ekspert / $MEZON_DEMO_PASSWORD  (faqat mahalliy namoyish uchun)")

    @staticmethod
    def _poisson(lam):
        L, k, p = 2.718281828 ** -lam, 0, 1.0
        while True:
            p *= R.random()
            if p <= L:
                return k
            k += 1

    def _defects(self, tpl):
        d = set()
        if R.random() < 0.10:
            d.add("dead_article")
        if R.random() < 0.08:
            d.add("retroactive")
        if R.random() < 0.06:
            d.add("farmoyish")
        if tpl.get("business"):
            if R.random() < 0.30:
                d.add("immediate")
            r = R.random()
            if r < 0.20:
                d.add("no_discussion")
            elif r < 0.32:
                d.add("short_discussion")
        elif R.random() < 0.10:
            d.add("no_discussion")
        if R.random() < 0.22:
            d.add("vague")
        if R.random() < 0.10:
            d.add("mixed_script")
        if tpl.get("rights") and R.random() < 0.35:
            d.add("rights")
        if tpl.get("budget") and R.random() < 0.30:
            d.add("no_source")
        if tpl.get("tax") and R.random() < 0.75:
            d.add("competence")
        return d

    def _curated_scenarios(self):
        # index 0 = newest request
        return [
            {"region": "QAS", "district": "Yakkabog‘ tumani", "tpl": 0, "defects": {"dead_article", "vague"}, "status": "new"},
            {"region": "NAV", "district": "Xatirchi tumani", "tpl": 11, "defects": {"retroactive", "immediate"}, "status": "new"},
            {"region": "TSV", "district": "Yangiyo‘l tumani", "tpl": 12, "defects": {"competence", "no_discussion"}, "status": "new"},
            {"region": "FAR", "district": "Qo‘qon shahri", "tpl": 2, "defects": set(), "status": "new"},
            {"region": "SAM", "district": "Urgut tumani", "tpl": 6, "defects": {"rights", "mixed_script"}, "status": "new"},
            {"region": "AND", "district": None, "tpl": 14, "defects": {"short_discussion", "no_source"}, "status": "in_review"},
            {"region": "TSH", "district": "Chilonzor tumani", "tpl": 3, "defects": set(), "status": "in_review"},
        ]

    # ------------------------------------------------------------------
    def _make_request(self, reg, dist, hname, htitle, tpl, defects, at):
        place = dist or reg.name
        doc_type = "farmoyish" if "farmoyish" in defects else "qaror"
        sub = at.date()
        req = RegulationRequest.objects.create(
            region=reg, district=dist or "", issuer_name=hname, issuer_title=htitle, title=tpl["title"],
            doc_type=doc_type, category=tpl["cat"], submitted_at=at, status="new",
            draft_number=f"{R.randint(100, 499)}-{R.randint(1, 9)}-{R.randint(10, 99)}-{'Q' if doc_type == 'qaror' else 'F'}/{sub:%y}",
            summary=f"{tpl['purpose'][0].upper() + tpl['purpose'][1:]}. {tpl['benefit'][0].upper() + tpl['benefit'][1:]}.",
        )
        Event.objects.create(request=req, kind=Event.Kind.SUBMITTED, created_at=at, text=f"{htitle} · {hname}")

        art = "25" if "dead_article" in defects else R.choice(["6", "6", "6"])
        basis = f"{L_MDH} {art}-moddasiga"
        if tpl["law"]:
            basis += f", {tpl['law']}ga"
        form_word = "QARORI" if doc_type == "qaror" else "FARMOYISHI"
        verb = "qaror qilaman" if doc_type == "qaror" else "farmoyish beraman"
        clauses = []
        for c in tpl["clauses"]:
            c = c.replace("{src}", "" if "no_source" in defects else R.choice(SOURCES))
            c = c.replace("{rights_aid}", RIGHTS_AID_BAD if "rights" in defects else RIGHTS_AID_OK)
            c = c.replace("{rights_kg}", RIGHTS_KG_BAD if "rights" in defects else RIGHTS_KG_OK)
            clauses.append(c)
        if "farmoyish" in defects:
            clauses.insert(1, "Ushbu tartib barcha jismoniy va yuridik shaxslar uchun majburiy hisoblansin.")
        if "vague" in defects:
            clauses.insert(2, VAGUE_CLAUSE)
        if "retroactive" in defects:
            past = first_of_month(sub, -R.choice([1, 2, 3]))
            clauses.append(f"Ushbu {doc_type} {d_uz(past)}dan boshlab yuzaga kelgan munosabatlarga nisbatan qo‘llaniladi.")
        elif "immediate" in defects:
            clauses.append(f"Ushbu {doc_type} rasmiy e’lon qilingan kundan boshlab kuchga kiradi.")
        elif tpl.get("business"):
            clauses.append(f"Ushbu {doc_type} {d_uz(first_of_month(sub, 4))}dan kuchga kiradi.")
        else:
            clauses.append(f"Ushbu {doc_type} rasmiy e’lon qilingan kundan boshlab kuchga kiradi.")
        clauses.append(f"Mazkur {doc_type} ijrosini nazorat qilish hokimning birinchi o‘rinbosari zimmasiga yuklansin.")

        lines = [f"{htitle.upper()}NING", form_word, "", tpl["title"], "",
                 f"{basis} muvofiq, shuningdek {tpl['purpose']} maqsadida {verb}:", ""]
        lines += [f"{i}. {c}" for i, c in enumerate(clauses, 1)]
        surname = hname.split()[-1]
        lines += ["", f"{htitle}                    {hname.split()[0][0]}. {surname}", f"{place}, {d_uz(sub)}"]
        text = "\n".join(lines)
        if "mixed_script" in defects:
            text = self._mix(text, tpl["title"])
        pages = max(1, len(text) // 1600 + 1)
        docs = [Document(request=req, kind="draft", title=f"{doc_type.capitalize()} loyihasi", text=text, pages=pages + R.randint(0, 1), order=0)]

        disc_days = None if "no_discussion" in defects else (R.randint(6, 12) if "short_discussion" in defects else R.randint(15, 30))
        note = [f"“{tpl['title']}” {doc_type} loyihasiga", "TUSHUNTIRISH XATI", "",
                f"Loyiha {tpl['purpose']} maqsadida ishlab chiqildi.",
                f"Hozirgi vaqtda {tpl['problem']}.",
                f"Loyiha qabul qilinishi natijasida {tpl['benefit']}."]
        if disc_days:
            note.append(f"Loyiha jamoatchilik muhokamasiga qo‘yildi ({disc_days} kun), {R.randint(3, 40)} ta taklif kelib tushdi.")
        note.append("Loyihani amalga oshirish qo‘shimcha shtat birliklarini talab qilmaydi.")
        docs.append(Document(request=req, kind="note", title="Tushuntirish xati", text="\n".join(note), pages=R.randint(1, 2), order=1))

        if tpl.get("budget") and R.random() < 0.8:
            amount = R.choice(["1 150", "1 900", "2 400", "3 000", "5 800"])
            docs.append(Document(request=req, kind="finance", title="Moliyaviy-iqtisodiy asoslash", order=2, pages=R.randint(1, 3),
                                 text=f"MOLIYAVIY-IQTISODIY ASOSLASH\n\nLoyihani amalga oshirish uchun jami {amount} mln so‘m talab etiladi.\n"
                                      f"Xarajatlar smetasi: materiallar 62%, ishlar 31%, loyiha-smeta hujjatlari 7%.\n"
                                      "Kutilayotgan ijtimoiy samara tushuntirish xatida keltirilgan."))
        if disc_days:
            d2 = sub - dt.timedelta(days=R.randint(3, 10))
            d1 = d2 - dt.timedelta(days=disc_days)
            k = R.randint(3, 40)
            docs.append(Document(request=req, kind="discussion", title="Jamoatchilik muhokamasi natijalari", order=3, pages=R.randint(1, 3),
                                 text=f"JAMOATCHILIK MUHOKAMASI NATIJALARI\n\nLoyiha {d_uz(d1)}dan {d_uz(d2)}gacha jamoatchilik muhokamasiga qo‘yildi ({disc_days} kun).\n"
                                      f"Muhokama davomida {k} ta taklif kelib tushdi, shundan {max(1, k // 3)} tasi inobatga olindi.\n"
                                      "Takliflar yig‘ma jadvali ilova qilinadi."))
        if R.random() < 0.55:
            docs.append(Document(request=req, kind="annex", title="1-ilova", order=4, pages=R.randint(1, 6),
                                 text=f"1-ILOVA\n\n{tpl['clauses'][0].split(' 1-ilova')[0]}\n\n"
                                      + "\n".join(f"{j}. {place}, {R.choice(['Mustaqillik', 'Navro‘z', 'Bog‘ishamol', 'Amir Temur', 'Do‘stlik', 'Istiqlol'])} ko‘chasi, {R.randint(1, 120)}-uy"
                                                  for j in range(1, R.randint(4, 9)))))
        if R.random() < 0.6:
            n_docs = len(docs) + 1
            docs.append(Document(request=req, kind="letter", title="Kuzatuv xati", order=5, pages=1,
                                 text=f"Hurmatli adliya boshqarmasi!\n\n{htitle} {doc_type} loyihasini huquqiy ekspertizadan o‘tkazish uchun yuboradi.\n"
                                      f"Ilova: {n_docs} ta hujjat.\n\n{htitle}                    {hname}"))
        Document.objects.bulk_create(docs)
        return req

    @staticmethod
    def _mix(text, title):
        target = title.split()[-2] if len(title.split()) > 2 else title.split()[0]
        for ch in ("a", "e", "o"):
            if ch in target:
                bad = target.replace(ch, CYR[ch], 1)
                return text.replace(target, bad, 1)
        return text

    def _lifecycle(self, req, at, now, analyzer, team, scenario):
        age_days = (now - at).total_seconds() / 86400
        if scenario:
            status = scenario["status"]
        elif age_days < 1:
            status = "new" if R.random() < 0.8 else "in_review"
        elif age_days < 4:
            status = R.choices(["new", "in_review", "decided"], [0.3, 0.4, 0.3])[0]
        elif age_days < 10:
            status = "in_review" if R.random() < 0.15 else "decided"
        else:
            status = "in_review" if R.random() < 0.02 else "decided"

        if status == "new":
            return
        expert = R.choice(team)
        opened = min(now - dt.timedelta(minutes=5), at + dt.timedelta(hours=R.uniform(0.5, 30)))
        req.status = "in_review"
        req.save(update_fields=["status"])
        Event.objects.create(request=req, kind=Event.Kind.OPENED, actor=expert, created_at=opened, text="Tekshiruv boshlandi")
        if status == "in_review" and R.random() < 0.3 and not scenario:
            return

        result = None
        for event in services.run_analysis(req, expert, analyzer=analyzer, render_html=False):
            result = event
        analysis = Analysis.objects.get(pk=result["analysis_id"])
        t = opened + dt.timedelta(seconds=2)
        steps = []
        for s in analysis.steps:
            t += dt.timedelta(milliseconds=R.randint(500, 2600))
            steps.append({**s, "ms": int((t - opened).total_seconds() * 1000)})
        analysis.steps = steps
        analysis.started_at = opened
        analysis.finished_at = t
        analysis.save(update_fields=["steps", "started_at", "finished_at"])
        Event.objects.filter(request=req, kind=Event.Kind.ANALYZED).update(created_at=t)

        if status != "decided":
            return
        rec = analysis.recommendation
        p_accept = {"accept": 0.95, "revise": 0.62, "reject": 0.1}[rec]
        outcome = "accept" if R.random() < p_accept else "reject"
        decided_at = min(now - dt.timedelta(minutes=1), t + dt.timedelta(hours=R.uniform(0.3, 60)))
        comments = {
            "accept": ["", "", "AI tahlili bilan tanishdim, jiddiy ziddiyat yo‘q.", "Kamchiliklar hokimlik bilan kelishildi, qabul qilinsin.",
                       "Tilshunoslik xatosi tuzatilishi sharti bilan."],
            "reject": ["Huquqiy asos sifatida kuchini yo‘qotgan modda keltirilgan.", "Orqaga qaytish kuchi berilgan, qayta ishlash kerak.",
                       "Kengash vakolatidagi masala, hokim qarori bilan hal qilib bo‘lmaydi.", "Jamoatchilik muhokamasi o‘tkazilmagan.",
                       "Teng huquqlilik prinsipiga zid cheklov bor.", "Tadbirkorlar uchun kuchga kirish muddati 3 oydan kam."],
        }
        if outcome == "reject":
            top = analysis.findings.first()
            comment = (f"{top.title}. {top.suggestion}" if top and R.random() < 0.7 else R.choice(comments["reject"]))
        else:
            comment = R.choice(comments["accept"])
        Decision.objects.create(request=req, outcome=outcome, comment=comment, decided_by=expert, decided_at=decided_at,
                                analysis=analysis, ai_recommendation=rec)
        req.status = "accepted" if outcome == "accept" else "rejected"
        req.save(update_fields=["status"])
        Event.objects.create(request=req, kind=Event.Kind.ACCEPTED if outcome == "accept" else Event.Kind.REJECTED,
                             actor=expert, created_at=decided_at, text=comment[:280] or ("Qabul qilindi" if outcome == "accept" else "Rad etildi"))
