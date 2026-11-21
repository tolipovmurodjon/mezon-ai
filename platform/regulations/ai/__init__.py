"""
Mezon AI: pluggable legal-analysis backends.

    from regulations.ai import get_analyzer
    analyzer = get_analyzer()
    for event in analyzer.analyze(request_obj, documents): ...

Pick the backend with settings.MEZON_AI["BACKEND"] (env MEZON_AI_BACKEND):
"demo", "http", "openai", or a dotted path to your own BaseAnalyzer subclass.
"""
from django.conf import settings
from django.utils.module_loading import import_string

from .base import AnalyzerError, BaseAnalyzer

BACKENDS = {
    "demo": "regulations.ai.demo.DemoAnalyzer",
    "http": "regulations.ai.remote.RemoteAnalyzer",
    "openai": "regulations.ai.openai_compat.OpenAICompatAnalyzer",
    "real": "regulations.ai.real.RealAnalyzer",
}


def get_analyzer(backend=None):
    config = dict(settings.MEZON_AI)
    name = backend or config.get("BACKEND") or "demo"
    cls = import_string(BACKENDS.get(name, name))
    return cls(config)


__all__ = ["get_analyzer", "BaseAnalyzer", "AnalyzerError", "BACKENDS"]
