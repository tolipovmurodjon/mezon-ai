"""L40S: how many Supreme Court plenum resolutions, Constitutional Court decisions, prosecutor / ombudsman acts
are already in our lex.uz catalogue (by title words, Latin + Cyrillic + Russian)."""
import re
import sqlite3

c = sqlite3.connect("data/raw/lexuz_full/state.sqlite", timeout=60)
titles = [(i, s, t or "") for i, s, t in c.execute("select lex_id, status, title from acts")]
pats = {
    "Supreme Court plenum": r"plenum|пленум",
    "Constitutional Court": r"konstitutsiyaviy sud|конституциявий суд|конституционн\w* суд",
    "Prosecutor General": r"bosh prokurat|бош прокурат|генеральн\w* прокурат",
    "Business Ombudsman": r"ombudsman|омбудсман|tadbirkorlik subyektlarining huquqlari",
    "Ministry of Justice orders": r"adliya vazir|адлия вазир|министр\w* юстиции",
}
for name, p in pats.items():
    hits = [(i, s, t) for i, s, t in titles if re.search(p, t, re.I)]
    print(f"{name}: {len(hits)}", [t[:70] for _, _, t in hits[:2]])
