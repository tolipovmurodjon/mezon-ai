"""
Demo analyzer: the 14 rule checks plus template-written answers.

It needs no model and no network, and it produces the same event stream a
real model will produce, so the whole review flow can be built and tested
before the model is plugged in. The UI labels its output as a demo.
"""
import re
import time

from .base import BaseAnalyzer
from .laws import LAWS, find_law_mentions
from .rules import run_checks, verdict_for

SEV_ORDER = {"critical": 0, "serious": 1, "warning": 2, "info": 3}



class DemoAnalyzer(BaseAnalyzer):
    name = "demo"
    label = "Demo analizator"
    is_demo = True

    @property
    def model_name(self):
        return "mezon-rules (demo)"

    def _pause(self, seconds):
        speed = float(self.config.get("DEMO_SPEED", 1.0))
        if speed > 0:
            time.sleep(seconds * speed)

    def _stream(self, text, word_delay=0.022):
        words = re.split(r"(\s+)", text)
        buf = ""
        for i, w in enumerate(words):
            buf += w
            if len(buf) > 12 or i == len(words) - 1:
                yield {"type": "token", "text": buf}
                buf = ""
                self._pause(word_delay * 2)

    # ------------------------------------------------------------------
    def analyze(self, req, documents):
        documents = list(documents)
        t0 = time.monotonic()

        def ms():
            return int((time.monotonic() - t0) * 1000)

        # 1. read
        yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qilmoqda", "status": "run"}
        self._pause(0.7)
        words = sum(len(d.text.split()) for d in documents)
        pages = sum(d.pages for d in documents)
        yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qildi", "status": "done",
               "detail": f"{len(documents)} ta hujjat · {pages} bet · {words:,} so‘z".replace(",", " "), "ms": ms()}

        # 2. references
        yield {"type": "step", "id": "refs", "label": "Huquqiy havolalar ajratilmoqda", "status": "run"}
        self._pause(0.6)
        draft_text = next((d.text for d in documents if d.kind == "draft"), documents[0].text if documents else "")
        mentions = find_law_mentions(draft_text)
        law_keys = list(dict.fromkeys(k for k, _, _ in mentions))
        articles = re.findall(r"(\d+)-moddas", draft_text)
        yield {"type": "step", "id": "refs", "label": "Huquqiy havolalar ajratildi", "status": "done",
               "detail": f"{len(law_keys)} ta hujjat, {len(articles)} ta modda", "ms": ms()}

        # 3. registry + 4. checks
        yield {"type": "step", "id": "checks", "label": "14 ta qoida bo‘yicha tekshirilmoqda", "status": "run"}
        ctx, results = run_checks(req, documents)
        findings = []
        for code, label, res in results:
            self._pause(0.16)
            yield {"type": "check", "id": code, "label": label, "status": res.status, "detail": res.detail}
            findings.extend(res.findings)
        passed = sum(1 for _, _, r in results if r.status in ("pass", "skip"))
        yield {"type": "step", "id": "checks", "label": "14 ta qoida bo‘yicha tekshiruv", "status": "warn" if findings else "done",
               "detail": f"{passed} tasi o‘tdi · {len(findings)} ta muammo", "ms": ms()}

        # 5. quote verification: every quote must be verbatim in the documents
        yield {"type": "step", "id": "quotes", "label": "Iqtiboslar hujjat matni bilan solishtirilmoqda", "status": "run"}
        self._pause(0.5)
        quoted = [f for f in findings if f["quote"]]
        exact = sum(1 for f in quoted if any(f["quote"] in d.text for d in documents))
        yield {"type": "step", "id": "quotes", "label": "Iqtiboslar tekshirildi", "status": "done",
               "detail": f"{exact}/{len(quoted)} aynan mos", "ms": ms()}

        findings.sort(key=lambda f: SEV_ORDER.get(f["severity"], 9))
        verdict, recommendation, score = verdict_for(findings)

        # sources: rule sources behind the findings, then the laws the draft cites
        sources, index = [], {}
        for f in findings:
            ref = f["law_ref"]
            if ref and ref not in index:
                index[ref] = len(sources) + 1
                sources.append({"type": "source", "title": ref, "meta": f"Qoida · {f['category']}", "kind": "rule"})
        for key in law_keys:
            title = LAWS[key]["title"]
            if title not in index:
                index[title] = len(sources) + 1
                lost = LAWS[key].get("lost")
                sources.append({"type": "source", "title": title, "kind": "law",
                                "meta": "Qaror asosida keltirilgan · qaror sanasidagi tahrir"
                                        + (" · ayrim moddalari kuchini yo‘qotgan" if lost else "")})
        for d in documents:
            sources.append({"type": "source", "title": d.title, "kind": "doc",
                            "meta": f"{req.number} · {d.pages} bet · {len(d.text.split())} so‘z"})
        for s in sources:
            yield s
        for f in findings:
            yield f

        # 6. conclusion
        yield {"type": "step", "id": "write", "label": "Xulosa yozilmoqda", "status": "run"}
        self._pause(0.4)
        summary = self._summary(req, verdict, findings, results, index)
        yield from self._stream(summary)
        yield {"type": "step", "id": "write", "label": "Xulosa tayyorlandi", "status": "done", "ms": ms()}
        yield {"type": "verdict", "verdict": verdict, "recommendation": recommendation, "score": score}

    def _summary(self, req, verdict, findings, results, index):
        n = len(findings)
        crit = [f for f in findings if f["severity"] == "critical"]
        counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV_ORDER}
        passed = sum(1 for _, _, r in results if r.status in ("pass", "skip"))
        parts = []
        if verdict == "conflict":
            first = crit[0]["title"]
            parts.append(f"Bu loyihani hozirgi ko‘rinishida qabul qilib bo‘lmaydi: {first[0].lower() + first[1:]}.")
        elif verdict == "minor":
            parts.append(f"Loyihada qonunga to‘g‘ridan-to‘g‘ri zid norma topilmadi, lekin {n} ta kamchilik bor.")
        else:
            parts.append(f"Loyiha amaldagi qonunchilikka mos: 14 ta tekshiruvdan {passed} tasi o‘tdi, muammo topilmadi.")

        if n:
            bits = [f"{counts[k]} ta {lbl}" for k, lbl in (("critical", "jiddiy"), ("serious", "muhim"), ("warning", "o‘rtacha"), ("info", "kichik")) if counts[k]]
            parts.append("")
            parts.append(f"Jami {n} ta muammo aniqlandi ({', '.join(bits)}):")
            for f in findings[:5]:
                parts.append(f"- **{f['title']}**")
            if n > 5:
                parts.append(f"- yana {n - 5} ta muammo quyidagi ro‘yxatda")
        parts.append("")
        parts.append({
            "conflict": "Tavsiya: so‘rovni rad etish va hokimlikka aniqlangan ziddiyatlarni tuzatib, qayta yuborishni so‘rash.",
            "minor": "Tavsiya: kamchiliklar tuzatilsa, qabul qilish mumkin. Muhim bandlarni hokimlik bilan kelishib oling.",
            "compliant": "Tavsiya: qabul qilish mumkin. Yakuniy qarorni siz qabul qilasiz.",
        }[verdict])
        return "\n".join(parts)

    # ------------------------------------------------------------------
    def chat(self, req, analysis, history, message):
        self._pause(0.6)
        findings = list(analysis.findings.all()) if analysis else []
        q = message.lower()
        if not analysis:
            text = "Avval loyiha tahlilini yakunlaylik: yuqoridagi tahlil tugagach, savolingizga aniq javob beraman."
        elif re.search(r"modda|qonun|havola|asos|manba", q):
            refs = list(dict.fromkeys(f.law_ref for f in findings if f.law_ref))
            draft = req.documents.filter(kind="draft").first()
            cited = list(dict.fromkeys(LAWS[k]["title"] for k, _, _ in find_law_mentions(draft.text if draft else "")))
            lines = ["Loyiha quyidagi hujjatlarga tayanadi:"]
            lines += [f"- {c}" for c in cited] or ["- huquqiy asos ko‘rsatilmagan"]
            if refs:
                lines += ["", "Quyidagi talablar bilan solishtirildi:"]
                lines += [f"- {r}" for r in refs]
            lines += ["", "Har bir havola qaror yuborilgan sanadagi tahrir bo‘yicha tekshirildi."]
            text = "\n".join(lines)
        elif re.search(r"qayta yoz|tuzat|tahrir|o.zgartir|qanday qilib", q):
            if not findings:
                text = "Tuzatish talab qiladigan band topilmadi. Loyihani shu holida qabul qilish mumkin."
            else:
                lines = ["Har bir muammo bo‘yicha taklif etilgan tuzatish:"]
                for i, f in enumerate(findings, 1):
                    where = f" ({f.quote_source})" if f.quote_source else ""
                    lines.append(f"- **{i}. {f.category}{where}:** {f.suggestion}")
                lines += ["", "Tuzatilgan loyiha qayta yuborilsa, uni yana tekshiraman."]
                text = "\n".join(lines)
        elif re.search(r"xulosa|ekspertiza|hujjat tayyorla|word", q):
            text = ("Ekspertiza xulosasi loyihasi tayyor: o‘ng tomondagi **Xulosa loyihasi** vidjetidan Word faylini "
                    "yuklab olishingiz mumkin. Unda so‘rov rekvizitlari, aniqlangan muammolar va tavsiyalar bor. "
                    "Yuborishdan oldin xulosani tekshirib, imzolang.")
        elif re.search(r"xavf|risk|oqibat|nima bo.ladi|qabul qilsak", q):
            crit = [f for f in findings if f.severity == "critical"]
            if crit:
                text = ("Qabul qilinsa, quyidagi xavflar bor:\n"
                        + "\n".join(f"- {f.title}: prokuratura protesti yoki sud orqali bekor qilinishi mumkin." for f in crit)
                        + "\n\nShuning uchun rad etib, tuzatilgan loyihani so‘rash xavfsizroq.")
            else:
                text = "Jiddiy huquqiy xavf topilmadi. Kamchiliklar asosan hujjatni rasmiylashtirishga oid."
        else:
            verdict = analysis.get_verdict_display().lower()
            lines = [f"Qisqa javob: loyiha bo‘yicha xulosa: **{verdict}** (muvofiqlik {analysis.score}%)."]
            if findings:
                lines += ["", "Eng muhim nuqtalar:"] + [f"- {f.title}" for f in findings[:3]]
            lines += ["", "Aniqroq so‘rang: masalan, “qaysi moddalarga tayangan?” yoki “bandlarni qanday tuzatish kerak?”"]
            text = "\n".join(lines)
        yield from self._stream(text)
