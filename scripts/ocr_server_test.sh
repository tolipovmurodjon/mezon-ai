#!/usr/bin/env bash
# L40S only: (re)start the OCR server if it is down, wait until it answers, then OCR one real page through it.
[ "$(uname -s)" = Linux ] || { echo "not Linux: refusing to run"; exit 1; }
cd "$HOME/mezon" || exit 1
if ! curl -s -m 5 http://127.0.0.1:8118/v1/models | grep -q PaddleOCR; then
  tmux kill-session -t =ocrsrv 2>/dev/null
  tmux new -d -s ocrsrv "PATH=$HOME/vllm-venv/bin:\$PATH PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True paddlex_genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm --host 127.0.0.1 --port 8118 --backend_config $HOME/ocr_vllm_backend.yaml > $HOME/mezon/logs/ocr_server.log 2>&1"
  for i in $(seq 1 60); do curl -s -m 5 http://127.0.0.1:8118/v1/models | grep -q PaddleOCR && break; sleep 10; done
fi
curl -s -m 5 http://127.0.0.1:8118/v1/models | head -c 120; echo
env | grep -iE "^(http|https|no)_proxy" || echo "no proxy env"
K=$(python3 -c "import json;print(next(json.loads(l)['file'] for l in open('data/ocr/scans.jsonl') if json.loads(l)['scanned']))")
T=$(mktemp -d); cd "$T" || exit 1
python3 -c "
import io,zipfile,sys
from pathlib import Path
p=Path('$HOME/mezon/data/cache/lexuz/files/$K'); d=p.read_bytes()
d = d if p.suffix=='.pdf' else zipfile.ZipFile(io.BytesIO(d)).read([n for n in zipfile.ZipFile(io.BytesIO(d)).namelist() if n.lower().endswith('.pdf')][0])
open('x.pdf','wb').write(d)"
pdftoppm -r 200 -png -f 1 -l 1 x.pdf p
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True "$HOME/ocr-venv/bin/python" - <<'PY' 2>&1 | grep -vE "^\s*$|Warning|warn" | tail -25
import glob, traceback
from paddleocr import PaddleOCRVL
for url in ["http://127.0.0.1:8118/v1", "http://localhost:8118/v1"]:
    try:
        pipe = PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="vllm-server", vl_rec_server_url=url)
        for r in pipe.predict(input=glob.glob("p-*.png")[0]):
            r.save_to_markdown(save_path="o")
        md = "".join(open(f, encoding="utf-8").read() for f in glob.glob("o/**/*.md", recursive=True))
        print("URL", url, "OK chars", len(md)); print(md[:300]); break
    except Exception:
        print("URL", url, "FAILED"); traceback.print_exc(limit=3)
PY
tail -3 "$HOME/mezon/logs/ocr_server.log" | cut -c1-200
echo "test on $(hostname), file $K"
