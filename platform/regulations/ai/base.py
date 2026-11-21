"""
The contract every analyzer follows.

An analyzer is a generator of plain-dict *events*. The review page draws them
live, and services.run_analysis() stores them. Event types:

  {"type": "step",    "id": "read", "label": "Hujjatlar o‘qildi", "status": "run|done|warn|fail",
                      "detail": "4 ta hujjat · 2 310 so‘z", "ms": 412}
  {"type": "check",   "id": "retroactivity", "label": "Orqaga qaytish kuchi",
                      "status": "pass|fail|warn|skip", "detail": "..."}
  {"type": "finding", "code": "retroactivity", "category": "Orqaga qaytish kuchi",
                      "severity": "critical|serious|warning|info", "title": "...",
                      "explanation": "...", "quote": "...", "quote_source": "Qaror loyihasi, 4-band",
                      "law_ref": "...", "law_text": "...", "suggestion": "..."}
  {"type": "source",  "title": "...", "meta": "...", "url": "https://lex.uz/..."}
  {"type": "token",   "text": "next piece of the summary"}
  {"type": "verdict", "verdict": "compliant|minor|conflict",
                      "recommendation": "accept|revise|reject", "score": 0-100}

chat() yields only {"type": "token", "text": ...} events.
"""


class AnalyzerError(Exception):
    """Raised when the model cannot be reached or answers with something unusable."""


class BaseAnalyzer:
    name = "base"
    label = "Mezon AI"
    is_demo = False

    def __init__(self, config):
        self.config = config

    @property
    def model_name(self):
        return self.config.get("MODEL", "")

    def analyze(self, req, documents):
        raise NotImplementedError

    def chat(self, req, analysis, history, message):
        raise NotImplementedError

    # -- helpers shared by adapters ----------------------------------------
    @staticmethod
    def request_payload(req, documents):
        return {
            "number": req.number,
            "draft_number": req.draft_number,
            "title": req.title,
            "doc_type": req.doc_type,
            "category": req.category,
            "region": req.region.name,
            "district": req.district,
            "issuer": {"name": req.issuer_name, "title": req.issuer_title},
            "submitted_at": req.submitted_at.isoformat(),
            "documents": [
                {"id": d.pk, "title": d.title, "kind": d.kind, "pages": d.pages, "text": d.text}
                for d in documents
            ],
        }

    @staticmethod
    def analysis_payload(analysis):
        if not analysis:
            return None
        return {
            "verdict": analysis.verdict,
            "recommendation": analysis.recommendation,
            "score": analysis.score,
            "summary": analysis.summary,
            "findings": [
                {"code": f.code, "severity": f.severity, "title": f.title, "explanation": f.explanation,
                 "quote": f.quote, "law_ref": f.law_ref, "suggestion": f.suggestion}
                for f in analysis.findings.all()
            ],
        }
