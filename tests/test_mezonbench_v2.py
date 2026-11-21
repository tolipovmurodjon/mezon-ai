"""MezonBench v2: oracle, baselines, grader edge cases, disjointness from v1 and the frozen manifest."""

import json
from pathlib import Path

import pytest

from research import mezonbench_v2 as v2

BENCH = v2.OUT
needs_bench = pytest.mark.skipif(not BENCH.exists(), reason="v2 bench not built")


@needs_bench
def test_oracle_is_100_percent():
    items = v2.load(BENCH)
    assert all(v2.grade(i, v2.oracle_answer(i)) == "right" for i in items)


@needs_bench
def test_noaniq_only_and_constant_answers_are_low():
    items = v2.load(BENCH)
    share = sum(i["family"] == "noaniq" for i in items) / len(items)
    assert 0.12 <= share <= 0.20
    got = sum(v2.grade(i, "noaniq") == "right" for i in items) / len(items)
    assert abs(got - share) < 1e-9
    base = v2.baselines(items)
    assert base["ALL"]["acc"] < 0.40  # best constant per family stays far below any real model
    for fam in ("ask_noaddr", "conflict_pair", "multi_hop"):
        assert base[fam]["acc"] == 0.0


@needs_bench
def test_binary_families_are_balanced():
    items = v2.load(BENCH)
    for fam in ("chain", "dead_cite"):
        c = [i["verdict"] for i in items if i["family"] == fam]
        assert abs(c.count("ha") - c.count("yo'q")) <= 2
    c = [i["verdict"] for i in items if i["family"] == "conflict_pair"]
    assert abs(c.count("A") - c.count("B")) <= 4


@needs_bench
def test_no_golden_case_and_no_internship_decision():
    text = BENCH.read_text(encoding="utf-8")
    for reg in v2.GOLDEN:
        assert reg not in text


@needs_bench
def test_strict_items_disjoint_from_v1():
    root = Path(__file__).resolve().parents[1]
    used = set()
    for f in v2.USED_FILES:
        p = root / f
        if p.exists():
            for line in p.open(encoding="utf-8"):
                j = json.loads(line)
                if j.get("act") and j.get("path"):
                    used.add((j["act"], j["path"]))
    for i in v2.load(BENCH):
        if i.get("act") and i.get("path") and not i.get("overlap_v1"):
            assert (i["act"], i["path"]) not in used, i["id"]


def test_dead_cite_needs_the_date():
    item = {"family": "dead_cite", "verdict": "yo'q", "gold_date": "2024-10-19"}
    assert v2.grade(item, "yo'q, 2024-10-19") == "right"
    assert v2.grade(item, "Yo'q. 19.10.2024 kuni kuchini yo'qotgan") == "right"
    assert v2.grade(item, "yo'q") == "wrong"
    assert v2.grade(item, "ha, 2024-10-19") == "wrong"
    assert v2.grade(item, "noaniq") == "abstain"


def test_noaniq_items_reward_only_abstention():
    item = {"family": "noaniq"}
    assert v2.grade(item, "noaniq, ekspert kerak") == "right"
    assert v2.grade(item, "ha") == "wrong"


def test_russian_and_cyrillic_verdicts():
    item = {"family": "ru_cyr", "task": "in_force", "verdict": "yo'q"}
    assert v2.grade(item, "Нет, не действовала") == "right"
    assert v2.grade(item, "йўқ") == "right"
    assert v2.grade(item, "да") == "wrong"
    h = {"family": "ru_cyr", "task": "hierarchy", "verdict": "B"}
    assert v2.grade(h, "В") == "right"


def test_lat2cyr():
    assert v2.lat2cyr("o'q") == "ўқ"
    assert v2.lat2cyr("qonun") == "қонун"


def test_frozen_manifest_matches_files():
    man = v2.FROZEN
    if not man.exists():
        pytest.skip("not frozen yet")
    m = json.loads(man.read_text(encoding="utf-8"))
    assert m["items"][BENCH.name]["sha256_16"] == v2.sha(BENCH)


def test_citation_parser_reads_dropped_superscripts():
    from mezon.rules.basis import cited_articles, split_article_numbers

    have = {("lsp", "art:16-2")}
    ex = lambda k, p: (k, p) in have
    assert split_article_numbers("16 2", "lsp", ex) == ["16-2"]
    assert split_article_numbers("16-2", "lsp", ex) == ["16-2"]
    assert split_article_numbers("16 2", "lsp", None) == ["16", "2"]  # no store: never merge
    assert split_article_numbers("16 2", "lsp", lambda k, p: False) == ["16", "2"]  # merged article must exist
    assert split_article_numbers("16, 24", "lsp", ex) == ["16", "24"]  # a real list stays a list
    text = ("QAROR O'zbekiston Respublikasi “Mahalliy davlat hokimiyati to'g'risida”gi Qonunining 16 2 , "
            "24-moddalari asosan, qaror qiladi: 1. Tasdiqlansin.")
    got = {p for k, p, _ in cited_articles(text, exists=ex) if k == "lsp"}
    assert "art:16-2" in got and "art:2" not in got and "art:16" not in got
    sup = text.replace("16 2 ,", "16²,")
    assert "art:16-2" in {p for k, p, _ in cited_articles(sup, exists=ex) if k == "lsp"}
    hy = text.replace("16 2 ,", "16-2,")
    assert "art:16-2" in {p for k, p, _ in cited_articles(hy, exists=ex) if k == "lsp"}


def test_evidence_finds_superscript_article():
    s = "Qonunining 16 2 , 24-moddalari asosan"
    assert "16 2" in v2.evidence(s, "16-2")
    assert v2.evidence("Qonunining 16 2 moddasi", "2") is None


def test_ask_noaddr_rejects_pronoun_stems_and_garbled_modals():
    assert v2.ANAPHOR_OR_ADDRESS.search("bunday yerlarda mahsulot yetishtirish taqiqlanadi")
    assert v2.ANAPHOR_OR_ADDRESS.search("ushbu Kodeksda belgilangan tartibda")
    assert not v2.ANAPHOR_OR_ADDRESS.search("tadbirkor soliq to'lashi shart")
    s = "servitut kimning manfaatlarini ko'zlab belgilangan bo'lsa, o'sha shaxs qonunda yoki shartnomada shart"
    assert v2.Builder.modal(s) == ("qoida", s)  # "majbur/shart" no longer cuts the stem
    kind, stem = v2.Builder.modal("Savdo qoidalarini buzgan holda tovar sotish ruxsat etilmaydi")
    assert kind == "taqiq" and stem.endswith("tovar sotish")


def test_split_is_seeded_stratified_and_30_percent_per_family():
    items = []
    for fam, n in (("chain", 60), ("dead_cite", 60), ("noaniq", 75)):
        for k in range(n):
            items.append({"id": f"{fam}-{k:03d}", "family": fam, "verdict": "ha" if k % 2 else "yo'q"})
    pub, priv = v2.split_items(items)
    assert (pub, priv) == v2.split_items(items)  # deterministic
    assert {i["id"] for i in pub}.isdisjoint(i["id"] for i in priv) and len(pub) + len(priv) == len(items)
    for fam, n in (("chain", 60), ("dead_cite", 60), ("noaniq", 75)):
        got = [i for i in priv if i["family"] == fam]
        assert len(got) == round(0.3 * n)
    c = [i["verdict"] for i in priv if i["family"] == "chain"]
    assert abs(c.count("ha") - c.count("yo'q")) <= 1  # stratified by gold
    assert all(i["split"] == "private" for i in priv) and all(i["split"] == "public" for i in pub)


V21 = v2.OUT_V21
needs_v21 = pytest.mark.skipif(not (V21.exists() and v2.PRIVATE_V21.exists()), reason="v2.1 not built")


@needs_v21
def test_v21_oracle_100_percent_on_public_private_both():
    for part in ("public", "private", "both"):
        items = v2.load_split(part)
        assert items and all(v2.grade(i, v2.oracle_answer(i)) == "right" for i in items)
    pub, priv = v2.load_split("public"), v2.load_split("private")
    assert {i["id"] for i in pub}.isdisjoint(i["id"] for i in priv)
    assert not {i["prompt"] for i in pub} & {i["prompt"] for i in priv}


@needs_v21
def test_v21_no_golden_no_pronoun_stems_and_parts_ok():
    text = V21.read_text(encoding="utf-8") + v2.PRIVATE_V21.read_text(encoding="utf-8")
    for reg in v2.GOLDEN:
        assert reg not in text
    for i in v2.load_split("both"):
        if i["family"] == "ask_noaddr":
            assert not v2.ANAPHOR.search(i["prompt"].split("\n")[0]), i["id"]
            assert i["kind"] in ("taqiq", "qoida")
