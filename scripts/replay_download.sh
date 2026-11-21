#!/usr/bin/env bash
# L40S only: download the public replay datasets (Boss approved 20.11): FineWeb-2 Uzbek (uzn_Latn, ODC-By) and the
# Tulu 3 SFT mixture (ODC-BY-1.0). Into data/raw/replay/, resumable (curl -C -).
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
python3 - <<'PY' > /tmp/replay_urls.txt
import json, urllib.request
for repo, path in [("HuggingFaceFW/fineweb-2", "data/uzn_Latn"), ("allenai/tulu-3-sft-mixture", "data")]:
    with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{repo}/tree/main/{path}?recursive=true", timeout=60) as r:
        for f in json.load(r):
            if f.get("type") == "file":
                print(f"https://huggingface.co/datasets/{repo}/resolve/main/{f['path']}\tdata/raw/replay/{repo.split('/')[1]}/{f['path']}")
PY
while IFS=$'\t' read -r url out; do
  mkdir -p "$(dirname "$out")"
  curl -sL -C - --retry 5 -o "$out" "$url" && echo "ok $(du -h "$out" | cut -f1) $out"
done < /tmp/replay_urls.txt
du -sh data/raw/replay; echo REPLAY_DONE on $(hostname)
