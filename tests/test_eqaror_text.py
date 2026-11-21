import json

from research import eqaror_text as e

CODE = "5d128f2a0123456789abcdef01234567"


def test_text_path_sharded(tmp_path):
    assert e.text_path(CODE, tmp_path) == tmp_path / "5d" / f"{CODE}.txt.gz"


def test_save_load_roundtrip(tmp_path):
    e.save_text(CODE, "Qaror ʻtest’ matni", tmp_path)
    assert e.load_text(CODE, tmp_path) == "Qaror ʻtest’ matni"
    assert e.load_text("00" + CODE[2:], tmp_path) is None


def test_pdf_tmp_name_ascii():
    n = e.pdf_tmp_name("ab/../ü" + CODE)
    assert n.isascii() and n.endswith(".pdf") and "/" not in n


def test_is_scan():
    assert e.is_scan("  \n x ")
    assert not e.is_scan("a" * 200)


def test_list_codes_order_and_filter(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    for n, code in ((10, "b" * 32), (2, "a" * 32)):
        (d / f"p{n}.json").write_text(json.dumps({"data": {"list": [{"code": code, "is_hidden": n == 2}, {"code": "bad"}]}}))
    assert list(e.list_codes("s", tmp_path)) == [("a" * 32, True), ("b" * 32, False)]
