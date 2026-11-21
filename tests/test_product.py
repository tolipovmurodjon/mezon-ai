"""The product layer: duplicate guard, plain-language flags, the law time machine and the review endpoints."""

import pytest

from mezon.plain import explain
from mezon.rules.duplicate import _same_matter


def test_same_matter_needs_identical_subject_and_numbers():
    school = "Qarshi tumanida maktab yoshidagi bolalarni umumiy o‘rta ta’limga to‘liq qamrab olish to‘g‘risida"
    assert _same_matter({"title": school}, {"title": school})
    # successive budget reports share a template but not the period
    assert not _same_matter({"title": "Vobkent tumani mahalliy byudjetining 2025-yil I-yarim yillik ijrosi"},
                            {"title": "Vobkent tumani mahalliy byudjetining 2025-yil I chorak ijrosi"})
    # clean-up decisions look alike by template
    cleanup = "Mirishkor tuman hokimining eskirgan va o‘z ahamiyatini yo‘qotgan normativ-huquqiy tusdagi qarorlari"
    assert not _same_matter({"title": cleanup}, {"title": cleanup})


def test_explain_builds_uzbek_text_and_an_appeal_with_the_law_quote():
    flag = {"check": "R_duplicate", "title": "Near-copy of 207-4-59-Q/24, which is still in force",
            "explanation": "", "citations": [{"act_title": "NLA", "article": "art:46/part:1", "quote": "Ilgari ..."}]}
    report = {"reg_number": "231-4-59-Q/24", "body": "Qarshi tumani hokimi", "date": "2024-06-21", "title": "X"}
    out = explain(flag, report)
    assert out["title_uz"].endswith("(207-4-59-Q/24)")
    assert "231-4-59-Q/24" in out["appeal_uz"] and "Ilgari ..." in out["appeal_uz"]
    assert out["channels"] and all(c["url"].startswith("https://") for c in out["channels"])


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mezon.api.main import _law, app

    if _law is None:
        pytest.skip("law store not built")
    return TestClient(app)


def test_time_machine_sees_a_repealed_article(client):
    d = client.get("/api/law", params={"act": "lsp", "path": "art:25", "on": "2024-06-21"}).json()
    assert d["then"] and d["repealed_since"]


def test_review_rejects_an_unknown_verdict(client):
    r = client.post("/api/reviews", json={"decision_id": "x", "check": "R_duplicate", "verdict": "maybe"})
    assert r.status_code == 422


@pytest.fixture(scope="module")
def law():
    from mezon.rules.run import load_law

    lw = load_law()
    if lw is None:
        pytest.skip("law store not built")
    return lw


LAND_TEXT = """QAROR
1. Fuqaro A.ga dehqon xo'jaligini yuritish uchun 0,1 gektar yer uchastkasi ajratilsin.
2. Tuman yer tuzish bo'limi ushbu qarorning bajarilishini ta'minlasin.
3. Mazkur qarorning ijrosini nazorat qilish tuman hokimi o'rinbosari zimmasiga yuklatilsin.
"""


def _decision(adopted: str, text: str = LAND_TEXT) -> dict:
    return {"type": "Q", "district": 59, "region": 4, "role": "adopted", "adopted": adopted, "text": text,
            "reg_number": "1-4-59-Q/22", "url": ""}


def test_land_rule_reads_the_edition_in_force_on_the_date(law):
    from mezon.rules import land

    assert land._revoke_banned(law, "2025-01-01") and not land._revoke_banned(law, "2026-06-01")
    flags = land.check(_decision("2022-03-01"), law)
    assert flags and flags[0].status == "possible_violation" and flags[0].citations[0].quote
    assert land.check(_decision("2021-05-01"), law) == []  # before PF-6243 took effect


def test_conclusion_draft_lists_each_defect_with_article_and_quote():
    from mezon.conclusion import draft

    report = {"reg_number": "231-4-59-Q/24", "body": "Qarshi tumani hokimi", "date": "2024-06-21", "title": "X",
              "url": "https://lex.uz/uz/docs/-6986157", "verdict": "negative", "checks_run": ["R_duplicate"],
              "flags": [{"check": "R_duplicate", "title": "Near-copy", "title_uz": "Deyarli aynan nusxa",
                         "status": "possible_violation", "evidence": [{"quote": "ro'yxati tasdiqlansin"}],
                         "citations": [{"act_title": "NLA", "article": "art:46/part:1", "on_date": "2024-06-21",
                                        "quote": "Ilgari qabul qilingan"}]}]}
    text = draft(report)
    assert "Salbiy" in text and "46-modda, 1-qism" in text and "«Ilgari qabul qilingan»" in text
    assert "(LOYIHA)" in text and "Imzo" in text


def test_budget_allocations_are_not_short_discussion_flags():
    from mezon.rules.procedure import is_budget_allocation

    assert is_budget_allocation("Shahar mahalliy budjetining qo‘shimcha manbalaridan foydalanish to‘g‘risida")
    assert is_budget_allocation("Xojeli rayonı jergilikli byudjetiniń qosımsha derekleri esabınan qarjılardı baǵdarlaw haqqında")
    assert not is_budget_allocation("Maishiy chiqindilarni olib chiqib ketish xizmati tariflarini tasdiqlash to‘g‘risida")
    assert not is_budget_allocation("Yer solig‘i bo‘yicha koeffitsiyentlarni belgilash to‘g‘risida")


def test_job_quota_is_needs_expert_not_high_confidence():
    from mezon.rules.business import JOB_QUOTA
    from research.textnorm import fold

    assert JOB_QUOTA.search(fold("Parkent tumanidagi aholining ijtimoiy ehtiyojmand toifalarini 2026-yilda ishga joylashtirish uchun ish o‘rinlari"))
    assert not JOB_QUOTA.search(fold("Maishiy chiqindilarni olib chiqib ketish tariflari to‘g‘risida"))


def test_tax_timing_rule_by_date():
    import datetime as dt

    from mezon.rules.business import _first_of_next_month

    assert _first_of_next_month(dt.date(2025, 12, 30)) == dt.date(2026, 1, 1)
    assert _first_of_next_month(dt.date(2024, 1, 31)) == dt.date(2024, 2, 1)


def test_entry_into_force_reads_yilning_dates_and_approval_day():
    import datetime as dt

    from research.regulation_window import entry_into_force

    e = entry_into_force("1. Stavkalar belgilansin. 12. Mazkur qaror 2026 yilning 1 yanvaridan kuchga kiradi.")
    assert e["kind"] == "date" and e["date"] == dt.date(2026, 1, 1)
    assert entry_into_force("1. Tariflar tasdiqlansin. 7. Ushbu qaror tasdiqlangan kundan kuchga kiradi.")["kind"] == "relative"


def test_checked_explains_silence():
    from mezon.plain import checked

    report = {"flags": [], "checks_run": ["R_form", "R_expertise", "R_business_3m+R_retroactive"]}
    rows = checked(report, "")
    assert {r["check"] for r in rows} == {"R_form", "R_expertise", "R_business_3m+R_retroactive"}
    assert all("tekshirilmadi" in r["why_uz"] for r in rows if r["check"] != "R_expertise")
    silent = checked({"flags": [], "checks_run": ["R_business_3m+R_retroactive"]},
                     "1. Chiqindi olib chiqish uchun to'lov tariflari belgilansin.")
    assert "3 oyni" in silent[0]["why_uz"]


def test_basis_reads_long_form_and_named_acts():
    from mezon.rules.basis import references

    text = ("Qarshi tuman hokimligi. Vazirlar Mahkamasining 2017-yil 15-martdagi 140-sonli qarori hamda "
            "Soliq kodeksiga asosan qaror qilaman: 1. Belgilansin.")
    nums = [n for n, _ in references(text)]
    assert "VMQ-140" in nums and "@taxcode" in nums


def test_corruption_checklist_has_29_rows_and_marks_found_factor():
    from mezon.rules.corruption import checklist, factors

    assert len(factors()) == 29
    report = {"flags": [{"check": "R_corruption_factor", "title": "Possible corruption-inducing factor 24: x",
                         "evidence": [{"locator": "clause 4", "quote": "boshqa manbalar hisobidan"}]}]}
    rows = {r["n"]: r for r in checklist(report, True)}
    assert rows[24]["answer"].startswith("bor") and rows[4]["answer"] == "aniqlanmadi"
    assert rows[10]["answer"] == "ekspert"


def test_cited_articles_keep_hyphenated_numbers_and_stop_at_next_act():
    from mezon.rules.basis import cited_articles

    text = ("Qarshi tuman hokimligi. O'zbekiston Respublikasining \u201cMahalliy davlat hokimiyati to'g'risida\u201dgi "
            "Qonunining 9- va 21-1-moddalari, \u201cDavlat mulkini boshqarish to'g'risida\u201dgi Qonunning 25-moddasiga "
            "asosan qaror qilaman: 1. Belgilansin.")
    arts = {p for k, p, _ in cited_articles(text) if k == "lsp"}
    assert arts == {"art:9", "art:21-1"}


def test_region_report_compares_with_previous_snapshot(tmp_path, monkeypatch):
    import json

    from mezon import region_report
    from mezon.version import ruleset

    snap = {"4": {"flagged": 70, "dead_article": 20, "repeats": 7}, "_ruleset": ruleset()}
    (tmp_path / "2026-11-01.json").write_text(json.dumps(snap))
    monkeypatch.setattr(region_report, "SNAPSHOTS", tmp_path)
    items = [{"id": "x", "reg_number": "355-4-68-Q/25", "adopted": "2025-11-13", "body": "", "title": "T",
              "url": "u", "checks": ["R_basis"], "n_hard": 1}]
    page = region_report.build(4, "Qashqadaryo", items, {"x": []})
    assert "2026-11-01 holatiga nisbatan" in page
    assert "(o'tgan safar 20 ta, -19)" in page


def test_region_report_says_why_a_decision_left_the_list(tmp_path, monkeypatch):
    import json

    from mezon import region_report
    from mezon.version import ruleset

    prev = {"4": {"flagged": 2, "dead_article": 1, "repeats": 0, "ids": {"flagged": ["a", "b"]}}, "_ruleset": ruleset()}
    (tmp_path / "2026-11-01.json").write_text(json.dumps(prev))
    monkeypatch.setattr(region_report, "SNAPSHOTS", tmp_path)
    items = [{"id": "a", "reg_number": "A-1", "adopted": "2025", "body": "x", "url": "u", "checks": [], "n_hard": 0}]
    lookup = {"b": {"reg_number": "B-2", "lost_force": "2026-11-10"}}.get
    page = region_report.build(4, "Qashqadaryo", items, {"a": []}, lookup)
    assert "6. O'tgan safardan beri" in page and "B-2: kuchini yo'qotgan (2026-11-10, lex.uz)" in page



def test_region_report_refuses_to_compare_across_rule_versions(tmp_path, monkeypatch):
    import json

    from mezon import region_report

    (tmp_path / "2026-11-01.json").write_text(json.dumps({"4": {"flagged": 99}, "_ruleset": "old"}))
    monkeypatch.setattr(region_report, "SNAPSHOTS", tmp_path)
    page = region_report.build(4, "Qashqadaryo", [], {})
    assert "boshqa qoidalar versiyasi" in page and "o'tgan safar" not in page


def test_conclusion_records_rules_version_and_text_hash():
    from mezon.conclusion import draft

    base = {"reg_number": "1-1-1-Q/25", "title": "T", "body": "B", "date": "2025-01-01", "verdict": "positive",
            "flags": [], "checks_run": [], "ruleset": "abc12345 (qonun bazasi 2026-11-12)", "url": "https://lex.uz/x"}
    with_text = draft({**base, "text_sha": "4a52504176f63ca3"})
    assert "abc12345" in with_text and "sha256 4a52504176f63ca3" in with_text
    assert "faqat E-qaror bosqichlari" in draft({**base, "text_sha": ""})


def test_conclusion_states_when_lexuz_status_was_checked():
    from mezon.conclusion import draft

    base = {"reg_number": "1-1-1-Q/25", "title": "T", "body": "B", "date": "2025-01-01", "verdict": "positive",
            "flags": [], "checks_run": [], "ruleset": "v", "url": "u", "text_sha": ""}
    assert "lex.uz holati tekshirilgan: 2026-11-19" in draft({**base, "lexuz_checked": "2026-11-19"})
    lost = draft({**base, "lexuz_checked": "2026-11-19", "lexuz_status": "lost force (lex.uz), store says in force"})
    assert "o'z kuchini yo'qotgan" in lost
    assert "hali qayta tekshirilmagan" in draft(base)


def test_freshness_writes_each_row_and_resumes(tmp_path, monkeypatch):
    import csv

    from research import freshness

    ds = [{"reg_number": f"{n}-4-1-Q/25", "region": 4, "url": f"https://lex.uz/uz/docs/-{n}"} for n in (1, 2, 3)]
    ds.append({"reg_number": "9-6-1-Q/25", "region": 6, "url": "https://lex.uz/uz/docs/-9"})
    monkeypatch.setattr(freshness, "DecisionStore", lambda: None)
    monkeypatch.setattr(freshness, "flagged_lexuz", lambda store: ds)
    seen = []
    monkeypatch.setattr(freshness, "check_one", lambda d, today: seen.append(d["reg_number"]) or
                        {"reg_number": d["reg_number"], "status": "unchanged", "detail": "", "url": d["url"]})
    out = tmp_path / "fresh.csv"
    freshness.main(limit=2, region=4, out=out)          # stopped after two
    freshness.main(region=4, out=out)                   # resumes with the third only
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert [r["reg_number"] for r in rows] == ["1-4-1-Q/25", "2-4-1-Q/25", "3-4-1-Q/25"]
    assert seen == ["1-4-1-Q/25", "2-4-1-Q/25", "3-4-1-Q/25"]   # nothing checked twice, other region untouched


def test_agent_trace_marks_dead_article_and_llm_off(monkeypatch):
    import pytest

    from mezon import llm
    from mezon.agent import run
    from mezon.decisions.store import DecisionStore
    from mezon.rules.run import load_law

    s, law = DecisionStore(), load_law()
    ids = s.by_reg("355-4-68-Q/25")
    if not ids or law is None:
        pytest.skip("store not built")

    def off(*a, **k):
        raise llm.LLMUnavailable("box off")

    monkeypatch.setattr(llm, "chat_json", off)
    r = run(ids[0], law, s)
    tools = [st["tool"] for st in r["steps"]]
    assert tools[0] == "decision_text" and tools[-1] == "conclusion" and "rules" in tools
    dead = [st for st in r["steps"] if st["tool"] == "law" and "art:25" in st["args"]]
    assert dead and not dead[0]["ok"] and "O" in dead[0]["result"] and "976" in dead[0]["result"]
    assert all(st["ok"] for st in r["steps"] if st["tool"] == "verify_quote")


def test_edition_gap_is_reported_for_skipped_tax_code_editions():
    import pytest

    from mezon.rules.run import load_law

    law = load_law()
    if law is None or not law.editions("taxcode"):
        pytest.skip("law store not built")
    assert law.edition_gap("taxcode", "2025-01-18") == ("2020-01-01", "2025-06-17")
    assert law.edition_gap("taxcode", "2026-01-05") is None


def test_quiet_period_is_not_an_edition_gap():
    import pytest

    from mezon.rules.run import load_law

    law = load_law()
    if law is None or not law.editions("lsp"):
        pytest.skip("law store not built")
    assert law.edition_gap("lsp", "2025-01-18") is None   # LSP simply was not amended 19.10.2024 - 01.05.2026


def test_ask_answers_for_citizen_and_expert():
    import pytest

    from mezon.api import main

    if not main._decisions.by_reg("355-4-68-Q/25"):
        pytest.skip("store not built")
    c = main.ask("355-4-68-Q/25 menga nima degani?", "citizen")
    assert c["found"] == "355-4-68-Q/25" and c["steps"][0]["tool"] == "decision_text"
    assert c["blocks"] and c["blocks"][0]["plain"] and c["blocks"][0]["channels"]
    e = main.ask("355-4-68-Q/25", "expert")
    assert "plain" not in e["blocks"][0] and e["conclusion"].endswith("355-4-68-Q/25")
    none = main.ask("salom", "citizen")
    assert none["found"] is None and none["suggestions"]


def test_ask_understands_intent_cyrillic_numbers_and_topics():
    import pytest

    from mezon import ask as a
    from mezon.api import main

    assert a.numbers("VII-3-1-5-77-К/25 nima degani") == ["VII-3-1-5-77-K/25"]
    assert a.intent("nega belgilandi?") == "why" and a.intent("qayerga murojaat qilay") == "action"
    assert a.intent("menga nima degani") == "meaning"
    if not main._decisions.by_reg("355-4-68-Q/25"):
        pytest.skip("store not built")
    r = main.ask("355-4-68-Q/25 nega belgilandi?", "expert")
    assert r["lead"].startswith("Belgilanish sababi") and "18-modda" in r["lead"] and "art:" not in r["lead"]
    t = main.ask("Yakkabog maktab", "citizen")
    assert t["found"] is None and all("Yakkabog" in m["title"] for m in t["matches"])


def test_law_changes_lists_only_decisions_still_in_force():
    import pytest

    from mezon.api import main

    r = main.law_changes(since="2024-01-01", limit=200)
    if not r["total"]:
        pytest.skip("no impact data")
    for i in r["items"]:
        d = main._decisions.get(main._decisions.by_reg(i["reg_number"])[0])
        assert not d.get("lost_force") and d.get("label") in (None, "", "none")
        assert i["articles"].endswith("-modda") and i["status"] in ("reworded", "removed")


def test_linguistic_finds_mixed_script_words_only():
    from mezon.rules.linguistic import mixed_words

    hits = mixed_words("Qaror TАRKIBI va JАDVАLI; Аholini ro'yxati. VII-son, toza matn.")
    assert [h["word"] for h in hits] == ["TАRKIBI", "JАDVАLI", "Аholini"]
    assert hits[0]["fixed"] == "TARKIBI" and hits[2]["fixed"] == "Aholini"
    assert mixed_words("Butunlay lotin matn. Бутунлай кирилл матн.") == []


def test_conclusion_opens_in_word():
    import pytest

    from mezon.api import main

    if not main._decisions.by_reg("355-4-68-Q/25"):
        pytest.skip("store not built")
    r = main.conclusion_word("355-4-68-Q/25")
    assert r.media_type == "application/msword" and "Mezon_xulosa_355-4-68-Q_25.doc" in r.headers["content-disposition"]
    body = r.body.decode("utf-8")
    assert "Times New Roman" in body and "&lt;" not in body[:0] and "<p>" in body


def test_citizen_lead_names_the_decisions_own_problem():
    import pytest

    from mezon.api import main

    if not main._decisions.by_reg("355-4-68-Q/25"):
        pytest.skip("store not built")
    lead = main.ask("355-4-68-Q/25 menga nima degani", "citizen")["lead"]
    assert "25-moddasiga tayanadi" in lead and "976" in lead
    assert main.ask("VII-3-1-5-77-K/25", "business")["lead"].startswith("Bu qarorda:")


def test_review_page_saves_reviewer_and_group_answers_in_a_temp_db(client, tmp_path, monkeypatch):
    """The lawyers' /review page: sheet loads, a verdict keeps the reviewer, group answers save. Never the real DB."""
    from mezon.api import main

    monkeypatch.setattr(main, "REVIEWS_DB", tmp_path / "reviews.sqlite")
    c = client
    assert c.get("/review").status_code == 200
    sheet = c.get("/api/review-sheet").json()
    assert len(sheet["flags"]) == 60 and len(sheet["groups"]) == 5
    f = next(x for x in sheet["flags"] if x["decision_id"])
    r = c.post("/api/reviews", json={"decision_id": f["decision_id"], "check": f["check"], "verdict": "correct",
                                     "reviewer": "Asila"})
    assert r.status_code == 200
    assert c.get("/api/reviews").json()["total"]["correct"] == 1
    assert c.post("/api/group-answers", json={"question": 1, "reviewer": "Asila", "answer": "depends",
                                              "note": "VMQ-965"}).status_code == 200
    assert c.get("/api/review-sheet").json()["answers"][0]["answer"] == "depends"
    assert c.post("/api/group-answers", json={"question": 1, "reviewer": "Asila", "answer": "maybe"}).status_code == 422
