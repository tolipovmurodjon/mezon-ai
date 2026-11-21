"""L40S: the few Constitutional Court PDFs listed on konstsud.uz (decisions section, ru + en), 2 s apart."""
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("data/raw/konstsud"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Mezon research; polite)"}
pages = ["https://www.konstsud.uz/ru/docs/konstitutsiyaviy-sudi-qarorlari",
         "https://www.konstsud.uz/en/docs/konstitutsiyaviy-sudi-qarorlari"]
got = 0
for p in pages:
    time.sleep(2)
    html = urllib.request.urlopen(urllib.request.Request(p, headers=UA), timeout=60).read().decode("utf-8", "replace")
    (OUT / (p.split("/")[3] + "_decisions.html")).write_text(html, encoding="utf-8")
    for href in sorted(set(re.findall(r'href="([^"]+\.pdf)"', html))):
        url = urllib.parse.quote(urllib.parse.urljoin(p, href), safe=":/%?=&#")
        target = OUT / urllib.parse.unquote(url.rsplit("/", 1)[-1])
        if target.exists():
            continue
        time.sleep(2)
        target.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())
        got += 1
        print("got", target.name, target.stat().st_size)
print("KONSTSUD DONE", got, "files")
