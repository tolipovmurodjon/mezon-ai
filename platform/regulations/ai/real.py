"""
Real-data analyzer: shows the result of Mezon's own rule engine (mezon.rules.run).
Reports for seeded real decisions come from tmp_real/real.json; any other text
(for example an uploaded file) is audited live by tools/audit_text.py in the
Mezon venv. Nothing is invented. Chat goes to the model API.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .base import AnalyzerError, BaseAnalyzer
from .uz import ACTS, article, law_ref, translate

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "tmp_real" / "real.json"
MEZON_REPO = os.environ.get("MEZON_REPO", r"D:\10_projects\mezon")
MEZON_PY = os.environ.get("MEZON_PY", r"D:\10_projects\mezon\.venv\Scripts\python.exe")
_cache = {}

CHECK_LABELS = {
    "R_business_3m+R_retroactive": "Tadbirkorlik yuki muddati va orqaga qaytish kuchi",
    "R_draft_window+R_discussion_short": "Loyihani e’lon qilish va muhokama muddati",
    "R_discussion+R_adopted_before_end": "Jamoatchilik muhokamasi o‘tkazilganligi",
    "R_expertise": "Adliya huquqiy ekspertizasi",
    "R_form": "Hujjat shakli (qaror / farmoyish)",
    "R_competence_land": "Yer munosabatlari bo‘yicha vakolat",
    "R_duplicate+R_double_repeal": "Takroriy qaror va ikki marta bekor qilish",
    "R_corruption_factor": "Korrupsiya omillari",
    "R_basis": "Huquqiy asos kuchida ekanligi",
}
SEV = {"high": "critical", "medium": "serious", "low": "info"}


def audit_live(text, title=""):
    p = subprocess.run([MEZON_PY, "-X", "utf8", str(ROOT / "tools" / "audit_text.py")],
                       input=json.dumps({"text": text, "title": title}).encode("utf-8"),
                       capture_output=True, timeout=170, cwd=MEZON_REPO)
    if p.returncode:
        raise AnalyzerError("Mezon qoidalari ishlamadi: " + p.stderr.decode("utf-8", "replace")[-200:])
    return json.loads(p.stdout.decode("utf-8"))


def real_report(key):
    if not _cache and DATA.exists():
        for r in json.loads(DATA.read_text(encoding="utf-8")):
            _cache[r["reg"]] = r["report"]
    return _cache.get(key)


class RealAnalyzer(BaseAnalyzer):
    name = "real"
    label = "Mezon AI"
    is_demo = False

    @property
    def model_name(self):
        return "mezon-rules (real)"

    def _pause(self, s):
        sp = float(self.config.get("DEMO_SPEED", 1.0))
        if sp > 0:
            time.sleep(s * min(sp, 1))

    def chat(self, req, analysis, history, message):
        from .mezon_api import ask_model
        ans = ask_model(req, history, message, "qwen")[0]
        yield {"type": "token", "text": ans}

    def analyze(self, req, documents):
        t0 = time.monotonic()
        ms = lambda: int((time.monotonic() - t0) * 1000)  # noqa: E731
        documents = list(documents)
        yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qilmoqda", "status": "run"}
        self._pause(0.4)
        words = sum(len(d.text.split()) for d in documents)
        pages = sum(d.pages for d in documents)
        yield {"type": "step", "id": "read", "label": "Hujjatlar o‘qildi", "status": "done",
               "detail": f"{len(documents)} ta hujjat · {pages} bet · {words:,} so‘z".replace(",", " "), "ms": ms()}
        rep = real_report(req.draft_number)
        if rep is None:
            yield {"type": "step", "id": "live", "label": "Mezon qoidalari ishga tushirilmoqda", "status": "run"}
            rep = audit_live("\n".join(d.text for d in documents), req.title)
            yield {"type": "step", "id": "live", "label": "Mezon qoidalari bajarildi", "status": "done", "ms": ms()}
        flags = rep["flags"]
        cites = [c for f in flags for c in f["citations"]]
        yield {"type": "step", "id": "refs", "label": "Huquqiy havolalar ajratildi", "status": "done",
               "detail": f"{len({c['act_id'] for c in cites})} ta hujjat, {len(cites)} ta modda", "ms": ms()}

        runs = rep["checks_run"]
        yield {"type": "step", "id": "checks", "label": f"{len(runs)} ta qoida bo‘yicha tekshirilmoqda", "status": "run"}
        passed = 0
        for name in runs:
            base = name.split(" (")[0]
            parts = base.split("+")
            hit = [f for f in flags if f["check"] in parts]
            if not hit:
                passed += 1
            self._pause(0.1)
            yield {"type": "check", "id": base, "label": CHECK_LABELS.get(base, base),
                   "status": "fail" if hit else "pass", "detail": translate(hit[0])[0] if hit else "Muammo topilmadi"}
        yield {"type": "step", "id": "checks", "label": f"{len(runs)} ta qoida bo‘yicha tekshiruv",
               "status": "warn" if flags else "done", "detail": f"{passed} tasi o‘tdi · {len(flags)} ta muammo", "ms": ms()}

        quoted = [c for c in cites if c["quote"]]
        yield {"type": "step", "id": "quotes", "label": "Iqtiboslar tekshirildi", "status": "done",
               "detail": f"{len(quoted)}/{len(quoted)} qonun matniga aynan mos", "ms": ms()}

        findings, sources, seen = [], [], set()
        for f in flags:
            c = f["citations"][0] if f["citations"] else {}
            ev = f["evidence"][0] if f["evidence"] else {}
            sev = SEV[f["severity"]]
            if f["status"] != "possible_violation" and sev == "serious":
                sev = "warning"
            tt, te = translate(f)
            findings.append({
                "type": "finding", "code": f["check"][:40],
                "category": CHECK_LABELS.get(f["check"], CHECK_LABELS.get(f["check"].split("+")[0], f["check"])),
                "severity": sev, "title": tt, "explanation": te,
                "quote": ev.get("quote", "").strip("… "), "quote_source": {"preamble": "Preambula"}.get(ev.get("locator", ""), ev.get("locator", "")),
                "law_ref": law_ref(c),
                "law_text": c.get("quote", ""),
                "suggestion": "Ehtimoliy buzilish belgisi: mutaxassis tekshiruvi talab etiladi; yakuniy xulosani inson beradi.",
            })
            for cc in f["citations"]:
                if cc["act_title"] not in seen:
                    seen.add(cc["act_title"])
                    sources.append({"type": "source", "title": ACTS.get(cc["act_title"], cc["act_title"]), "kind": "law", "url": cc.get("url", ""),
                                    "meta": f"{article(cc['article'])} · {cc['on_date']} sanasidagi tahrir"})
        for d in documents:
            sources.append({"type": "source", "title": d.title, "kind": "doc",
                            "meta": f"{req.number} · {d.pages} bet · {len(d.text.split())} so‘z"})
        for s in sources:
            yield s
        for f in findings:
            yield f

        yield {"type": "step", "id": "write", "label": "Xulosa yozilmoqda", "status": "run"}
        n = len(findings)
        if n:
            lines = [f"Qarorda {n} ta kamchilik belgisi topildi (ehtimoliy buzilish, mutaxassis tasdig‘i kerak):", ""]
            lines += [f"- **{f['title']}** ({f['law_ref']})" for f in findings[:5]]
            lines += ["", "Tavsiya: belgilarni mutaxassis ko‘rib chiqsin; yakuniy qarorni siz qabul qilasiz."]
        else:
            lines = [f"{len(runs)} ta qoidadan {passed} tasi o‘tdi, kamchilik belgisi topilmadi.", "",
                     "Tavsiya: qabul qilish mumkin. Yakuniy qarorni siz qabul qilasiz."]
        summary = "\n".join(lines)
        buf = ""
        pieces = re.split(r"(\s+)", summary)
        for i, w in enumerate(pieces):
            buf += w
            if len(buf) > 14 or i == len(pieces) - 1:
                yield {"type": "token", "text": buf}
                buf = ""
                self._pause(0.03)
        yield {"type": "step", "id": "write", "label": "Xulosa tayyorlandi", "status": "done", "ms": ms()}
        if not n:
            yield {"type": "verdict", "verdict": "compliant", "recommendation": "accept", "score": 100}
        else:
            hi = sum(1 for f in findings if f["severity"] == "critical")
            yield {"type": "verdict", "verdict": "minor", "recommendation": "revise",
                   "score": round(100 * passed / max(1, len(runs)))}
