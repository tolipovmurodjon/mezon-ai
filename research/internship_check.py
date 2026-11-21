"""CPU round-trip test for the internship data, with the REAL tokenizer. Run on the L40S box (no GPU is touched).

    python3 research/internship_check.py --model ~/models/Qwen3.8-27B --data internship_sft.jsonl [--deep 20]

Checks (a failure exits 1): for the first --deep rows, <tool_call> and </tool_call> counts match the messages; each call
parses back (research.bench_tools_run.parse_call) to the exact name and arguments; exactly the assistant spans are
unmasked (no system, user or tool_response token has a label, every think / call / answer is covered); for ALL rows,
tokens <= max_len. Prints token statistics.
"""

import argparse
import json
import re
import sys

if sys.platform != "linux":
    sys.exit("internship_check.py is meant for the L40S box (Linux): the laptop has no tokenizer and no spare RAM")

sys.path.insert(0, ".")
from mezon.tools import TOOLS  # noqa: E402
from research.bench_tools_run import CALL, parse_call  # noqa: E402
from research.internship_encode import assistant_spans, encode_multi  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--deep", type=int, default=20)
    ap.add_argument("--max-len", type=int, default=3072)
    ap.add_argument("--list-over", action="store_true", help="print ids of rows over max-len (row index and family)")
    a = ap.parse_args()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.model)
    rows = [json.loads(x) for x in open(a.data, encoding="utf-8", newline="").read().split("\n") if x.strip()]
    bad, over, lens, trained = [], [], [], 0
    deep_done = 0
    for i, r in enumerate(rows):
        tools = TOOLS if r["tools"] else None
        text = tok.apply_chat_template(r["messages"], tools=tools, tokenize=False)
        n = len(tok(text, add_special_tokens=False)["input_ids"])
        lens.append(n)
        if n > a.max_len:
            over.append((i, r["family"], n))
            continue
        if deep_done < a.deep and r["tools"] and "calls" in r:
            deep_done += 1
            msgs = r["messages"]
            want = [tc["function"] for m in msgs if m["role"] == "assistant" for tc in m.get("tool_calls", [])]
            spans = assistant_spans(text)
            conv = text[text.index("<|im_start|>user"):]  # the system block holds the template's own example call
            if conv.count("<tool_call>") != len(want) or conv.count("</tool_call>") != len(want):
                bad.append((i, "tool_call tag count"))
            if len(spans) != sum(1 for m in msgs if m["role"] == "assistant"):
                bad.append((i, "assistant span count"))
            got = [parse_call(b) for b in CALL.findall(conv)]
            for (gname, gargs), w in zip(got, want):
                if gname != w["name"] or {k: v.strip() for k, v in gargs.items()} != {k: str(v).strip() for k, v in w["arguments"].items()}:
                    bad.append((i, f"call mismatch {gname} {gargs} vs {w}"))
            enc = encode_multi(tok, msgs, tools, a.max_len)
            if enc is None:
                bad.append((i, "encode_multi returned None"))
                continue
            ids, labels = enc
            lab = tok.decode([t for t in labels if t != -100], skip_special_tokens=False)
            offs = tok(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
            for (st, _), lb in zip(offs, labels):
                if lb != -100:  # the turn that owns this token must be an assistant turn
                    head = text.rfind("<|im_start|>", 0, st + 1)
                    if not text.startswith("<|im_start|>assistant" + chr(10), head):
                        bad.append((i, f"labeled token outside an assistant turn at char {st}"))
                        break
            for m in msgs:
                if m["role"] == "assistant":
                    for piece in (m.get("reasoning_content") or "", m.get("content") or ""):
                        if piece.strip() and piece.strip()[:30] not in lab:
                            bad.append((i, "assistant text missing from labels"))
            if "<|im_start|>" in lab or "<tool_response>" in lab:
                bad.append((i, "header or tool_response inside labels"))
            if not lab.rstrip().endswith("<|im_end|>"):
                bad.append((i, "last labeled token is not <|im_end|>"))
            trained += sum(1 for t in labels if t != -100)
    lens_sorted = sorted(lens)
    print(json.dumps({"rows": len(rows), "deep_checked": deep_done, "tokens_mean": round(sum(lens) / len(lens), 1),
                      "tokens_median": lens_sorted[len(lens) // 2], "tokens_max": lens_sorted[-1],
                      "tokens_total": sum(lens), "over_max_len": len(over), "bad": len(bad)}))
    if a.list_over:
        print("over:", over[:40])
    for b in bad[:30]:
        print("BAD", b)
    sys.exit(1 if bad or over else 0)


if __name__ == "__main__":
    main()
