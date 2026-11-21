"""
Run under the Mezon venv:  stdin = {"text": "...", "title": "..."}  stdout = Report JSON.
Audits a raw decision text with the real mezon.rules engine (no store row needed).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"))
from mezon.decisions.store import DecisionStore  # noqa: E402
from mezon.rules.run import audit, load_law  # noqa: E402
from research.regulation_window import MONTHS  # noqa: E402
from research.regnum import find_all  # noqa: E402
from research.textnorm import normalize  # noqa: E402


class OneDoc(DecisionStore):
    def __init__(self, d):
        super().__init__()
        self._d = d

    def get(self, decision_id):
        return self._d if decision_id == self._d["id"] else super().get(decision_id)


def build(text, title):
    t = normalize(text)
    regs = find_all(t)
    # The decision's own number is the one in its signature ("355-4-68-Q/25 -son"), not one it cites ("... -sonli qaror").
    own = [m for m in re.finditer(r"(\d{1,4}-\d{1,2}-\d{1,3}-[QF]/\d{2}|[IVX]{1,4}-\d{1,3}-\d{1,4}-\d{1,2}-\d{1,3}-K/\d{2})\s*-?\s*son(?!li)", t)]
    p = {}
    pos = None
    if own:
        raw = own[0].group(1)
        p = next((r for r in regs if r["raw"] == raw), regs[-1] if regs else {})
        pos = own[0].start()
    elif regs:
        p = regs[-1]
    seg = t[max(0, pos - 220):pos] if pos else t
    dates = re.findall(r"(20\d\d)\W{0,3}yil\W{0,3}(\d{1,2})\W{0,3}([a-zA-Z']+)", seg) or re.findall(r"(20\d\d)\W{0,3}yil\W{0,3}(\d{1,2})\W{0,3}([a-zA-Z']+)", t)
    adopted = ""
    for y, d, m in reversed(dates):
        key = next((k for k in MONTHS if m.lower().startswith(k)), None)
        if key:
            adopted = f"{y}-{MONTHS[key]:02d}-{int(d):02d}"
            break
    return {
        "id": "upload:1", "src_id": "upload", "source": "upload", "role": "adopted", "reg_number": p.get("raw", ""),
        "type": p.get("type", "Q"), "region": p.get("region"), "district": p.get("district"), "year": p.get("year"),
        "body": "", "title": title, "adopted": adopted, "entry_into_force": adopted, "published": None, "lost_force": "",
        "is_normative": None, "url": "", "text": text, "clauses": [], "stages": {}, "label": "none", "trigger": "",
        "cancelled_numbers": "", "disc_start": None, "disc_end": None, "proposals": None,
    }


def audit_report(text, title=""):
    d = build(text, title)
    store = OneDoc(d)
    law = load_law()
    matched = None
    ids = store.by_reg(d["reg_number"]) if d["reg_number"] else []
    if ids:
        st = store.get(ids[0])
        from research.textnorm import bag_similarity as similarity
        # the uploaded text IS the stored decision (same registration number, near-identical text): use its stored audit
        if st and st.get("text") and similarity(st["text"], d["text"]) >= 0.9:
            matched = {"id": st["id"], "url": st.get("url") or "", "reg": st["reg_number"], "title": st.get("title") or ""}
            rep = audit(st["id"], law, store).to_dict()
        else:
            # same registration number but different text: still run the duplicate rule against stored decisions of the same body
            if st and st.get("title"):
                d["title"] = st["title"]
            d["source"] = "lex.uz"
            rep = audit("upload:1", law, store).to_dict()
    else:
        d["source"] = "lex.uz" if d["reg_number"] else d["source"]
        rep = audit("upload:1", law, store).to_dict()
    rep["matched"] = matched
    rep["detected"] = {"reg": d["reg_number"], "region": d["region"], "district": d["district"], "adopted": d["adopted"]}
    return rep


if __name__ == "__main__":
    inp = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    rep = audit_report(inp["text"], inp.get("title", ""))
    sys.stdout.buffer.write(json.dumps(rep, ensure_ascii=False).encode("utf-8"))
