"""
Chat through the Mezon model API (OpenAI-compatible, non-streaming) with the
So'rov's documents as context. Returns the model's answer plus the law-tool
calls it made (mezon_calls), so the page can show them as checklist rows.
"""
import json
import time
import re
import urllib.error
import urllib.request

from django.conf import settings

from .base import AnalyzerError

MODELS = {
    "qwen": {"label": "Qwen + qonun vositalari", "model": "qwen-base-tools", "use_tools": False},
    "mezon-lm": {"label": "Mezon-LM (bizning model)", "model": "mezon-lm", "use_tools": True},
    "demo": {"label": "Demo", "model": "demo", "use_tools": False},
}
DEFAULT = "mezon-lm"
TOOL_LABELS = {
    "search_law": "Qonun qidirildi",
    "law_as_of": "Qonun matni sana bo‘yicha o‘qildi",
    "verify_quote": "Iqtibos tekshirildi",
}
SYSTEM = ("Siz Mezon: O‘zbekiston mahalliy qarorlari bo‘yicha huquqiy ekspert yordamchisisiz. "
          "Ekspertning savoliga o‘zbek tilida (lotin), qisqa va aniq javob bering. Har bir xulosada qonun nomi, modda "
          "va sanani keltiring. Hech qachon “asossiz”, “noqonuniy” demang: “ehtimoliy buzilish — ekspert ko‘rib chiqadi” "
          "deb yozing. Qonun vositalari natijasini xom JSON ko‘rinishida ko‘rsatmang. Faqat berilgan qaror matni va "
          "qonun vositalariga tayaning.")


def _post(messages, cfg, tools=True):
    base = settings.MEZON_AI.get("URL", "").rstrip("/")
    body = {"model": cfg["model"], "messages": messages, "temperature": 0.2}
    if cfg["use_tools"] and tools:
        body["use_tools"] = True
    headers = {"Content-Type": "application/json"}
    if settings.MEZON_AI.get("API_KEY"):
        headers["Authorization"] = "Bearer " + settings.MEZON_AI["API_KEY"]
    r = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    data = None
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=max(180, int(settings.MEZON_AI.get("TIMEOUT", 180)))) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code >= 500 and attempt < 2:  # tunnel / gateway hiccup: try again
                time.sleep(3)
                continue
            break
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if "timed out" in str(exc) or isinstance(exc, TimeoutError):
                break
            if attempt < 2:
                time.sleep(3)
    if data is None:
        exc = last
        if isinstance(exc, urllib.error.HTTPError) and exc.code in (502, 503, 504, 521, 522, 523, 530):
            raise AnalyzerError("Mezon-LM hozir mavjud emas.") from exc
        if isinstance(exc, urllib.error.HTTPError):
            raise AnalyzerError(f"Model {exc.code} qaytardi: {exc.read()[:200].decode('utf-8', 'replace')}") from exc
        if "timed out" in str(exc) or isinstance(exc, TimeoutError):
            raise AnalyzerError("Model 180 soniyada javob bermadi. Birozdan keyin qayta urinib ko‘ring.") from exc
        raise AnalyzerError("Mezon-LM hozir mavjud emas.") from exc
    try:
        answer = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise AnalyzerError("Model kutilmagan javob qaytardi") from exc
    answer = clean_answer(re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip())
    return answer, data.get("mezon_calls") or [], data.get("mezon_seconds")


def _finish(messages, cfg, answer, calls, secs):
    """If the last turn was a tool result or empty, ask once more for the plain final answer."""
    if not answer:
        again = messages + [{"role": "user", "content": "Yakuniy javobni oddiy o‘zbekcha matn bilan yozing (JSON emas): qisqa xulosa, qonun, modda va sana."}]
        answer, more, s2 = _post(again, cfg, tools=False)
        calls = calls + more
        secs = (secs or 0) + (s2 or 0)
    return answer, calls, secs, cfg


def _clean_history(history):
    return [{"role": m["role"], "content": clean_answer(m["content"])} for m in history[-6:] if clean_answer(m["content"])]


def _post(messages, cfg, tools=True):
    base = settings.MEZON_AI.get("URL", "").rstrip("/")
    body = {"model": cfg["model"], "messages": messages, "temperature": 0.2}
    if cfg["use_tools"] and tools:
        body["use_tools"] = True
    headers = {"Content-Type": "application/json"}
    if settings.MEZON_AI.get("API_KEY"):
        headers["Authorization"] = "Bearer " + settings.MEZON_AI["API_KEY"]
    r = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    data = None
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=max(180, int(settings.MEZON_AI.get("TIMEOUT", 180)))) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last = exc
            break
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if "timed out" in str(exc) or isinstance(exc, TimeoutError):
                break
            if attempt < 2:
                time.sleep(3)
    if data is None:
        exc = last
        if isinstance(exc, urllib.error.HTTPError) and exc.code in (502, 503, 504, 521, 522, 523, 530):
            raise AnalyzerError("Mezon-LM hozir mavjud emas.") from exc
        if isinstance(exc, urllib.error.HTTPError):
            raise AnalyzerError(f"Model {exc.code} qaytardi: {exc.read()[:200].decode('utf-8', 'replace')}") from exc
        if "timed out" in str(exc) or isinstance(exc, TimeoutError):
            raise AnalyzerError("Model 180 soniyada javob bermadi. Birozdan keyin qayta urinib ko‘ring.") from exc
        raise AnalyzerError("Mezon-LM hozir mavjud emas.") from exc
    try:
        answer = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise AnalyzerError("Model kutilmagan javob qaytardi") from exc
    answer = clean_answer(re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip())
    return answer, data.get("mezon_calls") or [], data.get("mezon_seconds")


def _finish(messages, cfg, answer, calls, secs):
    """If the last turn was a tool result or empty, ask once more for the plain final answer."""
    if not answer:
        again = messages + [{"role": "user", "content": "Yakuniy javobni oddiy o‘zbekcha matn bilan yozing (JSON emas): qisqa xulosa, qonun, modda va sana."}]
        answer, more, s2 = _post(again, cfg, tools=False)
        calls = calls + more
        secs = (secs or 0) + (s2 or 0)
    return answer, calls, secs, cfg


def _clean_history(history):
    out = []
    for m in history[-6:]:
        c = clean_answer(m.get("content", ""))
        if c:
            out.append({"role": m["role"], "content": c})
    return out


def ask_model(req, history, message, key):
    cfg = MODELS.get(key) or MODELS[DEFAULT]
    docs = "\n\n".join(f"### {d.title}\n{d.text[:9000]}" for d in req.documents.all())
    analysis = req.latest_analysis
    ctx = f"So‘rov: {req.number} · {req.title}\nKimdan: {req.source_label}; {req.issuer_name}\nSana: {req.submitted_at:%d.%m.%Y}\n"
    if analysis:
        ctx += "Mezon qoida tekshiruvi: " + "; ".join(f.title for f in analysis.findings.all()) + "\n"
    messages = [{"role": "system", "content": SYSTEM + "\n\n" + ctx + "\nHujjatlar:\n" + docs}]
    messages += _clean_history(history)
    messages.append({"role": "user", "content": message})
    return _finish(messages, cfg, *_post(messages, cfg))


def ask_free(history, message, key):
    """Standalone chat: no decision attached."""
    cfg = MODELS.get(key) or MODELS[DEFAULT]
    messages = [{"role": "system", "content": SYSTEM}] + _clean_history(history) + [{"role": "user", "content": message}]
    return _finish(messages, cfg, *_post(messages, cfg))


def _prose(o, depth=0):
    """A JSON verdict from the model, turned into plain Uzbek lines (never show raw JSON)."""
    def label(k):
        return str(k).replace("_", " ").capitalize()
    pad = "  " * depth
    if isinstance(o, dict):
        out = []
        for k, v in o.items():
            if isinstance(v, (str, int, float)) or v is None:
                out.append(f"{pad}**{label(k)}:** {str(v).replace('_', ' ')}")
            else:
                out.append(f"{pad}**{label(k)}:**")
                out.append(_prose(v, depth + 1))
        return chr(10).join(out)
    if isinstance(o, list):
        out = []
        for v in o:
            if isinstance(v, dict):
                out.append(f"{pad}- " + "; ".join(f"{label(k)}: {str(x)[:200]}" for k, x in v.items() if isinstance(x, (str, int, float))))
            else:
                out.append(f"{pad}- {v}")
        return chr(10).join(out)
    return f"{pad}{o}"


def clean_answer(text):
    """Never show raw tool JSON: tool results are dropped, a model JSON verdict becomes prose."""
    t = (text or "").strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    if fenced.startswith("{") and fenced.endswith("}"):
        try:
            o = json.loads(fenced)
        except ValueError:
            o = None
        if isinstance(o, dict):
            if "error" in o or "ok" in o or "in_force" in o:
                return ""
            return _prose(o)
    keep = []
    for line in t.splitlines():
        ln = line.strip()
        if ln.startswith("{") and ln.endswith("}"):
            try:
                if isinstance(json.loads(ln), dict):
                    continue
            except ValueError:
                pass
        keep.append(line)
    return chr(10).join(keep).strip()


def plain_call(c):
    """One tool call as a plain-Uzbek checklist row: (label, detail, ok)."""
    a = c.get("args") or {}
    name = c.get("name")
    ok = c.get("ok", True)
    res = str(c.get("result") or c.get("error") or "")
    if name == "search_law":
        return "Qonun qidirildi", str(a.get("query", ""))[:90], ok
    if name == "law_as_of":
        art = a.get("unit") or a.get("article") or ""
        d = a.get("date") or a.get("on_date") or ""
        if not ok or "not found" in res:
            return f"{art.replace('art:', '')}-modda {d} holatida topilmadi", "kuchsiz yoki mavjud emas", False
        return f"{art.replace('art:', '')}-modda {d} holatida o‘qildi", "", True
    if name == "verify_quote":
        return ("Iqtibos qonun matniga aynan mos" if ok else "Iqtibos qonun matniga mos kelmadi"), "", ok
    if name == "list_editions":
        return "Qonun tahrirlari ro‘yxati olindi", "", ok
    return str(name or "vosita"), "", ok


def ask_ctx(context, history, message, key):
    """Chat about one E-qaror decision: context = its metadata (+ text and Mezon flags when we have them)."""
    cfg = MODELS.get(key) or MODELS[DEFAULT]
    messages = [{"role": "system", "content": SYSTEM + "\n\n" + context}] + _clean_history(history) + [{"role": "user", "content": message}]
    return _finish(messages, cfg, *_post(messages, cfg))


def stream_ctx(context, history, message, key):
    """Real token streaming from the Mezon API (OpenAI SSE, stream=true). Yields, as they arrive:
    ("delta", text) final-answer tokens, ("tool_call", {name, args, ok, result_summary}), ("done", {calls, seconds}).
    Raises AnalyzerError if the server cannot be reached (the caller then shows no AI section at all)."""
    cfg = MODELS.get(key) or MODELS[DEFAULT]
    messages = [{"role": "system", "content": SYSTEM + "\n\n" + context}] + _clean_history(history) + [{"role": "user", "content": message}]
    base = settings.MEZON_AI.get("URL", "").rstrip("/")
    body = {"model": cfg["model"], "messages": messages, "temperature": 0.2, "stream": True}
    if cfg["use_tools"]:
        body["use_tools"] = True
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if settings.MEZON_AI.get("API_KEY"):
        headers["Authorization"] = "Bearer " + settings.MEZON_AI["API_KEY"]
    r = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(r, timeout=max(180, int(settings.MEZON_AI.get("TIMEOUT", 180))))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise AnalyzerError("Mezon-LM serveriga ulanib bo‘lmadi") from exc
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                o = json.loads(data)
            except ValueError:
                continue
            ev = o.get("mezon_event")
            if ev == "tool_call":
                yield "tool_call", o
            elif ev == "done":
                yield "done", o
            elif o.get("choices"):
                t = (o["choices"][0].get("delta") or {}).get("content")
                if t:
                    yield "delta", t
