"""Template helpers: kit icons, Uzbek number and date formats."""
from django import template
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from ..text import format_ai_text

register = template.Library()


@register.simple_tag
def icon(name, cls="icon"):
    return format_html('<svg class="{}" aria-hidden="true"><use href="#i-{}"/></svg>', cls, name)


@register.filter
def uznum(value, digits=0):
    """12480 -> '12 480'; 91.3 -> '91,3'."""
    if value in (None, ""):
        return "—"
    return f"{float(value):,.{int(digits)}f}".replace(",", " ").replace(".", ",")


@register.filter
def signed(value):
    return ("+" if value > 0 else "−" if value < 0 else "") + uznum(abs(value))


@register.filter
def uzdate(value):
    return timezone.localtime(value).strftime("%d.%m.%Y") if value else "—"


@register.filter
def isodmy(value):
    """2024-07-16 -> 16.07.2024"""
    try:
        y, m, d = str(value)[:10].split("-")
        return f"{d}.{m}.{y}"
    except ValueError:
        return value


@register.filter
def uztime(value):
    return timezone.localtime(value).strftime("%H:%M") if value else ""


@register.filter
def uzdatetime(value):
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else "—"


@register.filter
def display_name(user):
    return (user.get_full_name() or user.username) if user else "Tizim"


@register.filter
def short_name(user):
    """'First Last' -> 'First L.'"""
    parts = (user.get_full_name() if user else "").split()
    return f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else display_name(user)


@register.filter
def initials(user):
    return "".join(p[0] for p in display_name(user).split()[:2]).upper() or "?"


@register.filter
def status_tone(status):
    return {"in_review": "warning", "accepted": "good", "rejected": "critical"}.get(status, "")


@register.filter
def ai_format(text):
    return format_ai_text(text)


@register.filter
def spark(values):
    return ",".join(str(v) for v in values)


@register.simple_tag(takes_context=True)
def query(context, **kwargs):
    """Current querystring with some keys replaced: {% query page=2 %}."""
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        if v in (None, ""):
            params.pop(k, None)
        else:
            params[k] = v
    return mark_safe(escape("?" + params.urlencode()))


_CHECK_UZ = {
    "R_basis": "kuchsiz moddaga tayangan",
    "R_business_3m": "biznesga 3 oydan kam muddat",
    "R_competence_land": "yer bo‘yicha vakolat",
    "R_duplicate": "takroriy qaror",
    "R_double_repeal": "allaqachon bekor qilingan hujjatni bekor qiladi",
    "R_discussion": "jamoatchilik muhokamasi qayd etilmagan",
    "R_discussion_short": "muhokama 15 kundan qisqa",
    "R_expertise": "adliya ekspertizasi qayd etilmagan",
    "R_retroactive": "orqaga qaytuvchi kuch",
    "R_form": "qaror o‘rniga farmoyish",
    "R_tax_timing": "soliq stavkasi muddati",
    "R_corruption_factor": "korrupsiyaviy omil",
}


@register.filter
def checks_uz(value):
    """'R_basis,R_expertise' -> short Uzbek reasons for list rows."""
    parts = [c for c in (value or "").split(",") if c]
    return " · ".join(_CHECK_UZ.get(c, c) for c in parts)
