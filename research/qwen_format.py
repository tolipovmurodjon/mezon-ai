"""Read the real Qwen model files on the box and write docs/qwen_tool_format.md from them, not from memory.

    python -X utf8 -m research.qwen_format /path/to/model_dir

Records: architectures, context length, whether a vision tower exists, the license line of the README, special tokens
for thinking and tool calls, and whether the chat template handles tools. Claims such as "vision-language", "262K
context" or "Apache 2.0" are only stated if these files say so.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(model_dir: str) -> None:
    m = Path(model_dir)
    cfg = json.loads((m / "config.json").read_text(encoding="utf-8"))
    tok = json.loads((m / "tokenizer_config.json").read_text(encoding="utf-8"))
    tmpl = tok.get("chat_template") or ""
    if not tmpl and (m / "chat_template.jinja").exists():
        tmpl = (m / "chat_template.jinja").read_text(encoding="utf-8")
    text_cfg = cfg.get("text_config", cfg)
    added = [v.get("content", "") for v in (tok.get("added_tokens_decoder") or {}).values()]
    special = [t for t in added if re.search(r"think|tool|im_start|im_end|vision|image", t)]
    readme = (m / "README.md").read_text(encoding="utf-8", errors="replace") if (m / "README.md").exists() else ""
    lic = re.search(r"^license:\s*(\S+)", readme, re.MULTILINE)
    lines = [
        f"# Qwen model format (read from {m.name} files, {__import__('datetime').date.today()})", "",
        f"- architectures: {cfg.get('architectures')}",
        f"- model_type: {cfg.get('model_type')}",
        f"- context (max_position_embeddings): {text_cfg.get('max_position_embeddings')}",
        f"- vision tower present: {'vision_config' in cfg}",
        f"- license (README front matter): {lic.group(1) if lic else 'not stated'}",
        f"- hidden size / layers: {text_cfg.get('hidden_size')} / {text_cfg.get('num_hidden_layers')}",
        f"- torch_dtype: {cfg.get('torch_dtype') or text_cfg.get('torch_dtype')}",
        f"- quantization_config: {cfg.get('quantization_config', {}).get('quant_method', 'none')}", "",
        "## Special tokens (thinking, tools, chat)", *[f"- `{t}`" for t in special], "",
        "## Chat template", f"- mentions tools: {'tools' in tmpl}", f"- mentions <tool_call>: {'<tool_call>' in tmpl}",
        f"- mentions <think>: {'<think>' in tmpl}", "", "```jinja", tmpl[:6000], "```"]
    out = ROOT / "docs" / "qwen_tool_format.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"-> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
