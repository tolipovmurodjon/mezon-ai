"""
Run under the Mezon venv:  stdin = {"text": "...", "date": "YYYY-MM-DD"}  stdout = list of law cards.
Parses the preamble for cited acts + articles and reads each as of the decision date (mezon.tools.law_as_of).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.environ.get("MEZON_REPO", r"D:\10_projects\mezon"))
from mezon import tools  # noqa: E402
from mezon.rules.basis import cited_articles  # noqa: E402
from mezon.rules.run import load_law  # noqa: E402
from mezon.rules.common import SafeLaw  # noqa: E402


def main():
    inp = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    text, date = inp["text"], inp["date"]
    law = load_law()
    cards = []
    if law is None:
        print(json.dumps([]))
        return
    exists = lambda key, path: law.get_unit(key, path, date) is not None  # noqa: E731
    try:
        arts = cited_articles(text, exists)
    except Exception:  # noqa: BLE001
        arts = cited_articles(text)
    if not arts:  # a bare title has no "qaror qilaman" marker: add one so the preamble parser reads it
        arts = cited_articles(text + " qaror qilaman: 1. ...")
    for key, path, sentence in arts[:12]:
        r = tools.law_as_of(law, key, path, date)
        try:
            title = law.act(key)["title"]
        except Exception:  # noqa: BLE001
            title = key
        card = {"act_key": key, "act_title": title, "article": path.removeprefix("art:"), "sentence": sentence[:300]}
        if "text" in r:
            card.update(text=r["text"], in_force=bool(r.get("in_force")), heading=r.get("heading") or "", edition=r.get("edition"),
                        url=r.get("url") or "", provisional=bool(r.get("provisional")))
        else:
            card.update(text="", in_force=False, missing=True, reason=r.get("reason") or r.get("error") or "",
                        removed_in=r.get("removed_in_edition"), last_seen=r.get("last_seen_edition"), edition=r.get("edition"),
                        note=r.get("lost_force_note") or "")
            if r.get("last_seen_edition"):  # show the expert what the decision actually relied on
                try:
                    old = tools.law_as_of(law, key, path, r["last_seen_edition"])
                    if old.get("text"):
                        card.update(last_text=old["text"][:700], last_heading=old.get("heading") or "")
                except Exception:  # noqa: BLE001
                    pass
        cards.append(card)
    sys.stdout.buffer.write(json.dumps(cards, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
