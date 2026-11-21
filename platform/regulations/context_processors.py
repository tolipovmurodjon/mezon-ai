from django.conf import settings


def shell(request):
    """Values the sidebar and top bar need on every page."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from .models import RegulationRequest

    return {
        "nav_open_count": 0,
        "ai_is_demo": settings.MEZON_AI.get("BACKEND", "demo") == "demo",
    }
