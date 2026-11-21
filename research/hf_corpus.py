"""Download the openly licensed Uzbek legal corpora from Hugging Face (box only: they are large).

    python -X utf8 -m research.hf_corpus            # -> data/raw/hf/<owner>__<name>/*.parquet + data/raw/hf/manifest.json

Only datasets whose card states an open license. Sohiba01/uzbek-legal-ir (no card, no license) and
Mehriddin1997/lex-uzbek-laws ("other") are deliberately skipped. An uploader's license does not override lex.uz's own
terms: use these for internal CPT; ask the Adolat centre before republishing their text. Row counts need pyarrow.
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "hf"
DATASETS = {"sukhrobnurali/uzbek-legal-corpus": "apache-2.0", "Alii2004/lexuz-legislation": "cc-by-4.0",
            "ninetydevuz/lex-uz-legal-text-scaping": "apache-2.0"}
UA = {"User-Agent": "mezon-research/0.1"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for ds, lic in DATASETS.items():
        files = json.loads(_get(f"https://huggingface.co/api/datasets/{ds}/parquet"))
        urls = [u for cfg in files.values() for split in cfg.values() for u in split] if isinstance(files, dict) else files
        if not urls:  # no parquet conversion on the Hub: take the repository's own data files
            tree = json.loads(_get(f"https://huggingface.co/api/datasets/{ds}/tree/main?recursive=true"))
            urls = [f"https://huggingface.co/datasets/{ds}/resolve/main/{f['path']}" for f in tree
                    if f["type"] == "file" and f["path"].endswith((".parquet", ".jsonl", ".json.gz", ".jsonl.gz", ".csv"))]
        d = OUT / ds.replace("/", "__")
        d.mkdir(exist_ok=True)
        rows, size = 0, 0
        for i, url in enumerate(urls):
            f = d / f"{i:03d}_{url.split('/resolve/main/')[-1].replace('/', '__') if '/resolve/main/' in url else url.rsplit('/', 1)[-1]}"
            if not f.exists():
                f.write_bytes(_get(url))
                time.sleep(1)
            size += f.stat().st_size
            try:
                import pyarrow.parquet as pq
                rows += pq.ParquetFile(f).metadata.num_rows
            except ImportError:
                rows = -1
        manifest[ds] = {"license": lic, "files": len(urls), "bytes": size, "rows": rows,
                        "fetched": time.strftime("%Y-%m-%d %H:%M")}
        print(ds, manifest[ds], flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
