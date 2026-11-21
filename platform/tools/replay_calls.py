"""
Run under the Mezon venv. stdin = [{"name","args","ok"}...] (the tool calls the model reported in `mezon_calls`);
stdout = one JSON line per call with the REAL result of that same deterministic call (law store), summarised in one line.
"""
import json
import os
import sys

sys.path.insert(0, os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"))


def one_line(name, args, res):
    if not isinstance(res, dict):
        return str(res)[:160]
    if name == "law_as_of":
        if "text" in res:
            txt = " ".join(res["text"].split())[:140]
            return ("kuchda" if res.get("in_force") else "kuchsiz") + f", {res.get('path', '')}: \u00ab{txt}\u2026\u00bb"
        if res.get("removed_in_edition"):
            return f"topilmadi \u2014 {res['removed_in_edition']} dan kuchsiz"
        return res.get("error", "topilmadi")[:140]
    if name == "verify_quote":
        return "so\u2018zma-so\u2018z mos" if res.get("ok") or res.get("found") or res.get("verbatim") else "mos kelmadi"
    if name == "search_law":
        hits = res.get("hits") or []
        return f"{len(hits)} ta natija" + (f": {hits[0]['path']} \u2014 {' '.join(hits[0].get('text', '').split())[:100]}" if hits else "")
    if name == "list_editions":
        return f"{len(res.get('editions') or [])} ta tahrir" + (f", oxirgisi {res['editions'][-1]}" if res.get("editions") else "")
    if name == "get_decision":
        return res.get("error") or f"{res.get('reg_number', '')} {str(res.get('title', ''))[:100]}"
    return json.dumps(res, ensure_ascii=False)[:160]


def main():
    calls = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    from mezon import tools
    from mezon.decisions.store import DecisionStore
    from mezon.rules.run import load_law
    law, ds = load_law(), DecisionStore()
    for c in calls:
        try:
            res = tools.call(c["name"], c.get("args") or {}, law, ds)
        except Exception as exc:  # noqa: BLE001
            res = {"error": str(exc)}
        out = {"name": c["name"], "args": c.get("args") or {}, "result": one_line(c["name"], c.get("args") or {}, res)}
        sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
