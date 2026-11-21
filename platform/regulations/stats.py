"""Dashboard numbers: this week vs last week, and requests per day."""
import datetime as dt
from collections import Counter, defaultdict

from django.utils import timezone

from .models import Analysis, Decision, RegulationRequest

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
CHART_DAYS = 30


def dashboard(now=None):
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    week = dt.timedelta(days=7)
    start, prev = now - week, now - 2 * week

    decisions = {d.request_id: d for d in Decision.objects.only("request_id", "decided_at", "outcome")}
    rows = []
    for r in RegulationRequest.objects.only("id", "submitted_at", "status"):
        d = decisions.get(r.id)
        rows.append((r.submitted_at, r.status, d.decided_at if d else None, d.outcome if d else None))

    def received(a, b):
        return sum(1 for at, *_ in rows if a <= at < b)

    def decided(outcome, a, b):
        return sum(1 for _, _, t, o in rows if o == outcome and t and a <= t < b)

    def backlog(t):
        return sum(1 for at, _, dt_, _ in rows if at < t and (dt_ is None or dt_ >= t))

    days = [now - dt.timedelta(days=7 - i) for i in range(8)]
    kpis = [
        {"label": "Kelgan", "value": received(start, now), "prev": received(prev, start),
         "spark": [received(days[i], days[i + 1]) for i in range(7)]},
        {"label": "Qabul qilingan", "value": decided("accept", start, now), "prev": decided("accept", prev, start),
         "spark": [decided("accept", days[i], days[i + 1]) for i in range(7)]},
        {"label": "Rad etilgan", "value": decided("reject", start, now), "prev": decided("reject", prev, start),
         "spark": [decided("reject", days[i], days[i + 1]) for i in range(7)]},
        {"label": "Jarayonda", "value": sum(1 for _, s, *_ in rows if s in RegulationRequest.OPEN_STATUSES),
         "prev": backlog(start), "spark": [backlog(days[i + 1]) for i in range(7)], "backlog": True},
    ]
    for k in kpis:
        k["diff"] = k["value"] - k["prev"]

    by_day = defaultdict(lambda: {"a": 0, "c": 0, "b": 0})
    for at, _, _, outcome in rows:
        key = "a" if outcome == "accept" else "c" if outcome == "reject" else "b"
        by_day[timezone.localtime(at).date()][key] += 1
    chart = []
    for i in range(CHART_DAYS - 1, -1, -1):
        d = today - dt.timedelta(days=i)
        chart.append({"label": f"{d.day}.{d.month:02d}", "t": f"{d.day}-{MONTHS[d.month - 1]}, {WEEKDAYS[d.weekday()]}",
                      **by_day.get(d, {"a": 0, "c": 0, "b": 0})})

    # AI verdicts on this week's requests (latest finished analysis each)
    latest = {}
    for a in Analysis.objects.filter(state="done").order_by("started_at"):
        latest[a.request_id] = a.verdict
    counts = Counter(latest.values())
    analysed = sum(counts.values())
    verdicts = [
        {"key": "compliant", "label": "Qonunga mos", "n": counts["compliant"]},
        {"key": "minor", "label": "Kamchiliklar bor", "n": counts["minor"]},
        {"key": "conflict", "label": "Ehtimoliy buzilish", "n": counts["conflict"]},
    ]
    for v in verdicts:
        v["pct"] = round(v["n"] / analysed * 100) if analysed else 0

    return {"kpis": kpis, "chart": chart, "verdicts": verdicts, "analysed": analysed, "open_now": kpis[3]["value"]}
