#!/usr/bin/env bash
# L40S only: stop OCR workers; move every OCR output that contains a failed page to data/ocr_failed/ (nothing deleted),
# drop those keys from done.jsonl (old file kept as done.jsonl.bak-<time>), so a rerun redoes them.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
tmux kill-session -t =ocr 2>/dev/null; pkill -f "[r]esearch/ocr_scans.py run"; sleep 3
python3 - <<'PY'
import json, shutil, time
from pathlib import Path
O = Path("data/ocr"); Q = Path("data/ocr_failed"); Q.mkdir(exist_ok=True)
bad = set()
for d in O.iterdir():
    if d.is_dir() and any("OCR failed" in p.read_text(encoding="utf-8", errors="replace") for p in d.glob("page-*.md")):
        bad.add(d.name)
for k in bad:
    shutil.move(str(O / k), str(Q / k))
    if (O / f"{k}.md").exists():
        shutil.move(str(O / f"{k}.md"), str(Q / f"{k}.md"))
done = O / "done.jsonl"
if done.exists():
    shutil.copy(done, O / f"done.jsonl.bak-{int(time.time())}")
    keep = [l for l in done.read_text(encoding="utf-8").splitlines() if json.loads(l)["key"] not in bad]
    done.write_text("".join(x + "\n" for x in keep), encoding="utf-8")
    print(f"moved {len(bad)} failed documents to data/ocr_failed; done.jsonl keeps {len(keep)} good")
PY
echo "on $(hostname)"
