"""After the pilot: does the trained adapter write a valid Mezon answer? One decision it trained on, one it never saw.

    python -X utf8 -m research.pilot_generate --model ~/models/Qwen3.8-27B --adapter data/models/pilot

A pipeline check only, not a quality score (that is the exam's job): prints valid-JSON yes/no, the verdict and the
number of flags next to the reference answer.
"""

import argparse
import json

from research import train_pilot as tp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default="data/models/pilot")
    ap.add_argument("--max-chars", type=int, default=2500)
    a = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb, dtype=torch.bfloat16,
                                                 device_map={"": 0})
    model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()

    train = tp.load(50)
    seen = {r["messages"][1]["content"][:120] for r in train}
    rows = [json.loads(line) for line in tp.SFT.open(encoding="utf-8")]
    unseen = next(r for r in rows if r["messages"][1]["content"][:120] not in seen
                  and json.loads(r["messages"][2]["content"])["kamchiliklar"])
    for name, r in (("trained-on", train[0]), ("unseen", unseen)):
        msgs = [dict(x) for x in r["messages"][:2]]
        if len(msgs[1]["content"]) > a.max_chars:
            msgs[1]["content"] = msgs[1]["content"][: a.max_chars] + "\n[…]\n\nQarorni tekshiring."
        enc = tok.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False, return_tensors="pt",
                                      return_dict=True).to("cuda")
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=700, do_sample=False)
        text = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        gold = json.loads(r["messages"][2]["content"])
        try:
            got = json.loads(text[text.find("{"): text.rfind("}") + 1])
            verdict = f"valid JSON, verdict={got.get('xulosa')}, flags={len(got.get('kamchiliklar', []))}"
        except json.JSONDecodeError as e:
            verdict = f"NOT valid JSON ({e.msg})"
        print(f"{name}: {verdict} | reference verdict={gold['xulosa']}, flags={len(gold['kamchiliklar'])}")
        print("   ", text[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
