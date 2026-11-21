"""
HTTP adapter for your own model service (for example the FastAPI agent).

Your service exposes two endpoints (full contract in docs/AI_INTEGRATION.md):

    POST {MEZON_AI_URL}/v1/analyze   body: request payload    -> NDJSON events, or one JSON result
    POST {MEZON_AI_URL}/v1/chat      body: request + history  -> NDJSON token events, or {"answer": "..."}

NDJSON means one JSON event per line, streamed as the agent works, using the
event types documented in regulations/ai/base.py.
"""
import json
import urllib.error
import urllib.request

from .base import AnalyzerError, BaseAnalyzer


class RemoteAnalyzer(BaseAnalyzer):
    name = "http"
    label = "Mezon AI"

    def _post(self, path, payload):
        url = self.config["URL"].rstrip("/") + path
        headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson, application/json"}
        if self.config.get("API_KEY"):
            headers["Authorization"] = f"Bearer {self.config['API_KEY']}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=self.config.get("TIMEOUT", 180))
        except urllib.error.HTTPError as exc:
            raise AnalyzerError(f"Model xizmati {exc.code} qaytardi: {exc.read()[:300].decode('utf-8', 'replace')}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AnalyzerError(f"Model xizmatiga ulanib bo‘lmadi ({url}): {exc}") from exc

    def _events(self, resp):
        ctype = resp.headers.get("Content-Type", "")
        if "ndjson" in ctype or "jsonl" in ctype or "event-stream" in ctype:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AnalyzerError(f"Model noto‘g‘ri JSON qaytardi: {line[:200]}") from exc
        else:
            try:
                yield json.loads(resp.read().decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise AnalyzerError("Model javobi JSON emas") from exc

    def analyze(self, req, documents):
        with self._post("/v1/analyze", self.request_payload(req, documents)) as resp:
            for event in self._events(resp):
                if "type" in event:
                    yield event
                else:
                    yield from result_to_events(event)

    def chat(self, req, analysis, history, message):
        payload = {
            "request": self.request_payload(req, req.documents.all()),
            "analysis": self.analysis_payload(analysis),
            "history": history,
            "message": message,
        }
        with self._post("/v1/chat", payload) as resp:
            for event in self._events(resp):
                if event.get("type") == "token":
                    yield event
                elif "answer" in event:
                    yield {"type": "token", "text": event["answer"]}


def result_to_events(result):
    """Turn a one-shot JSON result into the same events a streaming agent sends."""
    for step in result.get("steps", []):
        yield {"type": "step", "status": "done", **step}
    for check in result.get("checks", []):
        yield {"type": "check", **check}
    for source in result.get("sources", []):
        yield {"type": "source", **source}
    for f in result.get("findings", []):
        yield {"type": "finding", **f}
    if result.get("summary"):
        yield {"type": "token", "text": result["summary"]}
    yield {
        "type": "verdict",
        "verdict": result.get("verdict", "minor"),
        "recommendation": result.get("recommendation", "revise"),
        "score": result.get("score"),
    }
