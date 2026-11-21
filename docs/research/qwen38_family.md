# Qwen3.8 family and relatives: research note (20 Nov 2026)

Public sources only (Hugging Face model cards and API, docs pages, arXiv abstract). No Mezon data was sent anywhere.
Tags: "[snippet]" = not read in full (search-result summary only); "not found" = absent in what I read.
Pages were read through a summariser (WebFetch), so quote exact text from the card before citing in the dossier.

## 0. Does Qwen3.8 exist? Yes.

The HF API listing `huggingface.co/api/models?author=Qwen&sort=lastModified` shows six Qwen3.8 repos, all modified
2026-11-07: `Qwen3.8-27B`, `Qwen3.8-27B-FP8`, `Qwen3.8-Flash-Next`, `Qwen3.8-Flash-Next-FP8`, `Qwen3.8-2.4T-A95B`,
`Qwen3.8-2.4T-A95B-FP8`. The earlier "cannot confirm" search result was wrong.
`api/models/Qwen/Qwen3.8-27B`: created 2026-08-05, tags `qwen3_5`, `license:apache-2.0`, 27,781,427,952 params (BF16),
architecture `Qwen3_5ForConditionalGeneration`, EOS `<|im_end|>`, pad `<|endoftext|>`, 18 safetensors shards,
`chat_template.jinja` included, 6,454,419 downloads last month.
This matches our config. The architecture class is still named qwen3_5, so Qwen3.5 tooling applies.

## 1. Sizes in the newest generations

### Qwen3.8 (open weights on HF)
| Model | Total / active | Layers, hidden | Attention layout | Context | Licence | Source |
|---|---|---|---|---|---|---|
| Qwen3.8-27B (dense, text + vision) | 27B (27.78B) | 64, 5120 | 16 x (3 x Gated DeltaNet+FFN, 1 x Gated Attention+FFN); GDN 48 V / 16 QK heads, dim 128; GA 24 Q / 4 KV heads, dim 256, RoPE 64; FFN 17,408; vocab 248,320; MTP | 262,144 native, 1M with YaRN | Apache-2.0 | card + API |
| Qwen3.8-Flash-Next (MoE, text + vision) | 125B total, 6B active (+51B n-gram embedding, +4B MTP; Hub shows 180B) | 48, 2560 | 12 x (3 x GDN+MoE, 1 x Qwen Sparse Attention+MoE); 512 experts, 10 routed + 1 shared; expert dim 640 | 262,144 native, 1M YaRN | qwen-community-1.0 (not Apache; read its terms) | card |
| Qwen3.8-2.4T-A95B (MoE, text only, thinking cannot be disabled) | 2.4T / 95B | 92, 8192 | 23 x (3 x GDN+MoE, 1 x GA+MoE); 512 experts, 10+1 | 262,144, up to 1.01M | card says "qwen3.8-max"; terms not stated | card |

There is **no Qwen3.8 model below 27B** on the Hub as of today. The Qwen3.8 collection shows 4 items (card text).
Qwen3.8-Flash and Qwen3.8-Max are Qwen Cloud API versions, not open weights.

### Qwen3.6 (open): only two sizes
`Qwen3.6-27B`, `Qwen3.6-35B-A3B` (+FP8 each), Apache-2.0 (HF API search).
35B-A3B card: 40 layers, hidden 2048, 256 experts (8 routed + 1 shared, expert dim 512), GDN 32 V / 16 QK, GA 16 Q / 2 KV, 262,144 context.
Qwen3.6-27B layer counts: not read (only listed).

### Qwen3.5 (open): the full small-to-large ladder (HF API list, Apr 2026 uploads)
0.8B, 2B, 4B, 9B (all with Base variants), 27B, 35B-A3B, 122B-A10B, 397B-A17B; FP8 and GPTQ-Int4 for several. Apache-2.0 on the cards read.
- Qwen3.5-9B: 32 layers, hidden 4096, 8 x (3 GDN + 1 GA), FFN 12,288, 262,144 context, Apache-2.0.
- Qwen3.5-4B: 32 layers, hidden 2560, FFN 9216, tied embeddings, 262,144 context, Apache-2.0 (page says 4B, safetensors metadata 5B).
- 0.8B and 2B: dims not read.
- Same 3:1 GatedDeltaNet:Gated-Attention pattern as 3.8. Same 248,320 vocabulary.

### Benchmarks that decide size (cards; vendor numbers, different scaffolds; not our task)
| | MMLU-Pro | GPQA-D | IFEval | IFBench | BFCL-V4 | LongBench v2 |
|---|---|---|---|---|---|---|
| Qwen3.5-9B | 82.5 | 81.7 | 91.5 | 64.5 | 66.1 | 55.2 |
| Qwen3.5-4B | 79.1 | 76.2 | 89.8 | not found | 50.3 | 50.0 |
| Qwen3.8-27B | not found | 89.2 | not found | 79.5 | not found | not found |
Other 3.8-27B numbers on its card: SWE-bench Pro 61.7, Terminal Bench 2.1 73.0, LiveCodeBench v6 90.3, HLE 30.8.
Qwen3.8-Flash-Next: IFBench 81.3, GPQA-D 91.7, Toolathlon Verified 73.5 (27B: 67.1).
No legal or Uzbek benchmark found for any of them. Nobody published Uzbek-legal numbers.

## 2. Post-training recipe (what Qwen says)

- No Qwen3.5/3.6/3.8 technical report found. A [snippet] from the Alibaba Cloud blog says a report is "upcoming". An arXiv search returned nothing.
- Qwen3.5 card: RL "scaled across million-agent environments", progressively harder task distributions, asynchronous RL frameworks for big agent scaffolds. [snippet: blog credits gains mainly to scaling nearly all RL tasks and environments; FP8 native pipeline, disaggregated async RL.]
- SFT mix, distillation from larger models, RL algorithm, LoRA guidance: **not found** in official material. Do not claim distillation.
- Modes: thinking on by default, output starts `<think>\n...</think>\n\n`. Off with `chat_template_kwargs {"enable_thinking": false}`. `/think` and `/nothink` soft switches are not supported (3.5 card).
- 3.8 adds `reasoning_effort` (xhigh default, medium, low) and `preserve_thinking` (on by default in 3.8; in 3.6 the default keeps only the latest turn's reasoning). Suggested output limits 262,144 reasoning + 131,072 answer.
- Sampling, 3.8-27B: thinking T 1.0, top_p 0.95, top_k 20, min_p 0, presence 0, rep 1.0. Non-thinking T 0.7, top_p 0.8, top_k 20, presence 1.5. (3.5 cards use presence 1.5 for thinking.)
- Tool-call format: the cards do not print the template. The documented route is the `qwen3_coder` tool parser plus `qwen3` reasoning parser (vLLM and SGLang). Read `chat_template.jinja` in our local copy for the exact `<tool_call>` body.

## 3. Fine-tuning guidance and documented domain examples

Official fine-tuning guidance from Qwen: not found. Community and framework docs:

- **Unsloth Qwen3.5 guide** (read): LoRA r=16, alpha=16, dropout 0, all 7 projections (q,k,v,o,gate,up,down), grad checkpointing "unsloth", AdamW 8-bit, batch 1 x accum 4, seq 2048 to start; LR not stated. bf16 LoRA VRAM: 4B 10 GB, 9B 22 GB, **27B 56 GB**, 35B-A3B 74 GB, 122B-A10B 256 GB; full fine-tune about 4x. **Advises against QLoRA 4-bit for all Qwen3.5** (higher quantisation error). Needs transformers v5. Use the same chat template and EOS in training and inference. To keep reasoning, keep at least 75% reasoning examples in the mix. Router fine-tuning off by default on MoE.
- **ms-swift Qwen3.5 best practice** (read): 4B dense SFT, LoRA r=8, alpha=32, all-linear, LR 1e-4, warmup 0.05, 1 epoch, bf16, batch 4, max length 2048, `add_non_thinking_prefix true`, `loss_scale ignore_empty_think`, about 20 GiB per GPU on 4 GPUs, 12 min. 35B-A3B Megatron LoRA r=8 alpha=32 LR 1e-4 (min 1e-5), 4 GPUs about 40 GiB each. Install: `flash-linear-attention>=0.4.2` (`--no-build-isolation`), `causal-conv1d` from GitHub main (no pin), `transformers>=5.9`, `vllm>=0.17.0`, Python 3.12. Known slow-FLA-training issues (fla #758, #121). ms-swift >=4.1.0 uses Megatron GDN by default (`USE_MCORE_GDN=0` switches to the transformers path).
- **Finance, 4B** (arXiv 2610.08882 abstract, read): Qwen3.5-4B + LoRA r=16, 22,000 examples, 600-example benchmark. JSON validity 0% to 91.3%, FinQA exact match 14.7% to 40.0%, calculator correctness 48.0% to 82.7%, branch label agreement 20.1% to 89.5%. [snippet from the body: adapters on FFN of all layers, attention only in full-attention layers, GDN modules not adapted.] The author notes limits: filing overlap and inconsistent targets.
- **Legal, 35B-A3B** (HF adapter `thanhdath/Qwen3.5-35B-A3B-Legal-LoRA`, via friendli.ai page): r=16, alpha=32, LR 2e-5 cosine, warmup 0.03, 1 epoch = 266 steps, about 8,500 conversations, one A100 80 GB about 7.5 h. **No eval metric reported**, only loss 0.409 to about 0.31. LoRA only on attention projections and shared-expert MLP because routed experts are fused tensors. Treat as a recipe, not evidence.
- Medical: not found. Tool use: only the vendor benchmarks above.
- Long-context fine-tuning guidance (beyond YaRN factor 4.0 settings on the card): not found. The card warns static YaRN hurts short-text quality, so enable it only for long jobs.
- Thinking-token handling: no official rule. Defensible approach from the two frameworks: train with the same template as inference, either keep real `<think>` traces for at least 75% of rows (Unsloth) or mask empty think blocks (ms-swift `ignore_empty_think`). Verify on our own template before a long run.

## 4. Serving and RL rollouts on one 96 GB GPU

- vLLM and SGLang support the family (cards). 3.5 card: vLLM main/nightly; `--reasoning-parser qwen3`, `--enable-auto-tool-choice --tool-call-parser qwen3_coder`; `--language-model-only` frees the vision tower's memory; MTP via `--speculative-config '{"method":"mtp","num_speculative_tokens":1..5}'` (more speed at low concurrency, less throughput at high concurrency). Blackwell: use `vllm/vllm-openai:cu130-nightly` (vLLM recipe page). Our box is Blackwell.
- Known vLLM issue: `causal_conv1d_update` assertion `num_cache_lines >= batch` means CUDA-graph capture size exceeds the Mamba cache; lower `--max-cudagraph-capture-size` (default 512), or `--max-num-seqs` (vLLM recipes page; LMCache page).
- Prefix caching on these hybrid models needs `--mamba-cache-mode align`, and vLLM labels it **experimental** (recipes page; LMCache page).
- [snippet, LMCache Chinese page] GDN backend lacks vLLM's batch-invariant mode, so cached and fresh runs are not bitwise identical. Matters for RL, where logprob mismatch between rollout and trainer is a risk.
- vLLM blog "25K total TPS/GPU on Qwen3.5" (2026-08-06) exists [snippet, not read]. vLLM's Qwen3-Next post [snippet] says a hybrid KV cache manager aligns linear and full-attention state sizes.
- Linear-attention kernels: training needs `flash-linear-attention` plus `causal-conv1d` (ms-swift). The vLLM recipe page does not discuss fla or flashinfer (not found).
- Quantisation: official `Qwen3.8-27B-FP8` exists. Qwen3.5-27B also has an official GPTQ-Int4. No QLoRA (Unsloth). Memory arithmetic (mine, not from a source): BF16 27.8B weights are about 56 GB, FP8 about 28 GB. A bf16 LoRA run (56 GB per Unsloth) plus a vLLM rollout copy does not fit together in 96 GB, and the card says nothing about the Qwen server sharing the card (our box already gives about 55% of it to the chat model). So single-GPU RL on 27B needs sequential phases (rollout with FP8 or sleeping engine, then train) or a smaller model. RL framework behaviour with weight sync and hybrid caches: not found.

## 5. Which size for which Mezon job

| Job | Pick | Why and source |
|---|---|---|
| Main auditor (checks 4, 5, 12-14: conflict with higher law, mandate drift, corruption factors; citation-bound text) | **Qwen3.8-27B** (BF16 or FP8), thinking on, tool calling via qwen3_coder parser | Newest dense open Apache-2.0 model; GPQA-D 89.2 and IFBench 79.5 vs 3.6-27B 87.8 / 69.1 (3.8-27B card); 262,144 context holds a long decision plus parent act; LoRA fits (56 GB bf16 at 27B, Unsloth). Flash-Next scores higher (IFBench 81.3, Toolathlon 73.5) but has 125B total weights, a non-Apache licence, and no fit for 96 GB shared with another model; skip. Whether it handles Uzbek legal text better than 3.6/3.5: not found, run our 20-question test. |
| Fast filter (queue triage, normative-or-individual tag, who-is-affected tag, regnum and cited-act extraction, check 6 priority) | **Qwen3.5-9B** (22 GB bf16 LoRA, Unsloth), non-thinking | Largest small sibling; IFEval 91.5, MMLU-Pro 82.5, BFCL-V4 66.1 (3.5-9B card); same architecture and Apache-2.0. No 3.8 or 3.6 small model exists (HF list). 4B is the fallback (IFEval 89.8, BFCL-V4 50.3, 10 GB LoRA); the 4B finance LoRA study shows narrow structured tasks adapt well (JSON validity 0 to 91.3%, arXiv 2610.08882). Deterministic checks 1-3, 7-11 stay as rules; use the LLM only to tag. |
| On-device citizen app | **Qwen3.5-2B or 0.8B** only if truly on-device; otherwise a server-side 4B | Only sizes below 4B are 0.8B and 2B (HF list); their cards were not read, so no quality or footprint numbers. Plan says citizen app is thin, and routing and explanation sit inside flags generated server-side. Recommendation: keep the model on the server, ship the app as a thin client; test 2B only after a measured quality bar. |

## Open items
- Read `chat_template.jinja` and `generation_config.json` of the local 27B for the exact tool-call body and `<think>` handling.
- Read the 3.5-0.8B/2B cards and the Qwen3.6-27B card (layers) if the small variant is pursued.
- Check the qwen-community-1.0 licence text before ever considering Flash-Next.
- Run the Uzbek 20-question test across 27B, 9B, 4B before choosing.

## Sources
- https://huggingface.co/api/models?author=Qwen&sort=lastModified&limit=60
- https://huggingface.co/Qwen/Qwen3.8-27B and https://huggingface.co/api/models/Qwen/Qwen3.8-27B
- https://huggingface.co/Qwen/Qwen3.8-Flash-Next
- https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B
- https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- https://huggingface.co/Qwen/Qwen3.5-9B and https://huggingface.co/Qwen/Qwen3.5-4B
- https://unsloth.ai/docs/models/qwen3.5/fine-tune
- https://swift.readthedocs.io/en/v4.4/BestPractices/Qwen3_5-Best-Practice.html
- https://docs.vllm.ai/projects/recipes/en/stable/Qwen/Qwen3.5.html
- https://docs.lmcache.ai/recipes/qwen3_5.html [snippet]
- https://arxiv.org/abs/2610.08882
- https://friendli.ai/models/thanhdath/Qwen3.5-35B-A3B-Legal-LoRA
- https://www.alibabacloud.com/blog/qwen-3-5-towards-native-multimodal-agents_602894 [snippet]
- https://vllm.ai/blog/2026-08-06-qwen35-25k-tps [snippet, not read]
