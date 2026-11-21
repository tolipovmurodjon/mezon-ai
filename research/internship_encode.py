"""Multi-span encoder for tool-use SFT (pilot A): loss on every assistant span, on nothing else.

    from research.internship_encode import encode_multi
    ids, labels = encode_multi(tok, row["messages"], TOOLS if row["tools"] else None, max_len=3072)

research/train_sft.encode() masks everything before the LAST assistant header, so it cannot train a multi-turn tool
loop. This one renders the whole conversation with the model's own chat template, finds every assistant turn
("<|im_start|>assistant\\n" ... "<|im_end|>"), and unmasks it. Masked: system, user, <tool_response> turns, the assistant
header and the "<think>\\n" that the generation prompt already supplies at inference. Unmasked: the rest of the think,
the tool call, the final answer and <|im_end|>. Tokenised once (offset mapping), so token boundaries equal inference's.
An example longer than max_len is rejected (None), never truncated: a cut tool loop teaches a broken format.
"""

import re

SPAN = re.compile(r"<\|im_start\|>assistant\n(?:<think>\n)?(.*?<\|im_end\|>)", re.DOTALL)


def assistant_spans(text: str) -> list[tuple[int, int]]:
    """Character spans (start, end) of the trainable part of every assistant turn in the rendered chat text."""
    return [(m.start(1), m.end(1)) for m in SPAN.finditer(text)]


def encode_multi(tok, messages: list[dict], tools: list | None, max_len: int = 3072):
    """-> (input_ids, labels) as lists, or None when the example exceeds max_len tokens or has no assistant span."""
    text = tok.apply_chat_template(messages, tools=tools, tokenize=False)
    spans = assistant_spans(text)
    if not spans:
        return None
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids = list(enc["input_ids"])
    if len(ids) > max_len:
        return None
    labels, j = [], 0
    for tid, (s, e) in zip(ids, enc["offset_mapping"]):
        while j < len(spans) and s >= spans[j][1]:
            j += 1
        labels.append(tid if j < len(spans) and spans[j][0] <= s < spans[j][1] else -100)
    if all(x == -100 for x in labels):
        return None
    return ids, labels


def to_tensors(ids: list[int], labels: list[int]):
    import torch

    return torch.tensor([ids]), torch.tensor([labels])
