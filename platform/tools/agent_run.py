"""
Run under the Mezon venv. stdin = {"text","date","title","check_rules"}; stdout = one JSON event per line, flushed as each REAL step finishes:
  basis -> law_start/law (law_as_of per cited article) -> rules (mezon.rules over the text).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def out(o):
    sys.stdout.buffer.write((json.dumps(o, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    inp = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    text, date = inp["text"], inp["date"]
    from mezon import tools
    from mezon.rules.basis import cited_articles
    from mezon.rules.run import load_law
    law = load_law()
    arts = []
    if law is not None and text:
        exists = lambda key, path: law.get_unit(key, path, date) is not None  # noqa: E731
        try:
            arts = cited_articles(text, exists)
        except Exception:  # noqa: BLE001
            arts = cited_articles(text)
        if not arts:
            arts = cited_articles(text + " qaror qilaman: 1. ...")
    titles = {}
    for key, path, sentence in arts[:12]:
        try:
            titles[key] = law.act(key)["title"]
        except Exception:  # noqa: BLE001
            titles[key] = key
    out({"ev": "basis", "cites": [{"key": k, "act": titles[k], "article": p.removeprefix("art:")} for k, p, _ in arts[:12]]})
    for key, path, sentence in arts[:12]:
        art = path.removeprefix("art:")
        out({"ev": "law_start", "act": titles[key], "article": art})
        r = tools.law_as_of(law, key, path, date)
        card = {"act_key": key, "act_title": titles[key], "article": art, "sentence": sentence[:300]}
        if "text" in r:
            card.update(text=r["text"], in_force=bool(r.get("in_force")), edition=r.get("edition"), url=r.get("url") or "")
        else:
            card.update(text="", in_force=False, missing=True, removed_in=r.get("removed_in_edition"), note=r.get("lost_force_note") or "")
        out({"ev": "law", "card": card})
    if inp.get("check_rules") and text:
        out({"ev": "rules_start"})
        import audit_text
        rep = audit_text.audit_report(text, inp.get("title", ""))
        out({"ev": "rules", "report": rep})


if __name__ == "__main__":
    main()
