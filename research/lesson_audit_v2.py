"""Independent audit of law-school v2 lessons against the LawStore (does not import research.law_school_v2).

Usage: python -X utf8 -m research.lesson_audit_v2 OUT.json FILE.jsonl [FILE.jsonl ...]
Each lesson is parsed from its text only; every verdict, date and quote is re-derived with mezon.tools
(law_as_of / verify_quote) on the LawStore. Lessons whose act is not in the store are 'uncheckable'.
"""
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

from mezon import tools
from mezon.lawstore.store import LawStore
from research.textnorm import fold

ISO = r"\d{4}-\d{2}-\d{2}"
LAB = r"(?:Savol|S|So'rov|Савол|С|Сўров|Вопрос|В|Запрос)"
ALAB = r"(?:Javob|J|Natija|Жавоб|Ж|Натижа|Ответ|О|Результат)"
WORDS = {"modda": "art", "qism": "part", "band": "cl", "ilova": "annex", "bob": "ch", "bo'lim": "sec",
         "kichik band": "sub", "kirish qismi": "pre"}


def n_(s):
    return re.sub(r"\s+", " ", fold(s)).strip()


def parse_head(h):
    first = h.split("\n\n")[0]
    m = re.match(r"^(«.*?») \(([^()]*)\), (.+)$", first, re.S)
    if not m:
        return None
    where = m.group(3).replace("’", "'")
    pm = re.match(r"^((?:\d+(?:-\d+)?-(?:modda|qism|band|ilova|bob|bo'lim|kichik band|kirish qismi)(?=[ .:,]|$) ?)+)", where)
    return m.group(1)[1:-1], m.group(2), where, pm.group(1).strip() if pm else None


def path_of(pstr):
    return "/".join(f"{WORDS[t[1]]}:{t[0]}" for t in re.findall(
        r"(\d+(?:-\d+)?)-(modda|qism|band|ilova|bob|bo'lim|kichik band|kirish qismi)", pstr))


def items(text):
    out = []
    for p in text.split("\n\n")[1:]:
        m = re.match(rf"^{LAB}: (.*?)\n{ALAB}: (.*)$", p, re.S)
        out.append(("qa", m.group(1), m.group(2)) if m else ("raw", p, None))
    return out


FLOOR = {}


def floor(law, act):
    if act not in FLOOR:
        FLOOR[act] = law.editions(act)[0]["valid_from"]
    return FLOOR[act]


def stat(law, act, path, d):
    r = tools.law_as_of(law, act, path, d)
    return r if "text" in r else None


def has(law, act, path, d, q):
    r = tools.verify_quote(law, act, path, d, q)
    if not r.get("ok") and "edition" not in r:
        return None
    return bool(r.get("ok"))


def quotes(q, title):
    return [x for x in re.findall(r"«(.*?)»", q, re.S) if n_(x) != n_(title)]


def prevday(d):
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


def classify(law, act, path, vf, k, q, a, title):
    if k == "raw":
        m = re.search(ISO, q.split("\n")[0])
        body = q.split("\n", 1)[1] if "\n" in q else ""
        if not m or not body.strip():
            return "verbatim", "uncheckable", "parse"
        d = m.group(0)
        r = stat(law, act, path, d)
        if r is None:
            return "verbatim", "uncheckable", "no unit at date"
        b = body.removesuffix(" ...").strip()
        if not n_(r["text"]).startswith(n_(b)):
            return "verbatim", "wrong", "body differs from store text at " + d
        if r["valid_from"] != d:
            return "verbatim", "wrong", f"stated from {d} but store unit valid_from {r['valid_from']}"
        return "verbatim", "correct", ""
    a = a.strip()
    qs = quotes(q, title)
    dates = re.findall(ISO, q)
    if re.fullmatch(ISO, a):  # since
        if not qs:
            return "since", "uncheckable", "parse"
        s = qs[-1]
        ok = has(law, act, path, a, s)
        if ok is None:
            return "since", "uncheckable", "no unit"
        if not ok:
            return "since", "wrong", f"quote not verbatim in edition {a}"
        r = stat(law, act, path, a)
        if r["valid_from"] != a:
            return "since", "wrong", f"unit valid_from is {r['valid_from']}"
        if has(law, act, path, prevday(a), s):
            return "since", "wrong", f"same sentence already in force on {prevday(a)}: unchanged, so {a} is not when it began"
        return "since", "correct", ""
    mm = re.match(r"^(Ha|Yo'q|Ҳа|Йўқ|Да|Нет):\s*(.*)$", a, re.S)
    if mm:  # inforce
        if not qs or not dates:
            return "inforce", "uncheckable", "parse"
        s, d = qs[-1], dates[-1]
        ok = has(law, act, path, d, s)
        if ok is None:
            return "inforce", "uncheckable", "no unit at date (before act / article absent)"
        yes = mm.group(1) in ("Ha", "Ҳа", "Да")
        if ok != yes:
            return "inforce", "wrong", f"verdict {'yes' if yes else 'no'} but store: quote {'present' if ok else 'absent'} in edition on {d}"
        ds = re.findall(ISO, mm.group(2))
        if not ds:
            return "inforce", "uncheckable", "no date in answer"
        if yes:
            r = stat(law, act, path, d)
            if r["valid_from"] != ds[0]:
                return "inforce", "wrong", f"span start {ds[0]} != store {r['valid_from']}"
            return "inforce", "correct", ""
        sd = ds[0]
        if "keyin kuchga" in a or "позже" in a:
            r = stat(law, act, path, sd)
            if r is None or r["valid_from"] != sd or not has(law, act, path, sd, s):
                return "inforce", "wrong", f"stated start {sd} is not the start of this text in store"
        else:
            if has(law, act, path, sd, s):
                return "inforce", "wrong", f"text still in force on stated end date {sd}"
            if not has(law, act, path, prevday(sd), s):
                return "inforce", "wrong", f"text not in force the day before stated end {sd}"
        return "inforce", "correct", ""
    mm = re.match(r"^(To'g'ri|Noto'g'ri|Тўғри|Нотўғри|Верно|Неверно)\b(.*)$", a, re.S)
    if mm:  # tf
        if not qs or not dates:
            return "tf", "uncheckable", "parse"
        s, d = qs[-1], dates[-1]
        ok = has(law, act, path, d, s)
        if ok is None:
            return "tf", "uncheckable", "no unit at date"
        true = mm.group(1) in ("To'g'ri", "Тўғри", "Верно")
        if ok != true:
            return "tf", "wrong", f"verdict {'true' if true else 'false'} but quote {'present' if ok else 'absent'} in edition {d}"
        if not true:
            m2 = re.search(rf"\(({ISO})\)", a)
            if m2 and not has(law, act, path, m2.group(1), s):
                return "tf", "wrong", f"claimed previous edition {m2.group(1)} lacks the quote"
        return "tf", "correct", ""
    if "→" in a and a.startswith("«"):  # change
        m = re.match(r"^«(.*?)» → «(.*)»$", a, re.S)
        if not m or len(dates) < 2:
            return "change", "uncheckable", "parse"
        o, n = m.group(1), m.group(2)
        d0, d1 = dates[0], dates[1]
        r0, r1 = stat(law, act, path, d0), stat(law, act, path, d1)
        if r0 is None or r1 is None:
            return "change", "uncheckable", "no unit"
        bad = []
        if o != "—" and n_(o).rstrip(". ") not in n_(r0["text"]):
            bad.append(f"old fragment not in {d0}")
        if n != "—" and n_(n).rstrip(". ") not in n_(r1["text"]):
            bad.append(f"new fragment not in {d1}")
        if r1["valid_from"] != d1:
            bad.append(f"d1 {d1} is not unit start ({r1['valid_from']})")
        if n_(o).rstrip(". ") in n_(r1["text"]) and o != "—":
            bad.append("old fragment still in new text")
        return "change", ("wrong" if bad else "correct"), "; ".join(bad)
    if "____" in q:  # cloze
        mq = re.search(r"«([^«]*____.*?)»", q, re.S)
        if not mq or not vf:
            return "cloze", "uncheckable", "parse or no edition date"
        ok = has(law, act, path, vf, mq.group(1).replace("____", a))
        if ok is None:
            return "cloze", "uncheckable", "no unit"
        return "cloze", ("correct" if ok else "wrong"), ("" if ok else f"filled sentence not verbatim in {vf}")
    m = re.search(rf"\((?:с )?({ISO})", a)
    if m and qs:  # text2addr
        d, s = m.group(1), qs[-1]
        ok = has(law, act, path, d, s)
        if ok is None:
            return "text2addr", "uncheckable", "no unit"
        r = stat(law, act, path, d)
        if not ok:
            return "text2addr", "wrong", f"quote not in edition {d}"
        if r["valid_from"] != d:
            return "text2addr", "wrong", f"start {d} != store {r['valid_from']}"
        e = re.findall(ISO, a)
        if len(e) > 1 and r["valid_to"] != e[1]:
            return "text2addr", "wrong", f"end {e[1]} != store {r['valid_to']}"
        return "text2addr", "correct", ""
    if dates and len(a) > 40:  # addr2text
        r = stat(law, act, path, dates[-1])
        if r is None:
            return "addr2text", "uncheckable", "no unit at date"
        ok = n_(r["text"]).startswith(n_(a)[:1000]) or n_(a)[:1000] == n_(r["text"])[:1000]
        return "addr2text", ("correct" if ok else "wrong"), ("" if ok else "text differs from store")
    return "other", "uncheckable", "unclassified"


def audit_lesson(law, text, lid):
    h = parse_head(text)
    if not h:
        return [dict(lesson=lid, type="header", status="uncheckable", reason="head parse / cyrillic or russian lesson")]
    title, kind, where, pstr = h
    if not pstr:
        return [dict(lesson=lid, type="header", status="uncheckable", reason="path parse")]
    path = path_of(pstr)
    act = law.find_act(f"«{title}» ({kind})")
    if act is None or n_(law.act(act)["title"]) != n_(title):
        return [dict(lesson=lid, type="header", status="uncheckable", reason="act not in store", act=title[:70])]
    its = items(text)
    vf = next((a.strip() for k, q, a in its if k == "qa" and re.fullmatch(ISO, a.strip())), None)
    recs = []
    for k, q, a in its:
        typ, st, why = classify(law, act, path, vf, k, q, a, title)
        fl = floor(law, act)
        if st == "wrong" and any(law.edition_gap(act, d) for d in re.findall(ISO, q + " " + (a or ""))):
            st, why = "uncheckable", "store skipped editions here (edition_gap); " + why
        if st != "correct" and (any(d < fl for d in re.findall(ISO, q + " " + (a or ""))) or fl in why):
            st, why = "uncheckable", f"store history floor (first stored edition {fl}); " + why
        recs.append(dict(lesson=lid, act=act, path=path, type=typ, status=st, reason=why, q=q[:200], a=(a or "")[:200]))
    return recs


def consistency(text, lid):
    """Store-free checks on one lesson of any script: dates agree across items, verdict arithmetic, quotes inside own text."""
    its = [(q, a.strip()) for k, q, a in items(text) if k == "qa"]
    raw = [q for k, q, a in items(text) if k == "raw"]
    out, starts, ends = [], set(), set()
    body = " ".join(raw)
    nb = n_(body)
    for q, a in its:
        dq, da = re.findall(ISO, q), re.findall(ISO, a)
        m = re.match(r"^(Ha|Yo'q|Ҳа|Йўқ|Да|Нет):", a)
        if re.fullmatch(ISO, a):
            starts.add(a); typ = "since"
            ok = True
        elif m:
            typ = "inforce"
            d = dq[-1] if dq else None
            yes = m.group(1) in ("Ha", "Ҳа", "Да")
            if not d or not da:
                out.append((typ, "uncheckable", "parse")); continue
            if yes:
                starts.add(da[0]); ok = da[0] <= d <= da[1]
                if not ok: out.append((typ, "wrong", f"yes: {d} outside {da[0]}..{da[1]}")); continue
            else:
                before = re.search(r"keyin|кейин|позже", a) is not None
                ok = d < da[0] if before else d > da[0]
                if before: starts.add(da[0])
                else: ends.add(da[0])
                if not ok: out.append((typ, "wrong", f"no/{'before' if before else 'after'}: query {d} vs stated {da[0]}")); continue
        elif re.match(r"^(To'g'ri|Noto'g'ri|Тўғри|Нотўғри|Верно|Неверно)", a):
            typ = "tf"; ok = True
            if dq: starts.add(dq[-1])
            if re.search(r"oldingi|олдинги|предыдущей", a) and da and dq and not da[0] < dq[-1]:
                out.append((typ, "wrong", "previous edition date not earlier than edition date")); continue
        elif "→" in a and a.startswith("«"):
            typ = "change"
            if len(dq) >= 2 and dq[0] == dq[1]: out.append((typ, "wrong", "d0 == d1")); continue
            if len(dq) >= 2: starts.add(max(dq[:2]))
            ok = True
        elif "____" in q:
            typ = "cloze"; mq = re.search(r"«([^«]*____.*?)»", q, re.S)
            if not mq or not nb or body.rstrip().endswith("...") : out.append((typ, "uncheckable", "no full own text")); continue
            if n_(mq.group(1).replace("____", a)) in nb: out.append((typ, "correct", "")); continue
            if max([len(x) for x in raw + [a2 for q2, a2 in its]] + [0]) >= 1190:
                out.append((typ, "uncheckable", "own text truncated")); continue
            out.append((typ, "wrong", "filled cloze not in the lesson's own text")); continue
        else:
            typ = "other"; ok = True
        out.append((typ, "correct" if typ != "other" else "uncheckable", ""))
    if len(starts) > 1:
        out.append(("lesson", "wrong", f"items disagree on the edition start: {sorted(starts)}"))
    return [dict(lesson=lid, type=t, status=s, reason=w) for t, s, w in out]


def main():
    out, files = sys.argv[1], sys.argv[2:]
    law = LawStore()
    recs = []
    for f in files:
        for ln, line in enumerate(open(f, encoding="utf-8")):
            r = json.loads(line)
            if r["kind"] == "law:lessons":
                recs.extend(audit_lesson(law, r["text"], f"{Path(f).name}:{ln}"))
    cons = []
    for f in files:
        for ln, line in enumerate(open(f, encoding="utf-8")):
            r = json.loads(line)
            if r["kind"] == "law:lessons":
                cons.extend(consistency(r["text"], f"{Path(f).name}:{ln}"))
    json.dump({"store_checks": recs, "consistency": cons}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("consistency:", sorted(collections.Counter((r["type"], r["status"]) for r in cons).items()))
    for k, v in sorted(collections.Counter((r["type"], r["status"]) for r in recs).items()):
        print(k, v)


if __name__ == "__main__":
    main()
