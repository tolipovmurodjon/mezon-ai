"""
Business actions. Views stay thin; everything that changes state lives here.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .ai import AnalyzerError, get_analyzer
from .models import Analysis, ChatMessage, Decision, Event, Finding, RegulationRequest
from .text import format_ai_text

log = logging.getLogger("regulations")

AUTO_PROMPT = "Ushbu qaror loyihasini barcha hujjatlari bilan birga qonunchilikka, Konstitutsiyaga va etik me’yorlarga muvofiqligini tekshir."


def mark_opened(req, user):
    """First time an expert opens a new request, it moves to 'in review'."""
    if req.status == RegulationRequest.Status.NEW:
        req.status = RegulationRequest.Status.IN_REVIEW
        req.save(update_fields=["status", "updated_at"])
        Event.objects.create(request=req, kind=Event.Kind.OPENED, actor=user, text="Tekshiruv boshlandi")


def run_analysis(req, user=None, analyzer=None, render_html=True):
    """
    Run the analyzer, persist everything it says, and re-yield each event so
    a view can stream it. The last event is {"type": "result", ...}.
    """
    analyzer = analyzer or get_analyzer()
    documents = list(req.documents.all())
    analysis = Analysis.objects.create(
        request=req, started_by=user, backend=analyzer.name, model_name=analyzer.model_name,
        rules_version=settings.MEZON_AI.get("RULES_VERSION", ""), text_sha256=req.text_fingerprint(),
    )
    steps, checks, sources, findings, summary = {}, [], [], [], []
    try:
        if not documents:
            raise AnalyzerError("So‘rovga hech qanday hujjat biriktirilmagan.")
        for event in analyzer.analyze(req, documents):
            kind = event.get("type")
            if kind == "step":
                sid = event.get("id") or f"s{len(steps)}"
                steps[sid] = {**steps.get(sid, {}), **{k: v for k, v in event.items() if k != "type"}, "id": sid}
            elif kind == "check":
                checks.append({k: v for k, v in event.items() if k != "type"})
            elif kind == "source":
                sources.append({k: v for k, v in event.items() if k != "type"})
            elif kind == "finding":
                findings.append(event)
            elif kind == "token":
                summary.append(event.get("text", ""))
            elif kind == "verdict":
                analysis.verdict = event.get("verdict") or ""
                analysis.recommendation = event.get("recommendation") or ""
                analysis.score = event.get("score")
            yield event

        if analysis.verdict not in Analysis.Verdict.values:
            raise AnalyzerError("Model yakuniy xulosa (verdict) bermadi.")
        with transaction.atomic():
            analysis.steps = list(steps.values())
            analysis.checks = checks
            analysis.sources = sources
            analysis.summary = "".join(summary).strip()
            analysis.state = Analysis.State.DONE
            analysis.finished_at = timezone.now()
            analysis.save()
            Finding.objects.bulk_create([
                Finding(
                    analysis=analysis, order=i, code=f.get("code", "")[:40], category=f.get("category", "")[:80],
                    severity=f.get("severity") if f.get("severity") in Finding.Severity.values else "info",
                    title=f.get("title", "")[:240], explanation=f.get("explanation", ""),
                    quote=f.get("quote", ""), quote_source=f.get("quote_source", "")[:200],
                    law_ref=f.get("law_ref", "")[:300], law_text=f.get("law_text", ""), suggestion=f.get("suggestion", ""),
                ) for i, f in enumerate(findings)
            ])
            Event.objects.create(
                request=req, kind=Event.Kind.ANALYZED, actor=user,
                text=f"{analysis.get_verdict_display()} · {analysis.score}% · {len(findings)} ta muammo",
            )
        result = {"type": "result", "analysis_id": analysis.pk, "verdict": analysis.verdict,
                  "recommendation": analysis.recommendation}
        if render_html:
            result["summary_html"] = str(format_ai_text(analysis.summary))
            result["html"] = render_to_string("regulations/partials/_analysis_widgets.html",
                                              {"req": req, "analysis": analysis, "analyzer": analyzer})
            result["decision_html"] = render_to_string("regulations/partials/_ai_recommendation.html",
                                                       {"analysis": analysis})
        yield result
    except Exception as exc:  # the expert must see the failure, never a half-made verdict
        log.exception("Analysis failed for %s", req.number)
        analysis.state = Analysis.State.FAILED
        analysis.error = str(exc)
        analysis.finished_at = timezone.now()
        analysis.steps = list(steps.values())
        analysis.save()
        Event.objects.create(request=req, kind=Event.Kind.ANALYSIS_FAILED, actor=user, text=str(exc)[:300])
        message = str(exc) if isinstance(exc, AnalyzerError) else "Tahlil vaqtida kutilmagan xato yuz berdi."
        yield {"type": "error", "message": message}


def run_chat(req, user, message, analyzer=None, model=None):
    """Store the question, answer with the selected model, store the answer."""
    from .ai.mezon_api import MODELS, TOOL_LABELS, ask_model
    analysis = req.latest_analysis
    history = [{"role": m.role, "content": m.content} for m in req.messages.all()]
    ChatMessage.objects.create(request=req, role=ChatMessage.Role.USER, content=message, author=user)
    try:
        if model == "demo":
            fl = list(analysis.findings.all()) if analysis else []
            if fl:
                lines = ["Mezon qoida tekshiruvi natijalari (haqiqiy, qayta o‘ynatildi):", ""]
                for f in fl:
                    lines.append(f"- **{f.title}** — {f.law_ref}." + (f" Matndan: “{f.quote[:160]}”" if f.quote else ""))
                lines += ["", "Bular ehtimoliy buzilish belgilari — ekspert ko‘rib chiqadi."]
            else:
                lines = ["Mezon qoidalari bo‘yicha bu qarorda kamchilik belgisi topilmadi."]
            demo_text = "\n".join(lines)
            yield {"type": "token", "text": demo_text}
            answer, meta = demo_text, "Demo (haqiqiy qoida natijalari)"
        else:
            yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qildi", "status": "done",
                   "detail": f"{req.documents.count()} ta hujjat kontekstga qo‘shildi"}
            cfg = MODELS.get(model) or MODELS["qwen"]
            yield {"type": "step", "id": "model", "label": f"{cfg['label']} javob tayyorlamoqda", "status": "run"}
            answer, calls, secs, cfg = ask_model(req, history, message, model)
            from .ai.mezon_api import plain_call
            for i, c in enumerate(calls):
                label, detail, ok = plain_call(c)
                yield {"type": "step", "id": f"tool{i}", "status": "done" if ok else "warn", "label": label, "detail": detail}
            if not answer:
                yield {"type": "step", "id": "wait", "label": "Javob tayyorlanmoqda…", "status": "run"}
                answer = "Model yakuniy javobni shakllantira olmadi. Savolni aniqroq qilib qayta yuboring."
            yield {"type": "step", "id": "model", "label": "Javob tayyor", "status": "done",
                   "detail": f"{secs:.0f} soniya" if secs else ""}
            yield {"type": "token", "text": answer}
            meta = f"{cfg['label']} · {cfg['model']}"
        answer = answer or "Javob bo‘sh qaytdi."
        msg = ChatMessage.objects.create(request=req, role=ChatMessage.Role.ASSISTANT, content=answer)
        yield {"type": "result", "html": str(format_ai_text(answer)), "id": msg.pk, "model": meta}
    except Exception as exc:
        log.exception("Chat failed for %s", req.number)
        yield {"type": "error", "message": str(exc) if isinstance(exc, AnalyzerError) else "Javob olishda xato yuz berdi."}


@transaction.atomic
def decide(req, user, outcome, comment=""):
    if not req.is_open:
        raise ValueError("Bu so‘rov bo‘yicha qaror allaqachon qabul qilingan.")
    if outcome not in Decision.Outcome.values:
        raise ValueError("Noma’lum qaror.")
    analysis = req.latest_analysis
    decision = Decision.objects.create(
        request=req, outcome=outcome, comment=comment.strip(), decided_by=user, analysis=analysis,
        ai_recommendation=analysis.recommendation if analysis else "",
    )
    req.status = RegulationRequest.Status.ACCEPTED if outcome == "accept" else RegulationRequest.Status.REJECTED
    req.save(update_fields=["status", "updated_at"])
    Event.objects.create(
        request=req, kind=Event.Kind.ACCEPTED if outcome == "accept" else Event.Kind.REJECTED, actor=user,
        text=(comment.strip()[:280] or decision.get_outcome_display()),
    )
    return decision
