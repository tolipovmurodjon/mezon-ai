import time
import os
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
import re
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services, stats
from .ai import get_analyzer
from .models import Analysis, Document, Region, RegulationRequest


def _table():
    # annotate() drops Meta.ordering (GROUP BY), so order explicitly
    return (RegulationRequest.objects.select_related("region")
            .annotate(doc_count=Count("documents")).order_by("-submitted_at"))


def dashboard(request):
    from . import eqaror
    hour = timezone.localtime().hour
    d = eqaror.dashboard_data()
    return render(request, "regulations/dashboard.html", {
        **d, "greeting": "Xayrli tong" if 5 <= hour < 12 else "Xayrli kun" if hour < 18 else "Xayrli kech", "nav": "dashboard"})


def request_list(request):
    from django.core.paginator import Paginator
    from . import eqaror
    g = request.GET
    f = {k: (g.get(k) or "").strip() for k in ("q", "hudud", "tuman", "tur", "dan", "gacha", "sort", "holat")}
    try:
        pg = max(1, int(g.get("page") or 1))
    except ValueError:
        pg = 1
    tabs, regs = eqaror.counts(f["q"], f["hudud"], f["tuman"], f["tur"], "", f["dan"], f["gacha"], f["holat"])
    total, rows = eqaror.query(f["q"], f["hudud"], f["tuman"], f["tur"], "", f["dan"], f["gacha"], f["sort"] or "new", pg, 25, f["holat"])
    page = Paginator(range(total), 25).get_page(pg)
    page.object_list = rows
    fmt = lambda n: f"{n:,}".replace(",", " ")  # noqa: E731
    for r in rows:
        r["region"] = eqaror.REGION_NAMES.get(r["r"], "")
    t_all = sum(tabs.values())
    tab_list = [("", "Barchasi", t_all), ("1", "Ehtimoliy buzilish", tabs.get(1, 0)), ("3", "Ekspert tekshiradi", tabs.get(3, 0)), ("2", "Muammo topilmadi", tabs.get(2, 0)), ("0", "Matnsiz", tabs.get(0, 0))]
    return render(request, "regulations/request_list.html", {
        "page": page, "f": f, "total": fmt(total),
        "tabs": [(k, n, fmt(c)) for k, n, c in tab_list],
        "regions": [(str(k), n, fmt(regs.get(k, 0))) for k, n in eqaror.REGION_NAMES.items()],
        "districts": eqaror.districts(int(f["hudud"])) if f["hudud"].isdigit() else [],
        "types": eqaror.TYPES, "nav": "requests", "upload_url": "/sorovlar/yuklash/"})


@xframe_options_sameorigin
def original_doc(request, lexid):
    from . import eqaror
    p = eqaror.original_pdf(lexid)
    if not p:
        raise Http404("Asl hujjat topilmadi")
    resp = FileResponse(open(p, "rb"), content_type="application/pdf")
    name = (request.GET.get("n") or lexid).replace("/", "-")
    resp["Content-Disposition"] = f'{"attachment" if request.GET.get("dl") else "inline"}; filename="{name}.pdf"'
    return resp


def eqaror_find(request):
    """Paste an E-qaror link (or code / decision number) -> the decision's detail page."""
    import re as _re
    from . import eqaror
    q = (request.GET.get("havola") or "").strip()
    m = _re.search(r"[0-9a-f]{32}", q.lower())
    if m and eqaror.get(m[0]):
        return redirect("eqaror_detail", code=m[0])
    if q:
        # experts type numbers loosely: any case, spaces, "-" instead of "/" before the year
        n = _re.sub(r"\s+", "", q).upper().replace("–", "-").replace("—", "-")
        n = _re.sub(r"-([A-Z]{1,2})-(\d{2})$", r"-\1/\2", n)
        r = (eqaror.con().execute("SELECT code FROM rows WHERE n=? LIMIT 1", (q,)).fetchone()
             or eqaror.con().execute("SELECT code FROM rows WHERE n=? LIMIT 1", (n,)).fetchone()
             or eqaror.con().execute("SELECT code FROM rows WHERE upper(n)=? LIMIT 1", (n,)).fetchone())
        if r:
            return redirect("eqaror_detail", code=r[0])
    messages.error(request, "Bu havola bizdagi E-qaror yozuvlari orasida topilmadi. Qaror raqamini yozib ko\u2018ring.")
    return redirect(request.META.get("HTTP_REFERER") or "requests")


def review(request, pk):
    req = get_object_or_404(RegulationRequest.objects.select_related("region"), pk=pk)
    services.mark_opened(req, request.user)
    analysis = req.analyses.filter(state=Analysis.State.DONE).prefetch_related("findings").first()
    last = req.analyses.first()
    failed = last if last and last.state == Analysis.State.FAILED and (
        not analysis or last.started_at > analysis.started_at) else None
    return render(request, "regulations/review.html", {
        "req": req,
        "documents": req.documents.all(),
        "analysis": analysis,
        "failed": failed,
        "autostart": analysis is None and failed is None and req.is_open,
        "chat": req.messages.all(),
        "decision": req.decision,
        "analyzer": get_analyzer(),
        "auto_prompt": services.AUTO_PROMPT,
        "nav": "requests",
    })


def _stream(events):
    def body():
        yield ": mezon\n\n"  # opens the stream right away
        for event in events:
            yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"
    resp = StreamingHttpResponse(body(), content_type="text/event-stream; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@require_POST
def analyze(request, pk):
    req = get_object_or_404(RegulationRequest, pk=pk)
    return _stream(services.run_analysis(req, request.user))


@require_POST
def chat(request, pk):
    req = get_object_or_404(RegulationRequest, pk=pk)
    message = (request.POST.get("message") or "").strip()[:4000]
    if not message:
        return HttpResponse(status=400)
    return _stream(services.run_chat(req, request.user, message, model=request.POST.get("model") or "mezon-lm"))


@require_POST
def decide(request, pk):
    req = get_object_or_404(RegulationRequest, pk=pk)
    outcome, comment = request.POST.get("outcome", ""), request.POST.get("comment", "")
    if outcome == "reject" and not comment.strip():
        messages.error(request, "Rad etish sababini yozing.")
    else:
        try:
            decision = services.decide(req, request.user, outcome, comment)
            messages.success(request, f"{req.number} · {decision.get_outcome_display()}")
        except ValueError as exc:
            messages.error(request, str(exc))
    return redirect("review", pk=pk)


def document_download(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.file:
        return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.file.name.rsplit("/", 1)[-1])
    if not doc.text:
        raise Http404
    resp = HttpResponse(doc.text, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{doc.request.number}-{doc.pk}.txt"'
    return resp


@require_POST
def upload(request):
    from . import uploads
    f = request.FILES.get("file")
    text = (request.POST.get("matn") or "").strip()
    try:
        if f:
            if f.size > uploads.MAX_BYTES:
                raise uploads.UploadError("Fayl 20 MB dan katta.")
            uid = uploads.check(f.name, data=f.read())
        elif text:
            uid = uploads.check(None, text=text)
        else:
            raise uploads.UploadError("Fayl tanlanmadi yoki matn bo\u2018sh.")
    except uploads.UploadError as exc:
        from urllib.parse import quote
        return redirect("/sorovlar/?xato=" + quote(str(exc)))
    except Exception:
        return redirect("/sorovlar/?xato=" + "Tekshirishda kutilmagan xato yuz berdi. Qayta urinib ko\u2018ring.")
    return redirect("upload_detail", uid=uid)


def _upload_ctx(rec):
    return ("Foydalanuvchi yuklagan qaror: raqami " + (rec["reg"] or "aniqlanmadi") + "; sana " + rec["date"] + "; organ " + (rec["organ"] or "aniqlanmadi")
            + ".\nQaror matni:\n" + rec["text"][:9000] + "\n"
            + ("Mezon qoidalari topgan belgilar: " + "; ".join(f["title"] for f in rec["flags"]) + "\n" if rec["flags"] else ""))


def upload_detail(request, uid):
    from . import eqaror, uploads
    from .ai import uz as _uz
    rec = uploads.get(uid)
    if not rec:
        raise Http404
    for _f in rec["flags"]:
        _f["quote_html"] = _uz.quote_html(_f.get("quote", ""))
    row = {"code": uid, "n": rec["reg"] or "raqam aniqlanmadi", "d": rec["date"], "t": rec["title"], "h": 0, "nm": 1 if _norm_for(rec["reg"]) == "Ha" else 0, "rel": 0, "s": "upload",
           "ty": "Yuklangan hujjat", "src": "Yuklangan fayl", "region": eqaror.REGION_NAMES.get(rec["region"], ""), "organ_full": rec["organ"] or rec["file"]}
    return render(request, "regulations/eqaror_detail.html", {
        "row": row, "nav": "requests", "slice_label": "Yuklangan fayl: " + rec["file"], "lex": {"text": rec["text"], "url": ""},
        "flags": rec["flags"], "checks": rec["checks"], "laws": rec["laws"], "basis_source": "yuklangan matn",
        "lexid": "", "chat_url": f"/tekshiruv/{uid}/suhbat/", "matched": rec.get("matched"),
        "info": _info(rec["reg"], rec["date"], rec["organ"], eqaror.REGION_NAMES.get(rec["region"]), _norm_for(rec["reg"]), rec["laws"], rec.get("words"), rec.get("pages")),
        "orig_url": f"/tekshiruv/{uid}/asl.pdf" if rec["pdf"] else "", "is_upload": True})


@xframe_options_sameorigin
def upload_pdf(request, uid):
    from . import uploads
    p = uploads.pdf_path(uid)
    if not p:
        raise Http404
    resp = FileResponse(open(p, "rb"), content_type="application/pdf")
    rec = uploads.get(uid) or {}
    resp["Content-Disposition"] = f'{"attachment" if request.GET.get("dl") else "inline"}; filename="{(rec.get("file") or uid).replace(chr(34), "")}"'
    return resp


@require_POST
def upload_chat(request, uid):
    from . import uploads
    rec = uploads.get(uid)
    if not rec:
        raise Http404
    message = (request.POST.get("message") or "").strip()[:4000]
    model = request.POST.get("model") or "mezon-lm"
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []
    return _chat_response(_upload_ctx(rec), message, model, history)


@require_POST
def chat_clear(request, pk):
    req = get_object_or_404(RegulationRequest, pk=pk)
    req.messages.all().delete()
    return HttpResponse(status=204)


def ai_chat(request):
    chips = ["Hokim normativ hujjatni farmoyish bilan chiqara oladimi?",
             "NHH 40-modda: biznesga yangi majburiyat qachon kuchga kiradi?",
             "Mahalliy davlat hokimiyati to‘g‘risidagi Qonun 25-modda hozir kuchdami?",
             "Qaror jamoatchilik muhokamasidan qancha kun o‘tishi kerak?"]
    return render(request, "regulations/ai_chat.html", {"nav": "aichat", "chips": chips})


@require_POST
def ai_chat_api(request):
    from .ai.mezon_api import MODELS, ask_free, plain_call
    message = (request.POST.get("message") or "").strip()[:4000]
    model = request.POST.get("model") or "mezon-lm"
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []

    def events():
        try:
            yield {"type": "step", "id": "model", "label": f"{MODELS.get(model, MODELS['mezon-lm'])['label']} javob tayyorlamoqda", "status": "run"}
            if model == "demo":
                yield {"type": "token", "text": "Demo rejimida erkin suhbat yo‘q: modelni tanlang yoki So‘rov sahifasidan foydalaning."}
                yield {"type": "result", "model": "Demo"}
                return
            _t0 = time.time()
            answer, calls, secs, cfg = ask_free(history, message, model)
            for i, c in enumerate(calls):
                label, detail, ok = plain_call(c)
                yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
            yield from _trace_events(calls)
            yield {"type": "step", "id": "model", "label": "Javob tayyor", "status": "done", "detail": f"{secs:.0f} soniya" if secs else ""}
            yield {"type": "token", "text": answer or "Model javob bera olmadi, qayta yuboring."}
            yield {"type": "result", "model": f"{cfg['label']} · {cfg['model']}", "badge": _badge(cfg, secs, calls, time.time() - _t0)}
            if full.strip() and nchars and _is_default_check(message):
                _save_answer(code, full, calls, cfg, secs or (time.time() - _t0))
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
    return _stream(events())


def eqaror_registry(request):
    from django.core.paginator import Paginator
    from . import eqaror
    g = request.GET
    f = {k: (g.get(k) or "").strip() for k in ("q", "hudud", "tuman", "tur", "norm", "dan", "gacha", "sort")}
    try:
        pg = max(1, int(g.get("page") or 1))
    except ValueError:
        pg = 1
    total, rows = eqaror.query(f["q"], f["hudud"], f["tuman"], f["tur"], f["norm"], f["dan"], f["gacha"], f["sort"] or "new", pg)
    page = Paginator(range(total), 25).get_page(pg)
    page.object_list = rows
    sl = eqaror.slice_counts()
    fmt = lambda n: f"{n:,}".replace(",", " ")  # noqa: E731
    for r in rows:
        r["region"] = eqaror.REGION_NAMES.get(r["r"], "")
    return render(request, "regulations/eqaror.html", {
        "page": page, "f": f, "types": eqaror.TYPES,
        "slices": [{"label": s["label"], "have": fmt(s["have"]), "api_total": fmt(s["api_total"])} for s in sl],
        "regions": [(str(k), n) for k, n in eqaror.REGION_NAMES.items()],
        "districts": eqaror.districts(int(f["hudud"])) if f["hudud"].isdigit() else [],
        "total": fmt(total), "all_rows": fmt(sum(s["have"] for s in sl)), "nav": "eqaror"})


def _eqaror_context(row):
    """Everything real we know about one E-qaror row, plus lex.uz text and Mezon flags when matched."""
    from . import eqaror
    from .ai import uz
    from . import uploads
    att = uploads.attached(row["code"])
    arec = uploads.get(att) if att else None
    if arec:
        from .ai import uz as _uz
        for _f in arec["flags"]:
            _f["quote_html"] = _uz.quote_html(_f.get("quote", ""))
        return {"mismatch": ((arec["reg"], row["n"]) if arec.get("reg") and arec["reg"] != row["n"] else None),
                "lex": {"text": arec["text"], "url": ""}, "flags": arec["flags"], "checks": arec["checks"], "laws": arec["laws"],
                "basis_source": "qo\u2018shilgan matn", "orig_url": f"/tekshiruv/{att}/asl.pdf" if arec["pdf"] else "", "attached": True}
    lex = eqaror.lex_match(row["n"])
    ctx = {"lex": lex, "flags": [], "checks": None}
    basis_text = lex["text"] if lex else ("" if row["h"] else row["t"])
    ctx["basis_source"] = "lex.uz matni" if lex else "E-qaror sarlavhasi"
    try:
        ctx["laws"] = eqaror.laws(row["code"], basis_text, row["d"]) if basis_text else []
    except Exception:
        ctx["laws"] = []
    if lex:
        rep = eqaror.audit(row["n"], lex["text"], lex["title"])
        ctx["checks"] = {"total": len(rep["checks_run"]), "flags": len(rep["flags"])}
        for fl in rep["flags"]:
            t, e = uz.translate(fl)
            c = fl["citations"][0] if fl["citations"] else {}
            ctx["flags"].append({"title": t, "explanation": e, "law_ref": uz.law_ref(c), "law_text": c.get("quote", ""),
                                 "quote": (fl["evidence"][0]["quote"] if fl["evidence"] else "").strip("… "), "severity": fl["severity"],
                                 "quote_html": uz.quote_html(fl["evidence"][0]["quote"] if fl["evidence"] else ""), "status": fl["status"]})
    return ctx


def eqaror_detail(request, code):
    from . import eqaror
    row = eqaror.get(code)
    if not row:
        raise Http404
    kengash = "-K/" in row["n"]
    row["region"] = eqaror.REGION_NAMES.get(row["r"], "")
    row["organ_full"] = eqaror.organ_for(row["r"], row["dist"], kengash) or row["o"]
    ctx = _eqaror_context(row)
    import re as _re
    lexid = _re.sub(r"\D", "", (ctx["lex"] or {}).get("url", "")) if ctx["lex"] else ""
    ctx["lexid"] = lexid
    ctx.setdefault("orig_url", "")
    kut = request.GET.get("kutish")
    if kut:
        from . import uploads as _up
        prec = _up.get(kut)
        if prec:
            ctx["pending"] = {"uid": kut, "reg": prec["reg"], "row": row["n"]}
    txt = (ctx["lex"] or {}).get("text") or ""
    ctx["info"] = _info(row["n"], row["d"], row["organ_full"], row["region"], "Ha" if row["nm"] else "Yo\u2018q", ctx.get("laws"),
                        len(txt.split()) if txt else None, (txt.count("\f") or None) if txt else None)
    return render(request, "regulations/eqaror_detail.html", {
        "row": row, "nav": "eqaror", "slice_label": eqaror.SLICE_LABELS.get(row["s"], row["s"]), **ctx})


@require_POST
def eqaror_chat(request, code):
    from . import eqaror
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    row = eqaror.get(code)
    if not row:
        raise Http404
    message = (request.POST.get("message") or "").strip()[:4000]
    model = request.POST.get("model") or "mezon-lm"
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []
    c = _eqaror_context(row)
    title = "(yashirilgan hujjat: shaxsga doir ma\u2019lumot)" if row["h"] else row["t"]
    ctx = (f"E-qaror qarori: raqami {row['n']}; sana {row['d']}; organ {row['o']}; turi {row['ty']}; "
           f"normativ: {'ha' if row['nm'] else 'yo\u2018q'}; sarlavha: {title}.\n")
    if c["lex"]:
        ctx += "Qaror matni lex.uz dan olingan:\n" + c["lex"]["text"][:9000] + "\n"
        if c["flags"]:
            ctx += "Mezon qoidalari topgan belgilar: " + "; ".join(f["title"] for f in c["flags"]) + "\n"
    else:
        ctx += ("Qaror matni bizda yo\u2018q: faqat E-qaror ma\u2019lumotlari (sarlavha, organ, sana, raqam, tur) mavjud. "
                "Shu ma\u2019lumotlardan tekshirish mumkin bo\u2018lganini tekshiring (qaror yoki farmoyish shakli, normativ holati, "
                "sarlavhadan vakolat) va matn yo\u2018qligini ochiq ayting.\n")

    return _chat_response(ctx, message, model, history)


def _chat_response(ctx, message, model, history):
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    def events():
        try:
            yield {"type": "step", "id": "model", "label": f"{MODELS.get(model, MODELS['mezon-lm'])['label']} javob tayyorlamoqda", "status": "run"}
            if model == "demo":
                yield {"type": "token", "text": "Demo rejimi bu sahifada yo\u2018q: modelni tanlang."}
                yield {"type": "result", "model": "Demo"}
                return
            _t0 = time.time()
            answer, calls, secs, cfg = ask_ctx(ctx, history, message, model)
            for i, cl in enumerate(calls):
                label, detail, ok = plain_call(cl)
                yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
            yield from _trace_events(calls)
            yield {"type": "step", "id": "model", "label": "Javob tayyor", "status": "done", "detail": f"{secs:.0f} soniya" if secs else ""}
            yield {"type": "token", "text": answer or "Model javob bera olmadi, qayta yuboring."}
            yield {"type": "result", "model": f"{cfg['label']} \u00b7 {cfg['model']}", "badge": _badge(cfg, secs, calls, time.time() - _t0)}
        except Exception as exc:
            yield {"type": "error", "message": str(exc), "badge": {"text": "Model javob bera olmadi \u00b7 GPU", "tools": ""}}
    return _stream(events())


@require_POST
def eqaror_attach(request, code):
    """Attach a PDF / DOCX / pasted text to THIS E-qaror decision and run the real checks on it."""
    from urllib.parse import quote
    from . import eqaror, uploads
    row = eqaror.get(code)
    if not row:
        raise Http404
    f = request.FILES.get("file")
    text = (request.POST.get("matn") or "").strip()
    try:
        if f:
            if f.size > uploads.MAX_BYTES:
                raise uploads.UploadError("Fayl 20 MB dan katta.")
            uid = uploads.check(f.name, data=f.read())
        elif text:
            uid = uploads.check(None, text=text)
        else:
            raise uploads.UploadError("Fayl tanlanmadi yoki matn bo\u2018sh.")
    except uploads.UploadError as exc:
        return redirect(f"/eqaror/{code}/?xato=" + quote(str(exc)))
    rec = uploads.get(uid) or {}
    if rec.get("reg") and rec["reg"] != row["n"]:
        return redirect(f"/eqaror/{code}/?kutish={uid}")
    uploads.attach(code, uid)
    return redirect("eqaror_detail", code=code)


@require_POST
def eqaror_confirm(request, code, uid):
    from . import eqaror, uploads
    if not eqaror.get(code) or not uploads.get(uid):
        raise Http404
    uploads.attach(code, uid)
    return redirect("eqaror_detail", code=code)


def _info(reg, date, organ, region, norm, laws, words, pages, tur=None):
    """The 'Aniqlangan ma\u2019lumot' box: every field parsed from the text; None -> 'aniqlanmadi'."""
    typ = tur
    if not typ and reg:
        typ = "Kengash qarori" if "-K/" in reg else "Hokim farmoyishi" if re.search(r"-F/", reg) else "Hokim qarori" if re.search(r"-Q/", reg) else None
    chips = [f"{c['act_title']} \u00b7 {c['article']}-modda" for c in (laws or [])]
    return {"reg": reg or None, "date": date or None, "organ": organ or None, "region": region or None, "typ": typ,
            "norm": norm, "chips": chips, "words": words or None, "pages": pages or None}


def _norm_for(reg):
    from . import eqaror
    if not reg:
        return None
    r = eqaror.con().execute("SELECT nm FROM rows WHERE n=? LIMIT 1", (reg,)).fetchone()
    return None if r is None else ("Ha" if r[0] else "Yo\u2018q")


_ACT_NAMES = {"lsp": "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun", "nla": "NHH Qonuni (O‘RQ-682)",
              "taxcode": "Soliq kodeksi", "landcode": "Yer kodeksi", "budgetcode": "Byudjet kodeksi"}


@require_POST
def eqaror_agent(request, code):
    """Live agent run: every step is a real computation; each event is sent the moment it finishes."""
    import subprocess
    from . import eqaror, uploads
    from .ai import uz
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    row = eqaror.get(code)
    if not row:
        raise Http404
    model = request.POST.get("model") or "mezon-lm"
    message = (request.POST.get("message") or "Ushbu qarorni tekshiring").strip()[:2000]
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []

    def events():
        try:
            yield {"type": "step", "id": "read", "label": "Qaror o\u2018qilmoqda\u2026", "status": "run"}
            att = uploads.attached(code)
            arec = uploads.get(att) if att else None
            lex = None if arec else eqaror.lex_match(row["n"])
            text = arec["text"] if arec else (lex["text"] if lex else "")
            has_text = bool(text)
            basis_text = text or ("" if row["h"] else row["t"])
            pages = text.count("\f") if text else 0
            if has_text:
                yield {"type": "step", "id": "read", "label": f"Qaror o\u2018qildi ({len(text.split())} so\u2018z" + (f", {pages} bet" if pages else "") + ")", "status": "done"}
            else:
                yield {"type": "step", "id": "read", "label": "Qaror matni yo\u2018q \u2014 faqat E-qaror ma\u2019lumoti (sarlavha, organ, sana, raqam)", "status": "warn"}
            payload = json.dumps({"text": basis_text, "date": row["d"], "title": row["t"] if not row["h"] else "", "check_rules": has_text}).encode("utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.Popen([os.environ.get("MEZON_PY", r"D:\10_projects\mezon\.venv\Scripts\python.exe"), "-X", "utf8", str(eqaror.ROOT / "tools" / "agent_run.py")],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"), env=env)
            proc.stdin.write(payload)
            proc.stdin.close()
            yield {"type": "step", "id": "basis", "label": "Huquqiy asos qidirilmoqda\u2026", "status": "run"}
            laws, flags, report = [], [], None
            for line in proc.stdout:
                ev = json.loads(line.decode("utf-8"))
                k = ev["ev"]
                if k == "basis":
                    cites = ev["cites"]
                    if cites:
                        names = ", ".join(f"{_ACT_NAMES.get(c['key'], c['act'])} {c['article']}-modda" for c in cites)
                        yield {"type": "step", "id": "basis", "label": "Asos topildi: " + names, "status": "done"}
                    else:
                        yield {"type": "step", "id": "basis", "label": "Qarorning huquqiy asosidan qonun moddalari aniqlanmadi", "status": "warn"}
                elif k == "law_start":
                    d = row["d"]
                    yield {"type": "step", "id": f"law-{ev['article']}", "label": f"{ev['article']}-modda {d} holatida tekshirilmoqda\u2026", "status": "run"}
                elif k == "law":
                    c = ev["card"]
                    c["act_title"] = _ACT_NAMES.get(c["act_key"], c["act_title"])
                    laws.append(c)
                    if c["in_force"]:
                        lab, st = f"{c['article']}-modda {row['d']} holatida kuchda", "done"
                    else:
                        lab, st = (f"{c['article']}-modda {row['d']} tahrirda yo\u2018q" + (f", {c['removed_in']} dan kuchsiz" if c.get("removed_in") else "")), "warn"
                    yield {"type": "step", "id": f"law-{c['article']}", "label": lab, "status": st}
                    yield {"type": "law_card", "card": c}
                elif k == "rules_start":
                    yield {"type": "step", "id": "rules", "label": "Mezon qoidalari ishlamoqda\u2026", "status": "run"}
                elif k == "rules":
                    report = ev["report"]
                    for fl in report["flags"]:
                        t, e = uz.translate(fl)
                        c0 = fl["citations"][0] if fl["citations"] else {}
                        q = fl["evidence"][0]["quote"] if fl["evidence"] else ""
                        flags.append({"title": t, "explanation": e, "law_ref": uz.law_ref(c0), "quote_html": uz.quote_html(q), "quote": uz.clean_quote(q), "status": fl["status"],
                                      "severity": fl["severity"]})
                    n = len(report["checks_run"])
                    yield {"type": "step", "id": "rules", "label": f"Mezon qoidalari: {n} ta tekshiruv, {len(flags)} ta belgi" + (f" (bazadagi {report['matched']['reg']} bilan mos)" if report.get("matched") else ""),
                           "status": "warn" if flags else "done"}
                    yield {"type": "flags", "flags": flags}
            proc.wait(timeout=5)
            # ---- the AI answers with everything the agent just found
            title = "(yashirilgan hujjat)" if row["h"] else row["t"]
            ctx = (f"E-qaror qarori: raqami {row['n']}; sana {row['d']}; organ {row['o']}; turi {row['ty']}; sarlavha: {title}.\n")
            if has_text:
                ctx += "Qaror matni:\n" + text[:9000] + "\n"
            else:
                ctx += "Qaror matni bizda yo‘q: faqat E-qaror ma’lumotlari; matn yo‘qligini ochiq ayting.\n"
            ctx += "\nMEZON TEKSHIRUV NATIJALARI (haqiqiy, hisoblangan):\n"
            for c in laws:
                ctx += (f"- Keltirilgan norma: {c['act_title']}, {c['article']}-modda; {row['d']} holatida " +
                        ("KUCHDA" if c["in_force"] else "KUCHDA EMAS" + (f" ({c['removed_in']} dan kuchsiz)" if c.get("removed_in") else "")) + ".\n")
            hi = [f for f in flags if f.get("status") != "unclear_needs_expert"]
            un = [f for f in flags if f.get("status") == "unclear_needs_expert"]
            if report:
                vmap = {"positive": "ijobiy", "positive_with_fixable_defects": "tuzatiladigan kamchiliklar bilan ijobiy", "negative": "salbiy"}
                vt = vmap.get(report["verdict"], report["verdict"])
                if not hi and un:
                    vt = "ijobiy (faqat ekspert tekshirishi kerak bo‘lgan noaniq belgilar bor; ular kamchilik emas)"
                ctx += f"- Qoidalar bo‘yicha xulosa turi: {vt}.\n"
            for i, f in enumerate(hi, 1):
                ctx += f"- ANIQ belgi {i}: {f['title']}. Asos: {f['law_ref']}. Sabab: {f['explanation']}" + (f" Qarordan iqtibos: “{f['quote']}”" if f.get("quote") else "") + "\n"
            for i, f in enumerate(un, 1):
                ctx += f"- NOANIQ belgi {i} (ekspert tekshirishi kerak, kamchilik deb atamang): {f['title']}. Izoh: {f['explanation']}\n"
            if not flags:
                ctx += "- Qoidalar kamchilik topmadi.\n"
            ctx += "Eslatma: NOANIQ belgilarni kamchilik, buzilish yoki ‘tuzatiladigan kamchilik’ deb atamang; ularni ‘ekspert tekshirishi kerak’ deb yozing.\n"
            ask_msg = message
            if message.strip().lower().startswith("ushbu qarorni tekshiring"):
                ask_msg = ("Adliya ekspertizasi xulosasini 3333-son buyruq shaklida yozing: 1) Xulosa turi: ijobiy / tuzatiladigan kamchiliklar bilan ijobiy / salbiy; "
                           "2) Har bir kamchilik: qaysi modda, nima uchun, qarordan iqtibos; 3) Tavsiya: nima qilish kerak (masalan, amaldagi moddani keltirish). "
                           "Faqat berilgan ma’lumot va qonun vositalariga tayaning; ‘noqonuniy’ demang — ‘ehtimoliy buzilish, ekspert ko‘rib chiqadi’ deng. "
                           "Xulosa yozishdan oldin law_as_of vositasi bilan har bir keltirilgan moddani, verify_quote bilan iqtiboslarni tekshiring. ENG MUHIMI: ekspert tekshirishi kerak deb belgilangan (NOANIQ) belgilarni kamchilik deb atamang. Oddiy matn, JSON emas.")
            cfg = MODELS.get(model, MODELS["mezon-lm"])
            import queue
            import threading
            from .ai.mezon_api import stream_ctx
            box = queue.Queue()
            _t0 = time.time()

            def work():
                try:
                    for item in stream_ctx(ctx, history, ask_msg, "mezon-lm" if model == "demo" else model):
                        box.put(item)
                    box.put(("end", None))
                except Exception as e:  # noqa: BLE001  (unreachable model: the page simply shows no AI section)
                    box.put(("fail", e))
            threading.Thread(target=work, daemon=True).start()
            started, calls, secs, nchars = False, [], None, 0
            pend, full = "", ""
            while True:
                try:
                    kind, val = box.get(timeout=10)
                except queue.Empty:
                    yield {"type": "ping"}  # heartbeat: keeps the stream alive through gunicorn / nginx / the tunnel
                    continue
                if kind == "fail":
                    import logging
                    logging.getLogger("regulations").warning("mezon model unreachable: %s", val)
                    if started:
                        yield {"type": "step", "id": "ai", "label": "Model javobi uzildi", "status": "warn"}
                    else:
                        yield from _replay_saved(code, message)
                    return  # nothing is shown for the AI when it cannot be reached; rule results stay
                if kind == "end":
                    break
                if not started:
                    started = True
                    yield {"type": "step", "id": "ai", "label": f"{cfg['label']} xulosa yozmoqda…", "status": "run"}
                if kind == "tool_call":
                    cl = {"name": val.get("name"), "args": val.get("args") or {}, "ok": val.get("ok", True), "result_summary": val.get("result_summary", "")}
                    calls.append(cl)
                    label, detail, ok = plain_call(cl)
                    i = len(calls) - 1
                    yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
                    yield {"type": "trace", "name": cl["name"], "args": cl["args"], "result": val.get("result_summary", "")}
                elif kind == "delta":
                    nchars += len(val)
                    full += val
                    pend += val
                    for w in _words(pend):
                        yield {"type": "token", "text": w}
                        time.sleep(0.03)
                    pend = pend[sum(len(w) for w in _words(pend)):]
                elif kind == "done":
                    secs = val.get("seconds")
            if not started:
                yield from _replay_saved(code, message)
                return
            if pend:
                yield {"type": "token", "text": pend}
            yield {"type": "step", "id": "ai", "label": "Xulosa tayyor", "status": "done", "detail": f"{secs:.0f} soniya" if secs else ""}
            if not nchars:
                yield {"type": "token", "text": "Model javob bera olmadi, qayta yuboring."}
            yield {"type": "result", "model": f"{cfg['label']} · {cfg['model']}", "badge": _badge(cfg, secs, calls, time.time() - _t0)}
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
    return _stream(events())


def eqaror_registry(request):
    from django.core.paginator import Paginator
    from . import eqaror
    g = request.GET
    f = {k: (g.get(k) or "").strip() for k in ("q", "hudud", "tuman", "tur", "norm", "dan", "gacha", "sort")}
    try:
        pg = max(1, int(g.get("page") or 1))
    except ValueError:
        pg = 1
    total, rows = eqaror.query(f["q"], f["hudud"], f["tuman"], f["tur"], f["norm"], f["dan"], f["gacha"], f["sort"] or "new", pg)
    page = Paginator(range(total), 25).get_page(pg)
    page.object_list = rows
    sl = eqaror.slice_counts()
    fmt = lambda n: f"{n:,}".replace(",", " ")  # noqa: E731
    for r in rows:
        r["region"] = eqaror.REGION_NAMES.get(r["r"], "")
    return render(request, "regulations/eqaror.html", {
        "page": page, "f": f, "types": eqaror.TYPES,
        "slices": [{"label": s["label"], "have": fmt(s["have"]), "api_total": fmt(s["api_total"])} for s in sl],
        "regions": [(str(k), n) for k, n in eqaror.REGION_NAMES.items()],
        "districts": eqaror.districts(int(f["hudud"])) if f["hudud"].isdigit() else [],
        "total": fmt(total), "all_rows": fmt(sum(s["have"] for s in sl)), "nav": "eqaror"})


def _eqaror_context(row):
    """Everything real we know about one E-qaror row, plus lex.uz text and Mezon flags when matched."""
    from . import eqaror
    from .ai import uz
    from . import uploads
    att = uploads.attached(row["code"])
    arec = uploads.get(att) if att else None
    if arec:
        from .ai import uz as _uz
        for _f in arec["flags"]:
            _f["quote_html"] = _uz.quote_html(_f.get("quote", ""))
        return {"mismatch": ((arec["reg"], row["n"]) if arec.get("reg") and arec["reg"] != row["n"] else None),
                "lex": {"text": arec["text"], "url": ""}, "flags": arec["flags"], "checks": arec["checks"], "laws": arec["laws"],
                "basis_source": "qo\u2018shilgan matn", "orig_url": f"/tekshiruv/{att}/asl.pdf" if arec["pdf"] else "", "attached": True}
    lex = eqaror.lex_match(row["n"])
    ctx = {"lex": lex, "flags": [], "checks": None}
    basis_text = lex["text"] if lex else ("" if row["h"] else row["t"])
    ctx["basis_source"] = "lex.uz matni" if lex else "E-qaror sarlavhasi"
    try:
        ctx["laws"] = eqaror.laws(row["code"], basis_text, row["d"]) if basis_text else []
    except Exception:
        ctx["laws"] = []
    if lex:
        rep = eqaror.audit(row["n"], lex["text"], lex["title"])
        ctx["checks"] = {"total": len(rep["checks_run"]), "flags": len(rep["flags"])}
        for fl in rep["flags"]:
            t, e = uz.translate(fl)
            c = fl["citations"][0] if fl["citations"] else {}
            ctx["flags"].append({"title": t, "explanation": e, "law_ref": uz.law_ref(c), "law_text": c.get("quote", ""),
                                 "quote": (fl["evidence"][0]["quote"] if fl["evidence"] else "").strip("… "), "severity": fl["severity"],
                                 "quote_html": uz.quote_html(fl["evidence"][0]["quote"] if fl["evidence"] else ""), "status": fl["status"]})
    return ctx


def eqaror_detail(request, code):
    from . import eqaror
    row = eqaror.get(code)
    if not row:
        raise Http404
    kengash = "-K/" in row["n"]
    row["region"] = eqaror.REGION_NAMES.get(row["r"], "")
    row["organ_full"] = eqaror.organ_for(row["r"], row["dist"], kengash) or row["o"]
    ctx = _eqaror_context(row)
    import re as _re
    lexid = _re.sub(r"\D", "", (ctx["lex"] or {}).get("url", "")) if ctx["lex"] else ""
    ctx["lexid"] = lexid
    ctx.setdefault("orig_url", "")
    kut = request.GET.get("kutish")
    if kut:
        from . import uploads as _up
        prec = _up.get(kut)
        if prec:
            ctx["pending"] = {"uid": kut, "reg": prec["reg"], "row": row["n"]}
    txt = (ctx["lex"] or {}).get("text") or ""
    ctx["info"] = _info(row["n"], row["d"], row["organ_full"], row["region"], "Ha" if row["nm"] else "Yo\u2018q", ctx.get("laws"),
                        len(txt.split()) if txt else None, (txt.count("\f") or None) if txt else None)
    return render(request, "regulations/eqaror_detail.html", {
        "row": row, "nav": "eqaror", "slice_label": eqaror.SLICE_LABELS.get(row["s"], row["s"]), **ctx})


@require_POST
def eqaror_chat(request, code):
    from . import eqaror
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    row = eqaror.get(code)
    if not row:
        raise Http404
    message = (request.POST.get("message") or "").strip()[:4000]
    model = request.POST.get("model") or "mezon-lm"
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []
    c = _eqaror_context(row)
    title = "(yashirilgan hujjat: shaxsga doir ma\u2019lumot)" if row["h"] else row["t"]
    ctx = (f"E-qaror qarori: raqami {row['n']}; sana {row['d']}; organ {row['o']}; turi {row['ty']}; "
           f"normativ: {'ha' if row['nm'] else 'yo\u2018q'}; sarlavha: {title}.\n")
    if c["lex"]:
        ctx += "Qaror matni lex.uz dan olingan:\n" + c["lex"]["text"][:9000] + "\n"
        if c["flags"]:
            ctx += "Mezon qoidalari topgan belgilar: " + "; ".join(f["title"] for f in c["flags"]) + "\n"
    else:
        ctx += ("Qaror matni bizda yo\u2018q: faqat E-qaror ma\u2019lumotlari (sarlavha, organ, sana, raqam, tur) mavjud. "
                "Shu ma\u2019lumotlardan tekshirish mumkin bo\u2018lganini tekshiring (qaror yoki farmoyish shakli, normativ holati, "
                "sarlavhadan vakolat) va matn yo\u2018qligini ochiq ayting.\n")

    return _chat_response(ctx, message, model, history)


def _chat_response(ctx, message, model, history):
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    def events():
        try:
            yield {"type": "step", "id": "model", "label": f"{MODELS.get(model, MODELS['mezon-lm'])['label']} javob tayyorlamoqda", "status": "run"}
            if model == "demo":
                yield {"type": "token", "text": "Demo rejimi bu sahifada yo\u2018q: modelni tanlang."}
                yield {"type": "result", "model": "Demo"}
                return
            _t0 = time.time()
            answer, calls, secs, cfg = ask_ctx(ctx, history, message, model)
            for i, cl in enumerate(calls):
                label, detail, ok = plain_call(cl)
                yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
            yield from _trace_events(calls)
            yield {"type": "step", "id": "model", "label": "Javob tayyor", "status": "done", "detail": f"{secs:.0f} soniya" if secs else ""}
            yield {"type": "token", "text": answer or "Model javob bera olmadi, qayta yuboring."}
            yield {"type": "result", "model": f"{cfg['label']} \u00b7 {cfg['model']}", "badge": _badge(cfg, secs, calls, time.time() - _t0)}
        except Exception as exc:
            yield {"type": "error", "message": str(exc), "badge": {"text": "Model javob bera olmadi \u00b7 GPU", "tools": ""}}
    return _stream(events())


@require_POST
def eqaror_attach(request, code):
    """Attach a PDF / DOCX / pasted text to THIS E-qaror decision and run the real checks on it."""
    from urllib.parse import quote
    from . import eqaror, uploads
    row = eqaror.get(code)
    if not row:
        raise Http404
    f = request.FILES.get("file")
    text = (request.POST.get("matn") or "").strip()
    try:
        if f:
            if f.size > uploads.MAX_BYTES:
                raise uploads.UploadError("Fayl 20 MB dan katta.")
            uid = uploads.check(f.name, data=f.read())
        elif text:
            uid = uploads.check(None, text=text)
        else:
            raise uploads.UploadError("Fayl tanlanmadi yoki matn bo\u2018sh.")
    except uploads.UploadError as exc:
        return redirect(f"/eqaror/{code}/?xato=" + quote(str(exc)))
    rec = uploads.get(uid) or {}
    if rec.get("reg") and rec["reg"] != row["n"]:
        return redirect(f"/eqaror/{code}/?kutish={uid}")
    uploads.attach(code, uid)
    return redirect("eqaror_detail", code=code)


@require_POST
def eqaror_confirm(request, code, uid):
    from . import eqaror, uploads
    if not eqaror.get(code) or not uploads.get(uid):
        raise Http404
    uploads.attach(code, uid)
    return redirect("eqaror_detail", code=code)


def _info(reg, date, organ, region, norm, laws, words, pages, tur=None):
    """The 'Aniqlangan ma\u2019lumot' box: every field parsed from the text; None -> 'aniqlanmadi'."""
    typ = tur
    if not typ and reg:
        typ = "Kengash qarori" if "-K/" in reg else "Hokim farmoyishi" if re.search(r"-F/", reg) else "Hokim qarori" if re.search(r"-Q/", reg) else None
    chips = [f"{c['act_title']} \u00b7 {c['article']}-modda" for c in (laws or [])]
    return {"reg": reg or None, "date": date or None, "organ": organ or None, "region": region or None, "typ": typ,
            "norm": norm, "chips": chips, "words": words or None, "pages": pages or None}


def _norm_for(reg):
    from . import eqaror
    if not reg:
        return None
    r = eqaror.con().execute("SELECT nm FROM rows WHERE n=? LIMIT 1", (reg,)).fetchone()
    return None if r is None else ("Ha" if r[0] else "Yo\u2018q")


_ACT_NAMES = {"lsp": "“Mahalliy davlat hokimiyati to‘g‘risida”gi Qonun", "nla": "NHH Qonuni (O‘RQ-682)",
              "taxcode": "Soliq kodeksi", "landcode": "Yer kodeksi", "budgetcode": "Byudjet kodeksi"}


@require_POST
def eqaror_agent(request, code):
    """Live agent run: every step is a real computation; each event is sent the moment it finishes."""
    import subprocess
    from . import eqaror, uploads
    from .ai import uz
    from .ai.mezon_api import MODELS, ask_ctx, plain_call
    row = eqaror.get(code)
    if not row:
        raise Http404
    model = request.POST.get("model") or "mezon-lm"
    message = (request.POST.get("message") or "Ushbu qarorni tekshiring").strip()[:2000]
    try:
        history = json.loads(request.POST.get("history") or "[]")
    except ValueError:
        history = []

    def events():
        try:
            yield {"type": "step", "id": "read", "label": "Qaror o\u2018qilmoqda\u2026", "status": "run"}
            att = uploads.attached(code)
            arec = uploads.get(att) if att else None
            lex = None if arec else eqaror.lex_match(row["n"])
            text = arec["text"] if arec else (lex["text"] if lex else "")
            has_text = bool(text)
            basis_text = text or ("" if row["h"] else row["t"])
            pages = text.count("\f") if text else 0
            if has_text:
                yield {"type": "step", "id": "read", "label": f"Qaror o\u2018qildi ({len(text.split())} so\u2018z" + (f", {pages} bet" if pages else "") + ")", "status": "done"}
            else:
                yield {"type": "step", "id": "read", "label": "Qaror matni yo\u2018q \u2014 faqat E-qaror ma\u2019lumoti (sarlavha, organ, sana, raqam)", "status": "warn"}
            payload = json.dumps({"text": basis_text, "date": row["d"], "title": row["t"] if not row["h"] else "", "check_rules": has_text}).encode("utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.Popen([os.environ.get("MEZON_PY", r"D:\10_projects\mezon\.venv\Scripts\python.exe"), "-X", "utf8", str(eqaror.ROOT / "tools" / "agent_run.py")],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"), env=env)
            proc.stdin.write(payload)
            proc.stdin.close()
            yield {"type": "step", "id": "basis", "label": "Huquqiy asos qidirilmoqda\u2026", "status": "run"}
            laws, flags, report = [], [], None
            for line in proc.stdout:
                ev = json.loads(line.decode("utf-8"))
                k = ev["ev"]
                if k == "basis":
                    cites = ev["cites"]
                    if cites:
                        names = ", ".join(f"{_ACT_NAMES.get(c['key'], c['act'])} {c['article']}-modda" for c in cites)
                        yield {"type": "step", "id": "basis", "label": "Asos topildi: " + names, "status": "done"}
                    else:
                        yield {"type": "step", "id": "basis", "label": "Qarorning huquqiy asosidan qonun moddalari aniqlanmadi", "status": "warn"}
                elif k == "law_start":
                    d = row["d"]
                    yield {"type": "step", "id": f"law-{ev['article']}", "label": f"{ev['article']}-modda {d} holatida tekshirilmoqda\u2026", "status": "run"}
                elif k == "law":
                    c = ev["card"]
                    c["act_title"] = _ACT_NAMES.get(c["act_key"], c["act_title"])
                    laws.append(c)
                    if c["in_force"]:
                        lab, st = f"{c['article']}-modda {row['d']} holatida kuchda", "done"
                    else:
                        lab, st = (f"{c['article']}-modda {row['d']} tahrirda yo\u2018q" + (f", {c['removed_in']} dan kuchsiz" if c.get("removed_in") else "")), "warn"
                    yield {"type": "step", "id": f"law-{c['article']}", "label": lab, "status": st}
                    yield {"type": "law_card", "card": c}
                elif k == "rules_start":
                    yield {"type": "step", "id": "rules", "label": "Mezon qoidalari ishlamoqda\u2026", "status": "run"}
                elif k == "rules":
                    report = ev["report"]
                    for fl in report["flags"]:
                        t, e = uz.translate(fl)
                        c0 = fl["citations"][0] if fl["citations"] else {}
                        q = fl["evidence"][0]["quote"] if fl["evidence"] else ""
                        flags.append({"title": t, "explanation": e, "law_ref": uz.law_ref(c0), "quote_html": uz.quote_html(q), "quote": uz.clean_quote(q), "status": fl["status"],
                                      "severity": fl["severity"]})
                    n = len(report["checks_run"])
                    yield {"type": "step", "id": "rules", "label": f"Mezon qoidalari: {n} ta tekshiruv, {len(flags)} ta belgi" + (f" (bazadagi {report['matched']['reg']} bilan mos)" if report.get("matched") else ""),
                           "status": "warn" if flags else "done"}
                    yield {"type": "flags", "flags": flags}
            proc.wait(timeout=5)
            # ---- the AI answers with everything the agent just found
            title = "(yashirilgan hujjat)" if row["h"] else row["t"]
            ctx = (f"E-qaror qarori: raqami {row['n']}; sana {row['d']}; organ {row['o']}; turi {row['ty']}; sarlavha: {title}.\n")
            if has_text:
                ctx += "Qaror matni:\n" + text[:9000] + "\n"
            else:
                ctx += "Qaror matni bizda yo‘q: faqat E-qaror ma’lumotlari; matn yo‘qligini ochiq ayting.\n"
            ctx += "\nMEZON TEKSHIRUV NATIJALARI (haqiqiy, hisoblangan):\n"
            for c in laws:
                ctx += (f"- Keltirilgan norma: {c['act_title']}, {c['article']}-modda; {row['d']} holatida " +
                        ("KUCHDA" if c["in_force"] else "KUCHDA EMAS" + (f" ({c['removed_in']} dan kuchsiz)" if c.get("removed_in") else "")) + ".\n")
            hi = [f for f in flags if f.get("status") != "unclear_needs_expert"]
            un = [f for f in flags if f.get("status") == "unclear_needs_expert"]
            if report:
                vmap = {"positive": "ijobiy", "positive_with_fixable_defects": "tuzatiladigan kamchiliklar bilan ijobiy", "negative": "salbiy"}
                vt = vmap.get(report["verdict"], report["verdict"])
                if not hi and un:
                    vt = "ijobiy (faqat ekspert tekshirishi kerak bo‘lgan noaniq belgilar bor; ular kamchilik emas)"
                ctx += f"- Qoidalar bo‘yicha xulosa turi: {vt}.\n"
            for i, f in enumerate(hi, 1):
                ctx += f"- ANIQ belgi {i}: {f['title']}. Asos: {f['law_ref']}. Sabab: {f['explanation']}" + (f" Qarordan iqtibos: “{f['quote']}”" if f.get("quote") else "") + "\n"
            for i, f in enumerate(un, 1):
                ctx += f"- NOANIQ belgi {i} (ekspert tekshirishi kerak, kamchilik deb atamang): {f['title']}. Izoh: {f['explanation']}\n"
            if not flags:
                ctx += "- Qoidalar kamchilik topmadi.\n"
            ctx += "Eslatma: NOANIQ belgilarni kamchilik, buzilish yoki ‘tuzatiladigan kamchilik’ deb atamang; ularni ‘ekspert tekshirishi kerak’ deb yozing.\n"
            ask_msg = message
            if message.strip().lower().startswith("ushbu qarorni tekshiring"):
                ask_msg = ("Adliya ekspertizasi xulosasini 3333-son buyruq shaklida yozing: 1) Xulosa turi: ijobiy / tuzatiladigan kamchiliklar bilan ijobiy / salbiy; "
                           "2) Har bir kamchilik: qaysi modda, nima uchun, qarordan iqtibos; 3) Tavsiya: nima qilish kerak (masalan, amaldagi moddani keltirish). "
                           "Faqat berilgan ma’lumot va qonun vositalariga tayaning; ‘noqonuniy’ demang — ‘ehtimoliy buzilish, ekspert ko‘rib chiqadi’ deng. "
                           "Xulosa yozishdan oldin law_as_of vositasi bilan har bir keltirilgan moddani, verify_quote bilan iqtiboslarni tekshiring. ENG MUHIMI: ekspert tekshirishi kerak deb belgilangan (NOANIQ) belgilarni kamchilik deb atamang. Oddiy matn, JSON emas.")
            cfg = MODELS.get(model, MODELS["mezon-lm"])
            yield {"type": "step", "id": "ai", "label": f"{cfg['label']} xulosa yozmoqda\u2026", "status": "run"}
            import queue
            import threading
            box = queue.Queue()
            _t0 = time.time()

            def work():
                try:
                    box.put(("ok", ask_ctx(ctx, history, ask_msg, "mezon-lm" if model == "demo" else model)))
                except Exception as e:  # noqa: BLE001
                    box.put(("err", e))
            threading.Thread(target=work, daemon=True).start()
            while True:
                try:
                    kind, val = box.get(timeout=10)
                    break
                except queue.Empty:
                    yield {"type": "ping"}  # heartbeat: keeps the stream alive through gunicorn / nginx / the tunnel
            if kind == "err":
                raise val
            answer, calls, secs, cfg = val
            _bd = _badge(cfg, secs, calls, time.time() - _t0)
            for i, cl in enumerate(calls):
                label, detail, ok = plain_call(cl)
                yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
            yield from _trace_events(calls)
            yield {"type": "step", "id": "ai", "label": "Xulosa tayyor", "status": "done", "detail": f"{secs:.0f} soniya" if secs else ""}
            answer = answer or "Model javob bera olmadi, qayta yuboring."
            import re as _re
            for chunk in _re.findall(r"\S+\s*", answer):
                yield {"type": "token", "text": chunk}
            yield {"type": "result", "model": f"{cfg['label']} \u00b7 {cfg['model']}", "badge": _badge(cfg, secs, calls, time.time() - _t0)}
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
    return _stream(events())


def _words(buf):
    """Complete words (with their trailing whitespace) in buf; a trailing partial word is left for later."""
    import re as _re
    return _re.findall(r"\S+\s+", buf)


def _is_default_check(message):
    return message.strip().lower().startswith("ushbu qarorni tekshiring")


def _cache_path(code):
    from . import eqaror
    d = eqaror.ROOT / "tmp_real" / "answer_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / (re_sub_code(code) + ".json")


def re_sub_code(code):
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_.-]", "_", str(code))[:80]


def _save_answer(code, answer, calls, cfg, secs):
    """Every real model answer is kept, so it can be replayed (honestly labelled) if the GPU is off."""
    try:
        rec = {"answer": answer, "calls": calls, "model": cfg["model"], "label": cfg["label"], "seconds": secs,
               "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _cache_path(code).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("regulations").warning("answer cache write failed: %s", exc)


def _replay_saved(code, message):
    """Model unreachable: replay the saved REAL answer word by word. No saved answer: show nothing."""
    from .ai.mezon_api import plain_call
    if not _is_default_check(message):
        return
    try:
        rec = json.loads(_cache_path(code).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    yield {"type": "step", "id": "ai", "label": f"{rec.get('label', 'Mezon-LM')} saqlangan javobi", "status": "run"}
    for i, cl in enumerate(rec.get("calls") or []):
        label, detail, ok = plain_call(cl)
        yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
        yield {"type": "trace", "name": cl.get("name"), "args": cl.get("args") or {}, "result": cl.get("result_summary", "")}
        time.sleep(0.25)
    yield {"type": "step", "id": "ai", "label": "Saqlangan javob", "status": "done"}
    for w in _re_words(rec.get("answer", "")):
        yield {"type": "token", "text": w}
        time.sleep(0.03)
    ts = rec.get("saved_at", "")
    try:
        t = time.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        when = time.strftime("%d.%m.%Y %H:%M", t)
    except ValueError:
        when = ts
    yield {"type": "result", "model": f"{rec.get('label', 'Mezon-LM')} · {rec.get('model', '')}",
           "badge": {"text": f"Saqlangan javob · Mezon-LM · {when}", "tools": ""}}


def _re_words(text):
    import re as _re
    return _re.findall(r"\S+\s*", text)


def _badge(cfg, secs, calls, wall=None):
    """Source badge for an AI answer: model, GPU, the real response time and the tool calls the API reports."""
    from collections import Counter
    n = Counter(c.get("name", "vosita") for c in (calls or []))
    t = secs if secs else wall
    text = f"{cfg['label']} \u00b7 GPU (RTX PRO 6000)" + (f" \u00b7 {t:.0f} s" if t else "")
    tools = ("vositalar: " + ", ".join(f"{k} \u00d7{v}" for k, v in n.items())) if n else "vositalar: ishlatilmadi"
    return {"text": text, "tools": tools}


def _trace_events(calls):
    """The model's reported tool calls, replayed against the law store: one real one-line result per call."""
    import subprocess
    from pathlib import Path
    from . import eqaror
    from .ai.real import MEZON_PY
    if not calls:
        return
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        rp = subprocess.Popen([MEZON_PY, "-X", "utf8", str(eqaror.ROOT / "tools" / "replay_calls.py")],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(Path(MEZON_PY).parents[2]), env=env)
        rp.stdin.write(json.dumps(calls).encode("utf-8"))
        rp.stdin.close()
        for ln in rp.stdout:
            t = json.loads(ln.decode("utf-8"))
            yield {"type": "trace", "name": t["name"], "args": t["args"], "result": t["result"]}
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("regulations").warning("trace replay failed: %s", exc)
        return
