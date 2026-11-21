"""The Mezon agent: reads one decision, calls its tools step by step, and leaves a trace an expert can follow.

Maker-checker by design: the agent (maker) proposes; the verifier (checker 1) accepts a claim only if every quote is
verbatim, in the decision and in the law edition in force on the decision date; the expert (checker 2) decides.

Tools: decision_text · rules (the 14 deterministic checks) · basis (is each cited act and article in force that day?)
· law (an article as it read on a date) · search_law (higher norms in force that day) · verify_quote · llm (local
Qwen on the box, only for open questions such as a conflict with a higher norm; never from memory, always two quotes).
When the box is off the llm step says so and its questions go to the expert as open questions.
"""

import re

from mezon import llm
from mezon.rules import basis
from mezon.rules.common import SafeLaw, preamble
from mezon.rules.run import audit
from research.textnorm import fold

LLM_SYSTEM = (
    "You are a legal reviewer of Uzbek local decisions. Answer ONLY from the two texts given. Return JSON: "
    '{"verdict": "conflict" | "no_conflict" | "unclear", "decision_quote": "<exact words from the decision>", '
    '"law_quote": "<exact words from the law>", "why": "<one sentence in Uzbek>"}. '
    "If you cannot quote both texts exactly, answer unclear."
)


# Words that name the body, the date or the act type, not the subject; searching on them finds noise.  (noqa: one readable word list)
STOP = set("""tuman tumani shahar shahri viloyat viloyati hokimi hokimining hokimligi kengashi kengashining xalq deputatlari
qaror qarori qaroriga qarorining sonli yildagi yanvardagi fevraldagi martdagi apreldagi maydagi iyundagi iyuldagi
avgustdagi sentabrdagi oktabrdagi noyabrdagi dekabrdagi ozgartirish ozgartirishlar qoshimcha qoshimchalar kiritish
togrisida haqida bekor qilish respublikasi ozbekiston""".split())  # noqa: SIM905
NOISE_ACTS = {"nla", "pf6075"}  # the NLA law is cited by every flag; PF-6075's annex is a list of repealed acts


def _subject(title: str) -> str:
    words = [w for w in re.findall(r"[a-z]{5,}", fold(title).replace("'", "")) if w not in STOP and not w.endswith("dagi")]
    return " ".join(dict.fromkeys(words))


def _step(steps: list, tool: str, args: str, result: str, ok: bool = True) -> None:
    steps.append({"n": len(steps) + 1, "tool": tool, "args": args, "result": result, "ok": ok})


def _verbatim(quote: str, text: str) -> bool:
    q = fold(quote or "").strip()
    return len(q) >= 12 and q in fold(text or "")


def run(decision_id: str, law, decisions, use_llm: bool = True, k: int = 3) -> dict:
    steps: list[dict] = []
    d = decisions.get(decision_id) or {}
    text, on = d.get("text") or "", d.get("adopted") or ""
    _step(steps, "decision_text", d.get("reg_number", decision_id),
          f"{d.get('body') or ''} · {on} · {len(text):,} belgi matn" if text else "matn yo'q: faqat E-qaror bosqichlari",
          bool(text))

    report = audit(decision_id, law=law, decisions=decisions).to_dict()
    hard = [f for f in report["flags"] if f["status"] == "possible_violation"]
    _step(steps, "rules", f"{len(report.get('checks_run') or [])} ta tekshiruv",
          f"{len(report['flags'])} ta belgi ({len(hard)} tasi ehtimoliy qoidabuzarlik): "
          + (", ".join(sorted({f['check'] for f in report['flags']})) or "kamchilik topilmadi"))

    if text and law is not None:
        safe = SafeLaw(law)
        for num, _ in basis.references(text)[:6]:
            key = num[1:] if num.startswith("@") else law.find_act(num)
            if not key:
                _step(steps, "basis", num, "qonun bazasida yo'q: ekspert lex.uz da tekshiradi", False)
                continue
            ok, _ = law.in_force(key, on)
            _step(steps, "basis", f"{num.lstrip('@')} · {on}", "amalda" if ok else "shu sanada amalda emas", ok)
        for key, path, _ in basis.cited_articles(text)[:6]:
            unit = law.get_unit(key, path, on)
            gap = law.edition_gap(key, on)
            if unit and gap:
                _step(steps, "law", f"{key} {path} · {on}", f"bazada {gap[0]} dan {gap[1]} gacha tahrirlar yo'q: "
                      "ekspert lex.uz da shu sanadagi tahrirni ko'rsin", False)
            elif unit:
                _step(steps, "law", f"{key} {path} · {on}", f"amalda ({unit['edition']} tahriri)")
            elif basis._ever_existed(safe, key, path):
                note = basis._repeal_notes().get(key, {}).get(path.split(":")[1], {}).get("note", "")
                _step(steps, "law", f"{key} {path} · {on}", f"kuchini yo'qotgan. lex.uz: {note[:140]}", False)

    for f in report["flags"]:
        for c in f.get("citations") or []:
            unit = law.get_unit(c["act_id"], c["article"], c["on_date"]) if law is not None and c.get("act_id") else None
            good = bool(unit) and (not c.get("quote") or _verbatim(c["quote"], unit["text"]))
            _step(steps, "verify_quote", f"{f['check']} → {c.get('act_id')} {c.get('article')} · {c.get('on_date')}",
                  "iqtibos shu tahrirda aynan bor" if good else "tasdiqlanmadi: belgi ekspertga", good)

    open_qs: list[dict] = []
    if text and law is not None:
        query = " ".join(_subject(d.get("title") or "").split()[:6])
        norms = [u for u in law.search(query, on, k=k + 6) if u["act_key"] not in NOISE_ACTS][:k] if query else []
        _step(steps, "search_law", f"\"{query[:60]}\" · {on}",
              "; ".join(f"{u['act_key']} {u['path']}" for u in norms) or "mos norma topilmadi", bool(norms))
        clauses = (preamble(text) and text[len(preamble(text)):]) or text
        for u in norms:
            q = {"norm": f"{u['act_key']} {u['path']}", "url": u.get("url", ""), "status": "ekspert ko'radi"}
            if use_llm:
                try:
                    a = llm.chat_json(LLM_SYSTEM, f"QAROR ({on}):\n{clauses[:6000]}\n\nQONUN ({u['act_key']} "
                                      f"{u['path']}, {u['edition']} tahriri):\n{u['text'][:3000]}")
                    both = _verbatim(a.get("decision_quote", ""), text) and _verbatim(a.get("law_quote", ""), u["text"])
                    q["status"] = a.get("verdict", "unclear") if both else "unclear (iqtibos tasdiqlanmadi)"
                    q["why"] = a.get("why", "")
                    _step(steps, "llm", q["norm"], q["status"], both)
                except llm.LLMUnavailable:
                    use_llm = False
                    _step(steps, "llm", "Qwen (box)", "o'chiq: ochiq savollar ekspertga beriladi", False)
            open_qs.append(q)

    _step(steps, "conclusion", report["verdict"],
          f"{len(report['flags'])} ta belgi; {len(open_qs)} ta ochiq savol; har bir belgini ekspert hal qiladi")
    return {"reg_number": d.get("reg_number", ""), "verdict": report["verdict"], "steps": steps,
            "open_questions": open_qs, "llm": "on" if use_llm and any(s["tool"] == "llm" and s["ok"] for s in steps)
            else "off"}
