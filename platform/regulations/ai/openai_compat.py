"""
Adapter for any OpenAI-compatible server: vLLM, Ollama, LM Studio, TGI, llama.cpp.

This is the quickest way to plug in a fine-tuned open-source model:

    vllm serve ./mezon-qonun --served-model-name mezon-qonun --port 8000
    MEZON_AI_BACKEND=openai MEZON_AI_URL=http://127.0.0.1:8000/v1 MEZON_AI_MODEL=mezon-qonun

How it works: the 14 rule checks run first, because they are deterministic.
Then the model reads the documents and the check results and returns
structured JSON. Any quote the model gives that is not verbatim in the documents
is dropped, so a made-up citation never reaches the expert.
"""
import json
import re
import time
import urllib.error
import urllib.request

from .base import AnalyzerError, BaseAnalyzer
from .rules import run_checks, verdict_for

SYSTEM_ANALYZE = """Siz Mezon: O‘zbekiston qonunchiligi bo‘yicha huquqiy ekspert yordamchisisiz.
Vazifa: hokimlik qaror loyihasini amaldagi qonunlar, Konstitutsiya va etik me’yorlarga muvofiqligini tekshirish.
Faqat JSON qaytaring, boshqa matnsiz:
{"verdict": "compliant|minor|conflict",
 "recommendation": "accept|revise|reject",
 "score": 0-100,
 "summary": "birinchi gap: oddiy tilda asosiy xulosa. Keyin '- ' bilan muammolar ro‘yxati.",
 "findings": [{"code": "qisqa_kod", "category": "toifa", "severity": "critical|serious|warning|info",
               "title": "...", "explanation": "...", "quote": "hujjatdan AYNAN ko‘chirma",
               "quote_source": "Qaror loyihasi, 3-band", "law_ref": "qonun nomi, modda",
               "law_text": "qonun talabi", "suggestion": "tuzatish taklifi"}]}
Qoidalar: iqtibos hujjat matnida so‘zma-so‘z bo‘lishi shart. Ishonchingiz komil bo‘lmasa, buni ochiq yozing.
Yakuniy qarorni inson qabul qiladi: siz faqat tavsiya berasiz."""

SYSTEM_CHAT = """Siz Mezon: huquqiy ekspert yordamchisisiz. Ekspertning savollariga o‘zbek tilida (lotin),
qisqa va aniq javob bering. Avval bitta oddiy gap bilan javob, keyin kerak bo‘lsa '- ' bilan ro‘yxat.
Faqat berilgan hujjatlar va tahlilga tayaning; bilmasangiz, shuni ayting."""


class OpenAICompatAnalyzer(BaseAnalyzer):
    name = "openai"
    label = "Mezon AI"

    def _request(self, payload, stream=False):
        url = self.config["URL"].rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config.get("API_KEY"):
            headers["Authorization"] = f"Bearer {self.config['API_KEY']}"
        body = {"model": self.config["MODEL"], "stream": stream, **payload}
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=self.config.get("TIMEOUT", 180))
        except urllib.error.HTTPError as exc:
            raise AnalyzerError(f"Model {exc.code} qaytardi: {exc.read()[:300].decode('utf-8', 'replace')}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AnalyzerError(f"Modelga ulanib bo‘lmadi ({url}): {exc}") from exc

    def analyze(self, req, documents):
        documents = list(documents)
        t0 = time.monotonic()
        ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731

        yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qildi", "status": "done",
               "detail": f"{len(documents)} ta hujjat · {sum(len(d.text.split()) for d in documents)} so‘z", "ms": ms()}

        yield {"type": "step", "id": "checks", "label": "14 ta qoida bo‘yicha tekshirilmoqda", "status": "run"}
        _, results = run_checks(req, documents)
        rule_findings = []
        for code, label, res in results:
            yield {"type": "check", "id": code, "label": label, "status": res.status, "detail": res.detail}
            rule_findings.extend(res.findings)
        yield {"type": "step", "id": "checks", "label": "14 ta qoida bo‘yicha tekshiruv", "status": "done",
               "detail": f"{len(rule_findings)} ta muammo", "ms": ms()}

        yield {"type": "step", "id": "model", "label": f"{self.model_name} hujjatlarni tahlil qilmoqda", "status": "run"}
        docs_text = "\n\n".join(f"### {d.title} ({d.get_kind_display()})\n{d.text}" for d in documents)
        checks_text = "\n".join(f"- {label}: {res.status} — {res.detail}" for _, label, res in results)
        user = (f"So‘rov: {req.number}\nKimdan: {req.issuer_title} ({req.issuer_name}), {req.source_label}\n"
                f"Nomi: {req.title}\nShakli: {req.get_doc_type_display()} · Soha: {req.category}\n"
                f"Yuborilgan: {req.submitted_at:%d.%m.%Y}\n\nQoidalar tekshiruvi natijasi:\n{checks_text}\n\nHujjatlar:\n{docs_text}")
        with self._request({
            "messages": [{"role": "system", "content": SYSTEM_ANALYZE}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            content = data["choices"][0]["message"]["content"]
            result = json.loads(re.search(r"\{.*\}", content, re.S).group(0))
        except Exception as exc:
            raise AnalyzerError("Model JSON formatida javob bermadi") from exc
        yield {"type": "step", "id": "model", "label": "Model tahlili tayyor", "status": "done", "ms": ms()}

        # merge: rule findings first, then model findings whose code is new
        seen = {f["code"] for f in rule_findings}
        merged = list(rule_findings)
        dropped = 0
        for f in result.get("findings", []):
            if f.get("code") in seen:
                continue
            quote = (f.get("quote") or "").strip()
            if quote and not any(quote in d.text for d in documents):
                f["quote"] = ""  # citation verifier: never show a quote we cannot find
                dropped += 1
            merged.append({"type": "finding", "severity": "warning", "category": "Model tahlili", **f})
        yield {"type": "step", "id": "quotes", "label": "Iqtiboslar tekshirildi", "status": "warn" if dropped else "done",
               "detail": f"{dropped} ta tasdiqlanmagan iqtibos olib tashlandi" if dropped else "barchasi aynan mos", "ms": ms()}

        for d in documents:
            yield {"type": "source", "title": d.title, "kind": "doc", "meta": f"{req.number} · {d.pages} bet"}
        for f in merged:
            if f.get("law_ref"):
                yield {"type": "source", "title": f["law_ref"], "kind": "law", "meta": f.get("category", "")}
        for f in merged:
            yield f

        summary = result.get("summary") or ""
        for i in range(0, len(summary), 24):
            yield {"type": "token", "text": summary[i:i + 24]}

        # the rules keep a floor: a critical rule hit can never come out as "compliant"
        rv, rr, rs = verdict_for(rule_findings)
        verdict = result.get("verdict") or rv
        if rv == "conflict":
            verdict, rec = "conflict", "reject"
        else:
            rec = result.get("recommendation") or rr
        yield {"type": "verdict", "verdict": verdict, "recommendation": rec, "score": result.get("score", rs)}

    def chat(self, req, analysis, history, message):
        context = f"So‘rov: {req.number} · {req.title}\n"
        if analysis:
            context += f"Tahlil xulosasi: {analysis.get_verdict_display()} ({analysis.score}%)\n{analysis.summary}\n"
            context += "\n".join(f"- [{f.severity}] {f.title}: {f.explanation}" for f in analysis.findings.all())
        docs = "\n\n".join(f"### {d.title}\n{d.text[:6000]}" for d in req.documents.all())
        messages = [{"role": "system", "content": SYSTEM_CHAT + "\n\n" + context + "\n\nHujjatlar:\n" + docs}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
        messages.append({"role": "user", "content": message})
        with self._request({"messages": messages, "temperature": 0.2}, stream=True) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    delta = json.loads(chunk)["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield {"type": "token", "text": delta}
