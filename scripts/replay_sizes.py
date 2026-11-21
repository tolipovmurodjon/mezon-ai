"""L40S: sizes of the public replay datasets on Hugging Face (metadata only, nothing downloaded)."""
import json
import urllib.request

def tree(repo, path):
    url = f"https://huggingface.co/api/datasets/{repo}/tree/main/{path}?recursive=true"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

for repo, path in [("HuggingFaceFW/fineweb-2", "data/uzn_Latn"), ("allenai/tulu-3-sft-mixture", "data")]:
    try:
        files = [f for f in tree(repo, path) if f.get("type") == "file"]
        print(repo, path, f"{len(files)} files, {sum(f.get('size', 0) for f in files) / 1e9:.2f} GB",
              [f["path"].split("/")[-1] for f in files][:4])
    except Exception as e:  # noqa: BLE001
        print(repo, path, "error", e)
