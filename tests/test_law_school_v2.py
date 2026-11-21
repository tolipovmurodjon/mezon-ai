"""Law school v2 builder: leak control, balance, caps, per-act cap, add-only rounds (pure functions, no refinery data)."""
import gzip
import json
import random
from collections import Counter

from research import law_school_v2 as ls


def _item(t, tpl, ans, cls="", lang="lat"):
    return {"t": t, "tpl": tpl, "ans": ans, "cls": cls, "txt": f"S: q\nJ: {ans}"}


def _row(i, items, act="x", lang="lat"):
    return {"act": act, "lex_id": act, "path": f"art:{i}", "root": f"art:{i}", "vf": "2020-01-01", "lang": lang, "view": 0, "items": items, "head": "h"}


def test_root_of():
    assert ls.root_of("art:5/part:2") == "art:5"
    assert ls.root_of("annex:1/cl:3") == "annex:1"


def test_exam_exclusion_covers_twin_scripts_and_p3_rows():
    ex = {("5378966", "art:12"), ("nla", "art:12")}
    keep = ls.make_keep(ex, {"5378966", "nla"})
    assert not keep({"act": "nla", "lex_id": "-5378966", "root": "art:12"})      # Latin, store key
    assert not keep({"act": "5378966", "lex_id": "5378966", "root": "art:12"})   # Cyrillic twin, same unsigned id
    assert keep({"act": "nla", "lex_id": "-5378966", "root": "art:13"})
    assert not keep({"act": "x", "lex_id": "-5378966", "roots": ["art:3", "art:12"]})   # raw chunk containing the article
    assert not keep({"act": "x", "lex_id": "5378966", "roots": []})   # no roots on an exam act: dropped whole
    assert keep({"act": "x", "lex_id": "999", "roots": []})
    assert keep({"act": "hier", "lex_id": "5378966", "root": ""})


def test_enforce_balance_template_and_answer_caps():
    rng = random.Random(1)
    rows = []
    for i in range(3000):
        its = [_item("inforce", f"inforce:{rng.randrange(60)}", "Ha" if rng.random() < 0.8 else "Yo'q", cls="Ha"),
               _item("cloze", f"cloze:{rng.randrange(60)}", "degan soz bilan" if rng.random() < 0.3 else f"ans{i}"),
               _item("since", f"since:{rng.randrange(60)}", f"d{i}"),
               _item("tf", f"tf:{rng.randrange(60)}", "To'g'ri", cls="To'g'ri")]
        its[0]["cls"] = its[0]["ans"].split(":")[0]
        rows.append(_row(i, its))
    rep: dict = {}
    out = ls.enforce(rows, rep)
    items = [it for r in out for it in r["items"]]
    c = Counter(i["cls"] for i in items if i["t"] == "inforce")
    assert 0.45 <= c["Ha"] / sum(c.values()) <= 0.55
    for typ in ("inforce", "cloze", "since"):
        t = Counter(i["tpl"] for i in items if i["t"] == typ)
        assert max(t.values()) / sum(t.values()) <= 0.03 + 0.005
    ans = Counter(i["ans"] for i in items if not i["cls"])
    assert max(ans.values()) / len(items) <= 0.0051
    assert rep["enforce_drops"]["balance"] > 0


def test_prefilter_caps_per_root_and_per_act(tmp_path):
    f = tmp_path / "l.jsonl.gz"
    rows = []
    for act, n_roots in (("big", 1), ("small", 5)):
        for root in range(n_roots):
            for k in range(50):   # 50 lessons for the same root (editions x views)
                rows.append({"act": act, "lex_id": act, "path": f"art:{root}/part:{k}", "root": f"art:{root}", "vf": f"2020-01-{k % 28 + 1:02d}",
                             "lang": "lat", "view": k, "items": [], "head": "x" * 100, "text": "x" * 100})
    with gzip.open(f, "wt", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    rep: dict = {}
    out = ls.prefilter([f], lambda r: True, set(), ls.lesson_prio, 6, None, rep, "lessons")
    per = Counter((r["act"], r["root"]) for r in out)
    assert max(per.values()) == 6
    out2 = ls.prefilter([f], lambda r: True, set(), ls.lesson_prio, 6, 400, rep, "lessons")
    by_act = Counter(r["act"] for r in out2)
    assert by_act["small"] <= 4 and by_act["big"] <= 4   # 400 chars cap per act, each row 100 chars
    # rows written earlier are never offered again
    used = {ls.row_key("lessons", r) for r in out}
    again = ls.prefilter([f], lambda r: True, used, ls.lesson_prio, 6, None, rep, "lessons")
    assert not ({ls.row_key("lessons", r) for r in again} & used)


def test_lesson_row_balanced_classes_and_no_leak_of_placeholders():
    u = {"type": "law", "title": "Test qonun", "number": "O'RQ-1", "act_key": "t", "lex_id": "1", "path": "art:3/part:1", "valid_from": "2020-01-01",
         "valid_to": "2022-01-01", "text": "Fuqarolar o'z huquqlarini sud orqali himoya qilish huquqiga ega bo'lib, bu huquq hech qanday shart bilan cheklanmaydi. "
                                          "Davlat organlari ushbu huquqning amalga oshirilishini ta'minlashi shart va javobgar bo'ladi.", "heading": "H"}
    got = Counter()
    for k in range(300):
        u2 = {**u, "path": f"art:{k}"}
        row = ls.lesson_row(u2, None, None, "lat", 0)
        assert row
        for it in row["items"]:
            assert "{" not in it["txt"]
            if it["t"] == "inforce":
                got[it["cls"]] += 1
    assert 0.35 <= got["Ha"] / sum(got.values()) <= 0.65   # raw generator is near 50/50; enforce() tightens to 45-55 %


def test_to_cyr_keeps_placeholders():
    assert ls.to_cyr("{a} sana") .startswith("{a}")
