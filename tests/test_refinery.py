"""Corpus refinery tests: extraction parity with the law store, masking, leak canary, normalisation, dedup, change notes.

Parity is checked on every core act whose page (and edition files) sits in the machine's cache: the laptop holds a few,
the box holds all of them. Nothing here touches the network."""

from pathlib import Path

import pytest

from mezon.lawstore.parse import parse_units
from research.mezonbench import unseen
from research.refinery import config, dedup, export, leak, parity, pii
from research.refinery import sources as src
from research.refinery.extract_html import assemble_text, classify_note
from research.refinery.normalize import (
    canon_apostrophes,
    detect_lang,
    fix_homoglyphs,
    normalise,
    repair_glue,
)


def _core_pages():
    """(act_key, lex_id) for core acts whose page is cached on this machine."""
    return [(k, lid) for k, lid in sorted(leak.load_core().items()) if src.doc_page(lid)[0]]


CORE = _core_pages()


@pytest.mark.skipif(not CORE, reason="no core act cached on this machine")
@pytest.mark.parametrize("key,lid", CORE, ids=[c[0] for c in CORE])
def test_unit_versions_parity_with_store(key, lid):
    """The last 8 editions keep the laptop run short; `python -m research.refinery.parity` runs them all (the box)."""
    res = parity.check(key, lid, tail=8)
    assert res and res["equal"], f"{key}: refinery unit rows differ from the store's units: {res}"
    assert res["store_rows"] > 0


@pytest.mark.skipif(not CORE, reason="no core act cached on this machine")
def test_document_order_blocks_use_parse_units_paths():
    for _key, lid in CORE[:6]:
        page = src.doc_page(lid)[0]
        act = assemble_text(page)
        units = {u.path for u in parse_units(page)}
        assert {b.path for b in act.blocks if b.path} <= units
        body = act.body
        for widget in ("Audioni tinglash", "Hujjatga taklif yuborish", "Hujjat elementidan havola olish"):
            assert widget not in body
        assert "tahririda" not in body  # inline amendment notes live in `notes`, not in the text


def test_assemble_keeps_title_headings_and_moves_notes():
    html = (
        '<div id="main_container1"><div class="ACT_FORM lx_elem"><div class="lx_elem2"><div class="lx_elem3">'
        '<span>Audioni tinglash</span></div></div><div id="1">Oʻzbekiston Respublikasining Qonuni</div></div>'
        '<div class="TEXT_HEADER_DEFAULT lx_elem"><div id="2">1-bob. Umumiy qoidalar</div></div>'
        '<div class="CLAUSE_DEFAULT lx_elem"><div id="3">25-modda. Hokim vakolatlari</div></div>'
        '<div class="ACT_TEXT lx_elem"><div id="4">Matn.</div></div>'
        '<div class="CHANGES_ORIGINS lx_no_select"><div id="5">(25-modda Oʻzbekiston Respublikasining 2024-yil '
        '17-oktabrdagi OʻRQ-976-sonli <a href="/uz/docs/-7162473?ONDATE=19.10.2024 01#-1">Qonuniga </a>asosan '
        "oʻz kuchini yoʻqotgan — Qonunchilik maʼlumotlari milliy bazasi)</div></div></div>"
    )
    act = assemble_text(html)
    assert [b.kind for b in act.blocks] == ["form", "heading", "article", "text"]
    assert "Audioni" not in act.body and "1-bob. Umumiy qoidalar" in act.body
    assert len(act.notes) == 1 and act.notes[0].kind == "lost_force"
    assert act.notes[0].dates == ["2024-10-19"] and act.notes[0].act_ids == ["-7162473"]
    assert act.notes[0].target.startswith("25-modda")


def test_note_classes_cover_lost_force_renumbering_and_moves():
    assert (
        classify_note("(25-modda OʻRQ-976-sonli Qonuniga asosan oʻz kuchini yoʻqotgan — x)")["kind"]
        == "lost_force"
    )
    assert (
        classify_note("(2-modda Qonuniga asosan uchinchi qismi bilan toʻldirilgan — x)")["kind"]
        == "supplemented"
    )
    assert classify_note("(1-moddaning birinchi qismi Qonuni tahririda — x)")["kind"] == "edited"
    assert classify_note("(10-modda Qonuniga asosan 11-modda deb hisoblansin — x)")["kind"] == "renumbered"
    assert classify_note("(7-modda Qonuniga asosan 21-1-moddaga koʻchirilgan — x)")["kind"] == "moved"
    assert classify_note("(часть третья статьи 40 в редакции Закона)")["kind"] == "edited"


# ------------------------------------------------------------------ normalisation


def test_apostrophes_homoglyphs_glue_and_script_kept():
    assert canon_apostrophes("to'g'risida G‘uzor ma'lumot maʻlumot") == "toʻgʻrisida Gʻuzor maʼlumot maʼlumot"
    fixed, n = fix_homoglyphs("Tovarlarni imроrt qilish")  # Cyrillic р and о inside a Latin word
    assert n == 1 and "import" in fixed
    assert repair_glue("boʻlimining2022") == "boʻlimining 2022"
    cyr = "Ўзбекистон Республикасининг қонуни"
    assert normalise(cyr)[0] == cyr  # script and letters untouched
    assert detect_lang(cyr) == {"lang": "uz", "script": "Cyrl", "lang_conf": "cyrl+uz_letters"}
    assert detect_lang("Закон Республики Узбекистан об образовании")["lang"] == "ru"


# ------------------------------------------------------------------ masking


def test_masking_citizens_only_stable_tokens():
    text = (
        "Fuqaro Karimov Aziz Rustamovich 1990-yilda yashaydi. Tel: +998 90 123 45 67, pasport AA1234567, "
        "PINFL 12345678901234. Kadastr 12:34:56:78:90:1234. Manzil: Nurafshon k., 15-uy.\x00"
        "Karimova Dilnoza Alisher qizi. Fuqaro Karimov Aziz Rustamovich qayta murojaat qildi.\x00"
        "Tuman hokimi A. Karimov ishtirok etdi.\x00Hokim Z. ALIKULOV"
    )
    out, counts = pii.mask(text, "local")
    for secret in (
        "Rustamovich",
        "Dilnoza",
        "+998",
        "AA1234567",
        "12345678901234",
        "12:34:56:78:90:1234",
        "15-uy",
    ):
        assert secret not in out
    assert out.count("[FUQARO_2]") == 2 and "[FUQARO_1]" in out  # same person, same token inside one document
    assert "[TELEFON]" in out and "[KADASTR]" in out and "[MANZIL]" in out
    assert "Tuman hokimi A. Karimov" in out and "Hokim Z. ALIKULOV" in out  # officials stay
    assert counts["name_patronymic"] >= 1 and all(isinstance(v, int) for v in counts.values())
    assert "Karimov" not in str(counts)  # the report holds counts only


def test_national_level_keeps_names_masks_numbers():
    out, counts = pii.mask(
        "Prezident Sh. Mirziyoyev imzoladi. Aloqa: +998 71 200 00 00. Fuqaro Karimov Aziz.", "national"
    )
    assert "Mirziyoyev" in out and "+998" not in out and "Karimov" in out
    assert set(counts) <= {"phone"}


def test_second_pass_flags_guardianship_residue():
    sp = pii.second_pass("Vasiylik toʻgʻrisida. Telefon +998 90 111 22 33.", "local", "", None)
    assert sp["guardianship"] and sp["exclude"]
    assert not pii.second_pass("Oddiy qaror matni. [FUQARO_1] [TELEFON]", "local", "", None)["exclude"]


# ------------------------------------------------------------------ leak control and the canary


def _net():
    bench = leak.load_bench()
    if not bench or not config.CORE_ACTS.exists():
        pytest.skip("bench or core act list not on this machine")
    return bench, leak.build_net(bench, leak.load_core(), unseen)


def test_canary_removes_all_twenty_injected_documents():
    bench, net = _net()
    res = leak.canary_test(net, bench, unseen)
    assert res["n"] == 20 and res["failed"] == 0 and res["passed"], res["results"]


def test_unit_blocklist_and_ngram_net_on_synthetic_items():
    quote = " ".join(f"soʻz{i}" for i in range(40))
    bench = [
        {
            "id": "lookup-001",
            "family": "lookup",
            "act": "nla",
            "path": "art:5/part:1",
            "answer": quote,
            "prompt": "«Qonun» art:5 holatida qanday edi?",
        }
    ]
    net = leak.build_net(bench, {"nla": "-5378966"}, lambda a, p: True)
    blocks = [
        {"kind": "article", "text": "5-modda. Sarlavha", "path": "art:5", "art": "art:5"},
        {"kind": "text", "text": quote, "path": "art:5/part:1", "art": "art:5"},
        {"kind": "text", "text": "Boshqa modda matni.", "path": "art:6/part:1", "art": "art:6"},
    ]
    res = leak.clean_blocks(blocks, net, "5378966")
    assert [b["path"] for b in res["blocks"]] == [
        "art:5",
        "art:6/part:1",
    ]  # the blocked part is gone, no marker left
    other = leak.clean_blocks(
        [{"kind": "text", "text": "Qaror. " + quote + " Kuchga kiradi.", "path": None, "art": None}],
        net,
        "999",
    )
    assert leak.survivors(" ".join(b["text"] for b in other["blocks"]), quote) == 0


def test_golden_cases_flagged_by_id_and_registration_number():
    assert leak.golden_flag("-6986157", None) == "golden"
    assert leak.golden_flag("-7026714", None) == "cancelling_act"
    assert leak.golden_flag("-1", "VII-3-1-5-77-K/25") == "golden"
    assert leak.golden_flag("-1", "1-1-1-Q/24") == "none"


# ------------------------------------------------------------------ dedup


def test_twins_and_minhash_stay_inside_strata():
    lat = "Qarshi tumanida maktab yoshidagi bolalarni umumiy oʻrta taʼlimga toʻliq qamrab olish " * 30
    cyr = "Қарши туманида мактаб ёшидаги болаларни умумий ўрта таълимга тўлиқ қамраб олиш " * 30
    assert dedup.twin_verdict(lat, cyr)[0] == "twin"
    assert dedup.twin_verdict(lat, "Soliq kodeksining 12-moddasi stavkalar " * 60)[0] == "different_acts"
    base = " ".join(f"word{i % 97}x{i}" for i in range(300))
    near = base.replace("word5x5", "changed")
    items = [
        {"id": "a", "stratum": "s1", "text": base, "adopted": "2024-01-01"},
        {"id": "b", "stratum": "s1", "text": near, "adopted": "2024-02-01"},
        {"id": "c", "stratum": "s2", "text": base, "adopted": "2024-03-01"},  # other stratum: never compared
        {
            "id": "d",
            "stratum": "s1",
            "text": " ".join(f"zzz{i}" for i in range(300)),
            "adopted": "2024-04-01",
        },
    ]
    rows = dedup.minhash_clusters(items)
    assert {r["id"] for r in rows} == {"a", "b"} and all(r["dup_count"] == 2 for r in rows)


def test_exact_groups_ignore_script_only_inside_same_language():
    g = dedup.exact_groups({"x": "Qaror matni, 1-band.", "y": "qaror  matni 1 band", "z": "Boshqa matn"})
    assert list(g.values()) == [["x", "y"]]


# ------------------------------------------------------------------ editions, change notes, lessons


def _row(path, text, vf, vt, sf, st, notes="", container=False):
    return {
        "path": path,
        "heading": "",
        "text": text,
        "element_id": "",
        "notes": notes,
        "ondate": vf,
        "seq_from": sf,
        "seq_to": st,
        "valid_from": vf,
        "valid_to": vt,
        "is_container": container,
    }


def test_change_documents_cover_changes_lost_force_and_moves():
    long_a = (
        "Mahalliy hokimlarning vakolatlari quyidagilardan iborat: hududni rivojlantirish dasturlarini tasdiqlash. "
        * 2
    )
    rows = [
        _row("art:21/part:1", "Eski matn " * 12, "2020-01-01", "2024-10-19", 0, 0),
        _row(
            "art:21/part:1",
            "Yangi matn " * 12,
            "2024-10-19",
            None,
            1,
            1,
            "(21-modda OʻRQ-976-sonli Qonuniga asosan tahrirda — x)",
        ),
        _row("art:25", long_a, "2020-01-01", "2024-10-19", 0, 0),  # removed, text moves
        _row("art:21-1", long_a, "2024-10-19", None, 1, 1),  # ... to art:21-1
        _row("art:30", "Kuchini yoʻqotgan modda " * 8, "2020-01-01", "2024-10-19", 0, 0),  # removed outright
    ]
    meta = {"abs_id": 112170, "title": "Mahalliy davlat hokimiyati toʻgʻrisida", "act_type": "law"}
    docs = export.amendment_docs(meta, rows, "uz", "Latn")
    assert len(docs) == 1 and docs[0]["date"] == "2024-10-19"
    t = docs[0]["text"]
    assert "21-modda 1-qism: oʻzgartirilgan" in t and "Oldin (2020-01-01 dan 2024-10-19 gacha)" in t
    assert "25-modda: 21-1-modda ga koʻchirilgan" in t  # moved or renumbered, found from the text itself
    assert "30-modda: 2024-10-19 dan kuchini yoʻqotgan" in t
    assert "oʻz kuchini yoʻqotgan" not in t or "Asos" in t


def test_time_cut_keeps_new_editions_out_of_change_documents_and_lessons():
    rows = [_row("art:1", "Matn " * 30, "2026-10-05", None, 0, 0)]
    assert export.amendment_docs({"abs_id": 1, "title": "t", "act_type": "law"}, rows, "uz", "Latn") == []
    meta = {"abs_id": 1, "title": "t", "act_type": "law", "lex_id": "-1", "number": ""}
    assert export.lesson_inputs(meta, rows, "k", set()) == []


def test_header_and_chunks_repeat_dates_on_every_chunk():
    meta = {
        "abs_id": 4674902,
        "title": "Soliq kodeksi",
        "act_type": "code",
        "number": "",
        "adopted": "2019-12-30",
    }
    hdr = export.header(meta, "uz", "Latn", "2025-01-01", None, "in_force")
    assert (
        hdr.startswith("[HUJJAT] Soliq kodeksi | tur: kodeks") and "tahrir: 2025-01-01 dan hozirgacha" in hdr
    )
    blocks = [
        {"kind": "article", "text": f"{i}-modda. Sarlavha", "path": f"art:{i}", "art": f"art:{i}"}
        for i in range(1, 6)
    ]
    for b in blocks[:]:
        blocks.append(
            {"kind": "text", "text": "soʻz " * 300, "path": b["path"] + "/part:1", "art": b["path"]}
        )
    blocks.sort(key=lambda b: (int(b["art"].split(":")[1]), b["kind"] != "article"))
    chunks = export.chunk_by_article(blocks, hdr, max_words=700)
    assert len(chunks) >= 2 and all(c["text"].startswith(hdr) for c in chunks)


def test_lesson_inputs_skip_containers_and_blocklisted_units():
    rows = [
        _row("art:5", "x" * 200, "2020-01-01", None, 0, 0, container=True),
        _row("art:5/part:1", "a" * 200, "2020-01-01", "2022-01-01", 0, 0),
        _row("art:5/part:1", "b" * 200, "2022-01-01", None, 1, 1),
        _row("art:6/part:1", "c" * 200, "2020-01-01", None, 0, 0),
    ]
    meta = {"act_type": "law", "title": "T", "number": "1", "lex_id": "-1"}
    got = export.lesson_inputs(meta, rows, "nla", {"art:6"})
    assert [(r["path"], r["valid_from"]) for r in got] == [
        ("art:5/part:1", "2020-01-01"),
        ("art:5/part:1", "2022-01-01"),
    ]
    assert got[1]["prev_text"] == "a" * 200 and got[0]["prev_text"] is None


def test_law_school_data_reads_refinery_lesson_inputs(tmp_path):
    from research import law_school_data as lsd
    from research.refinery.io import write_jsonl

    rows = [
        {
            "act_key": "-9",
            "path": "cl:1",
            "heading": "",
            "text": "1. " + "Hokim tuman hududida qaror qabul qiladi, " * 4,
            "valid_from": "2024-05-01",
            "valid_to": None,
            "act_type": "local_hokim_qaror",
            "type": "local_hokim",
            "title": "Qarshi tumanida",
            "number": "1-1-1-Q/24",
            "prev_text": None,
            "lex_id": "-9",
        }
    ]
    write_jsonl(tmp_path / "lesson_inputs" / "part-00000.jsonl.gz", rows)
    out = tmp_path / "lessons.jsonl"
    lsd.main(tmp_path / "lesson_inputs", out)
    line = out.read_text(encoding="utf-8").splitlines()[0]
    assert "mahalliy hokim qarori" in line and "1-band" in line


# ------------------------------------------------------------------ PDF decisions


def _first_zip():
    files = config.CACHE / "files"
    zips = sorted(files.glob("*.zip")) if files.exists() else []
    for z in zips:
        if z.stat().st_size:
            return z
    return None


@pytest.mark.skipif(_first_zip() is None, reason="no local-decision ZIP cached")
def test_pdf_extraction_uses_ascii_temp_name_and_cuts_clauses():
    import shutil

    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext missing")
    from research.refinery.extract_pdf import extract_pdf

    res = extract_pdf(Path(_first_zip()), "t")
    good = [r for r in res if r.text]
    assert good and good[0].pages >= 1
    assert any(u["path"] and u["path"].startswith("cl:") for u in good[0].units)
    assert "e-qaror.gov.uz" not in good[0].text


# ------------------------------------------------------------------ OCR letter restoration and officials in tables


def test_ocr_restores_uzbek_cyrillic_letters_from_the_vocabulary():
    from research.refinery.extract_ocr import ocr_correct, ocr_quality

    vocab = {"қарори", "тўғрисида", "ўзбекистон", "ҳокимлиги", "кучга", "кирди"}
    text = "Ҳокимлиги карори тӯфрисида Ъзбекистон хокимлиги кучга кирди, зххзхз"
    fixed, n = ocr_correct(text, vocab)
    assert "қарори" in fixed and "тўғрисида" in fixed and "Ўзбекистон" in fixed and "ҳокимлиги" in fixed
    assert (
        "кучга" in fixed and "зххзхз" in fixed
    )  # words the vocabulary knows, or cannot explain, stay as read
    assert n == 4
    assert ocr_quality(fixed, vocab)["oov_rate"] < ocr_quality(text, vocab)["oov_rate"]


def test_ocr_markup_leaks_are_stripped():
    from research.refinery.extract_ocr import strip_markup

    out = strip_markup(
        r"&amp;quot;ТУМАРИС&amp;quot; $ \frac{F.Нормаев}{(\phi.и.ш.)} $ 40^{\circ}C \mathrm{CM} \underline{20}"
    )
    for junk in ("quot", "frac", "circ", "mathrm", "underline", "$", "{", "\\"):
        assert junk not in out
    assert "ТУМАРИС" in out and "Нормаев" in out and "CM" in out and "20" in out


_OCR_DIR_OK = config.OCR_DIR.exists() and (config.OUT / "pilot_ids.jsonl").exists()


@pytest.mark.skipif(not _OCR_DIR_OK, reason="needs the OCR folder and the pilot ids (the box)")
def test_ocr_oov_pass_rate_on_the_pilot_documents():
    """Pilot baseline with the first restoration pass: 98 of 200 finished OCR documents under the OOV gate."""
    from research.refinery import filters, ocr_eval
    from research.refinery.io import read_jsonl

    pilot = config.OUT / "pilot"
    texts = []
    for f in sorted((pilot / "01_extract" / "acts").glob("*.jsonl.gz")):
        for r in read_jsonl(f):
            if r["source_kind"] == "html" and r["meta"]["level"] == "national":
                texts.append("\n".join(b["text"] for b in r["blocks"]))
    keys = [t["key"] for t in read_jsonl(config.OUT / "pilot_ids.jsonl") if t.get("kind") == "ocr"]
    res = ocr_eval.evaluate(keys, filters.build_vocab(texts))
    assert res["docs"] >= 190 and res["oov_pass"] >= 105, res


def test_officials_in_commission_rows_stay_unmasked():
    rows = (
        "Komissiya tarkibi:\n"
        "1. | Karimov A. | tuman hokimi, komissiya raisi\n"
        "2. | Aliyev Vali Karimovich | hokim oʻrinbosari\n"
        "3. | Тошматов Б. | Туман молия бўлими бошлиғи\n"
        "4. Rahimov S. boshligʻi, ishchi guruh aʼzosi\n"
        "9 Yusupov K. aʼzosi"
    )
    out, counts = pii.mask(rows, "local", None, sensitive=True)
    for name in ("Karimov", "Aliyev", "Тошматов", "Rahimov", "Yusupov"):
        assert name in out, (name, out)
    assert "[FUQARO" not in out and not counts.get("name_patronymic") and not counts.get("name_initials")


def test_citizens_next_to_the_same_words_are_still_masked():
    text = (
        "Fuqaro Karimov Aziz Rustamovich ga yer ajratilsin.\n"
        "1. | Nurmatova Dilnoza Alisher qizi | 12:34:56:78:90:1234 | kadastr\n"
        "Qishloq xoʻjaligi yer uchastkasi tuman hokimining 2024-yil 5-martdagi qaroriga asosan fuqaro Sodiqov T. ga doimiy foydalanishga berildi."
    )
    out, _ = pii.mask(text, "local", None, sensitive=True)
    for secret in ("Rustamovich", "Nurmatova", "12:34:56", "Sodiqov"):
        assert secret not in out, (secret, out)


# ------------------------------------------------------------------ batch run: the global steps do not depend on batching


def test_batches_never_split_a_twin_pair_and_keep_order():
    from research.refinery import full

    tasks = [{"lex_id": lid} for lid in ["-5", "5", "-6", "6", "7", "-8", "8", "9"]]
    batches = full.make_batches(tasks, 3)
    flat = [t["lex_id"] for b in batches for t in b]
    assert flat == [t["lex_id"] for t in tasks]
    for b in batches:  # an absolute id never appears in two batches
        assert not (
            {t["lex_id"].lstrip("-") for t in b}
            & {t["lex_id"].lstrip("-") for o in batches if o is not b for t in o}
        )


def test_signature_clusters_match_text_clusters_and_ignore_input_order():
    import random

    from research.refinery import dedup

    base = " ".join(f"word{i % 97}x{i}" for i in range(400))
    texts = {
        "a": base,
        "b": base.replace("word5x5", "changed"),
        "c": " ".join(f"zzz{i}" for i in range(400)),
        "d": base.replace("word9x9", "other").replace("word20x20", "more"),
    }
    mh = dedup.MinHasher()
    items = [
        {
            "id": k,
            "stratum": "s",
            "sig": mh.signature_np(dedup.shingle_set(t)),
            "adopted": f"2024-0{i + 1}-01",
        }
        for i, (k, t) in enumerate(texts.items())
    ]
    ref = {(r["id"], r["cluster"]) for r in dedup.cluster_signatures(items)}
    ids = {i for i, _ in ref}
    assert ids == {"a", "b", "d"}
    for seed in range(5):
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        got = dedup.cluster_signatures(shuffled)
        assert {r["id"] for r in got} == ids and len({r["cluster"] for r in got}) == 1
    text_rows = dedup.minhash_clusters(
        [{"id": k, "stratum": "s", "text": t, "adopted": "2024-01-01"} for k, t in texts.items()]
    )
    assert {r["id"] for r in text_rows} == ids


def test_rotating_writer_is_deterministic_and_never_empty(tmp_path):
    import hashlib

    from research.refinery import full
    from research.refinery.io import read_jsonl

    def run(d):
        w = full.Rotating(d, "b000", 2)
        for i in range(5):
            w.write({"i": i, "t": "Oʻzbekiston"})
        w.close()
        return sorted(d.glob("*.gz"))

    f1, f2 = run(tmp_path / "x"), run(tmp_path / "y")
    assert len(f1) == 3
    assert [hashlib.sha1(p.read_bytes()).hexdigest() for p in f1] == [
        hashlib.sha1(p.read_bytes()).hexdigest() for p in f2
    ]
    assert [r["i"] for p in f1 for r in read_jsonl(p)] == list(range(5))
    empty = full.Rotating(tmp_path / "z", "b001", 2)
    empty.close()
    assert list(read_jsonl(tmp_path / "z" / "b001-000.jsonl.gz")) == []


def test_word_attachments_are_read_from_doctext(tmp_path):
    from research.refinery.extract_pdf import doc_text

    (tmp_path / "123__2-x.doc.txt").write_text(
        "2-ИЛОВА\n\n1. Иккинчи band matni, " + "сўз " * 30, encoding="utf-8"
    )
    (tmp_path / "123__1-x.doc.txt").write_text(
        "Қарор\nқилади:\n1. Биринчи band matni, " + "сўз " * 30, encoding="utf-8"
    )
    (tmp_path / "124__1-x.doc.txt").write_text("x", encoding="utf-8")
    pt = doc_text("123", tmp_path)
    assert pt and pt.pages == 2 and pt.text.index("Биринчи") < pt.text.index("Иккинчи")
    assert any(u["path"] == "cl:1" for u in pt.units)
    assert doc_text("124", tmp_path) is None and doc_text("999", tmp_path) is None
