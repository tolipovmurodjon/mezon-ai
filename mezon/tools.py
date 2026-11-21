"""The five law tools Mezon-LM calls (playbook stage 1). Every lookup needs a date: the law as it read that day.

    from mezon.tools import TOOLS, call
    call("law_as_of", {"act": "O'RQ-682", "article": "40", "date": "2025-10-23"}, law)

TOOLS is the JSON-schema list for Qwen's chat template (tools=TOOLS); call() runs one tool and returns a JSON-able
dict. Results carry the edition and the lex.uz link, so every claim can be checked. Nothing here calls a network.
"""

import re

from research.textnorm import fold

TOOLS = [
    {"type": "function", "function": {
        "name": "law_as_of",
        "description": "Text of one article (or part / clause) of an act exactly as it read on a date, with the edition and lex.uz link.",
        "parameters": {"type": "object", "required": ["act", "article", "date"], "properties": {
            "act": {"type": "string", "description": "The act exactly as the question names it (its title or its number, "
                                                         "for example a code's title or a law number like O'RQ-682)"},
            "article": {"type": "string", "description": "Article number ('40'), or a path ('art:40/part:2', 'annex:1/cl:92')"},
            "date": {"type": "string", "description": "YYYY-MM-DD: the decision date"}}}}},
    {"type": "function", "function": {
        "name": "list_editions",
        "description": "All stored editions of an act (start dates), and whether / when it lost force.",
        "parameters": {"type": "object", "required": ["act"], "properties": {
            "act": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "search_law",
        "description": "Find articles in force on a date that match words (Latin or Cyrillic).",
        "parameters": {"type": "object", "required": ["query", "date"], "properties": {
            "query": {"type": "string"}, "date": {"type": "string"},
            "act": {"type": "string", "description": "optional: search inside one act"}}}}},
    {"type": "function", "function": {
        "name": "get_decision",
        "description": "A local decision by registration number: date, body, title, and its text split into preamble and clauses.",
        "parameters": {"type": "object", "required": ["reg"], "properties": {
            "reg": {"type": "string", "description": "e.g. 231-4-59-Q/24"}}}}},
    {"type": "function", "function": {
        "name": "verify_quote",
        "description": "Check that a quote is word for word in the article as it read on the date. Use before citing.",
        "parameters": {"type": "object", "required": ["act", "article", "date", "quote"], "properties": {
            "act": {"type": "string"}, "article": {"type": "string"}, "date": {"type": "string"},
            "quote": {"type": "string"}}}}},
]

MAX_TEXT = 4000  # characters of one unit returned to the model


def _path(article: str) -> str:
    a = str(article).strip()
    if ":" in a:
        return a
    m = re.search(r"(\d+(?:\s*[-–]\s*\d+)?)", a)
    return "art:" + re.sub(r"\s+", "", m.group(1)).replace("–", "-") if m else a


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s)).strip()


def _missing(law, key: str, path: str, act: str, date: str, ed) -> dict:
    """Not a bare error: say whether the article existed earlier and when it left the text."""
    out = {"error": f"{path} not found in {act} as on {date}", "ok": False, "in_force": False, "act_key": key,
           "article": path.removeprefix("art:"), "edition": ed["ondate"]}
    rows = law.con.execute("SELECT seq_to, notes FROM units WHERE act_key=? AND path=? ORDER BY seq_to", (key, path)).fetchall()
    eds = law.editions(key)
    if rows:
        last = max(r["seq_to"] for r in rows)
        nxt = [e for e in eds if e["seq"] > last]
        lastd = [e for e in eds if e["seq"] == last]
        note = next((r["notes"] for r in reversed(rows) if r["notes"]), None) or law.act(key)["lost_force"]
        out.update(reason=f"not in the edition in force on {date}",
                   last_seen_edition=lastd[0]["valid_from"] if lastd else None,
                   removed_in_edition=nxt[0]["valid_from"] if nxt else None, lost_force_note=note)
    else:
        out["reason"] = f"{path} does not appear in any stored edition of this act"
    return out


def _unit(law, act: str, article: str, date: str):
    key = law.find_act(act)
    if key is None:
        return None, {"error": f"act not in the law store: {act}"}
    in_force, ed = law.in_force(key, date)
    if ed is None:
        return None, {"error": f"{act} did not exist on {date}", "act_key": key}
    path = _path(article)
    unit = law.get_unit(key, path, date)
    if unit is None:
        return None, _missing(law, key, path, act, date, ed)
    unit["in_force"] = in_force
    return unit, None


def law_as_of(law, act: str, article: str, date: str) -> dict:
    unit, err = _unit(law, act, article, date)
    if err:
        return err
    out = {k: unit[k] for k in ("act_key", "path", "heading", "edition", "valid_from", "valid_to", "in_force", "url")}
    out["provisional"] = unit["provisional"]
    out["text"] = unit["text"][:MAX_TEXT] + (" …" if len(unit["text"]) > MAX_TEXT else "")
    return out


def list_editions(law, act: str) -> dict:
    key = law.find_act(act)
    if key is None:
        return {"error": f"act not in the law store: {act}"}
    a = law.act(key)
    return {"act_key": key, "title": a["title"], "number": a["number"], "lost_force": a["lost_force"],
            "editions": [e["valid_from"] for e in law.editions(key)]}


def _remote_search(query: str, date: str, k: int, key: str | None, rerank: bool) -> list[dict]:
    """Hybrid (FTS5 + bge-m3, rank fusion, optional reranker) from the box's retrieval service (mezon.retrieval.service)."""
    import json
    import os
    import urllib.request
    url = os.environ.get("MEZON_RETRIEVAL_URL", "http://127.0.0.1:8765").rstrip("/") + "/search"
    body = json.dumps({"query": query, "date": date, "k": k, "mode": "hybrid", "rerank": rerank, "act_key": key}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["hits"]


def search_law(law, query: str, date: str, act: str | None = None, k: int = 5, mode: str = "fts", rerank: bool = True) -> dict:
    """mode "fts" (default, the exam's behaviour) searches the local store; "hybrid" asks the retrieval service."""
    key = law.find_act(act) if act else None
    if mode == "hybrid":
        hits = _remote_search(query, date, k, key, rerank)
    else:
        hits = law.search(query, date, k=k, act_key=key)
    return {"date": date, "hits": [{"act_key": h["act_key"], "path": h["path"], "heading": h["heading"],
                                    "edition": h["edition"], "text": h["text"][:600]} for h in hits]}


def get_decision(decisions, reg: str) -> dict:
    if decisions is None:
        return {"error": "no decision store"}
    d = decisions.get(reg) if hasattr(decisions, "get") else None
    if not d and hasattr(decisions, "by_reg"):  # DecisionStore is keyed by id; the model knows the reg number
        ids = decisions.by_reg(reg)
        d = decisions.get(ids[0]) if ids else None
    if not d:
        return {"error": f"decision not found: {reg}"}
    if "reg_number" in d:  # DecisionStore row: text only, never the label / trigger / cancelled_numbers (exam gold)
        return {"reg": d["reg_number"], "date": d.get("adopted"), "body": d.get("body"), "title": d.get("title"),
                "text": (d.get("text") or "")[:8000], "url": d.get("url")}
    keep = ("reg", "date", "body", "title", "preamble", "clauses", "url")
    return {k: d[k] for k in keep if k in d}


def verify_quote(law, act: str, article: str, date: str, quote: str) -> dict:
    unit, err = _unit(law, act, article, date)
    if err:
        return {"ok": False, **err}
    q = _norm(quote.strip(" .…\"'“”«»"))
    ok = len(q) >= 12 and q in _norm(unit["text"])
    return {"ok": ok, "act_key": unit["act_key"], "path": unit["path"], "edition": unit["edition"],
            "in_force": unit["in_force"], "reason": "" if ok else ("quote too short" if len(q) < 12 else
                                                                  "not word for word in this edition")}


def call(name: str, args: dict, law, decisions=None) -> dict:
    """Run one tool call from the model; bad arguments come back as an error the model can read, never a crash."""
    try:
        if name == "get_decision":
            return get_decision(decisions, **args)
        fn = {"law_as_of": law_as_of, "list_editions": list_editions, "search_law": search_law,
              "verify_quote": verify_quote}.get(name)
        if fn is None:
            return {"error": f"unknown tool: {name}"}
        return fn(law, **args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
