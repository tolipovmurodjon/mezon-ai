from mezon import llm
from mezon.reader import frame

CLAUSE = ("3. Tuman hududidagi barcha tadbirkorlik subyektlari 2027-yil 1-yanvardan boshlab har oyda "
          "maishiy chiqindilar uchun 44 080 so‘m to‘lov to‘lashi shart.")


def _fake(frames):
    return lambda system, user, max_tokens=1500: {"frames": frames}


def test_grounded_frame_is_kept(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake([{
        "who": "tadbirkorlik subyektlari", "modality": "obligation", "action": "to'lov to'lash",
        "deadline": "2027-yil 1-yanvardan", "money": "44 080 so'm", "affects_business": True,
        "quote": "maishiy chiqindilar uchun 44 080 so'm to'lov to'lashi shart",
    }]))
    frames, dropped = frame.read_clause(CLAUSE)
    assert dropped == 0 and len(frames) == 1
    assert frames[0].affects_business and frames[0].modality == "obligation"


def test_invented_quote_and_bad_modality_are_dropped(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake([
        {"modality": "obligation", "quote": "jarima 10 baravar miqdorida undiriladi"},
        {"modality": "maybe", "quote": "maishiy chiqindilar uchun 44 080"},
        {"modality": "obligation", "quote": "shart"},
    ]))
    frames, dropped = frame.read_clause(CLAUSE)
    assert frames == [] and dropped == 3
