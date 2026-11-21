# Training speed and multi-node plan for the Qwen3.8-27B continued pre-training (21 Nov 2026)

Tags: [full] = read in the full page or file this session. [snippet] = from a search-result summary only, not verified on the page. [estimate] = my arithmetic or judgement, not measured. Nothing here was run on our machines. Every [estimate] must be measured before it is trusted.

Code read: `D:\10_projects\mezon\research\train_cpt.py` [full]. Facts that matter from it: batch 1, each row encoded alone (no padding, no packing), `model(input_ids, labels).loss`, `accum=16` rows per optimizer step, LoRA r=128 `all-linear`, checkpoint every 30 min with optimizer state, gradient checkpointing on (non-reentrant), `AutoModelForCausalLM` in bf16 (PEFT casts adapter weights to fp32 by default [estimate: PEFT default `autocast_adapter_dtype=True`, not checked this session]).

## 0. Bottom line

1. Capacity arithmetic [estimate]: tokens = N GPUs x tok/s per GPU x 0.9 scaling x 48,600 s (13.5 h after load and startup).
   - 6 machines at today's 620 tok/s: 163M tokens. At 800: 210M. At 1,000: 262M. At 1,200: 315M.
   - 5 machines at 1,000: 219M. At 1,200: 262M.
   - So 250-300M in 14 h needs 6 machines AND about 1,000+ tok/s per GPU (1.6x faster). Multi-node alone cannot do it.
2. The cheapest big wins, in order: (a) Liger Kernel with fused linear cross-entropy (supported for qwen3_5 [full]); (b) length-bucketed micro-batches of several rows, right-padded (no correctness risk); (c) multi-node with a hand-written chunked all-reduce of the LoRA gradients in bf16. True packing is last and probably not needed.
3. g7e.2xlarge: 50 Gbps network, 1 GPU, 8 vCPU, 64 GiB RAM, EBS up to 5 Gbps [full, AWS G7e page]. EFA is NOT available on the 2xlarge: the AWS EFA list names only g7e.8xlarge, 12xlarge, 24xlarge and 48xlarge [full]. So it is TCP over ENA, and NCCL uses the socket transport.
4. Communication is affordable: about 1-5 s per optimizer step against a 25-45 s step, if accumulation is 32-64 rows and gradients go as bf16 (section 2).
5. Open risk to check first: whether 50 Gbps is a sustained or a burst figure for a 2xlarge (AWS says sizes up to 16 vCPU are usually "up to" with a baseline and credits that last 5-60 minutes [full]). One CLI call gives the baseline (section 3, step 0).

## 1. Single-GPU fixes

### 1.1 Packing / padding-free for this hybrid model

- HF docs [full, huggingface.co/docs/transformers/en/padding_free]: for Qwen3-Next and Qwen3.5 (Gated DeltaNet) there is no position_ids-only path. Use `DataCollatorWithFlattening(return_flash_attn_kwargs=True, return_seq_idx=True)`, no attention_mask. Without the right kernels, or without these kwargs, the model "quietly" treats the whole batch as one sequence: no error, no warning, tokens leak across samples.
- HF modeling code [full, raw modeling_qwen3_5.py main]: `chunk_gated_delta_rule` receives `cu_seqlens=kwargs.pop("cu_seq_lens_q", None)`. `causal_conv1d_fn` gets the remaining `**kwargs` (so `seq_idx` can reach it). The pure-PyTorch fallback `torch_chunk_gated_delta_rule` ignores `cu_seqlens`. Fast kernels are attached by decorators naming `fla` and `causal_conv1d`; I did not read the selection logic.
- fla supports varlen: `cu_seqlens` of shape [N+1], batch dim must be 1, inputs flattened [snippet, fla/vLLM/NVIDIA API docs]. NVIDIA NeMo Automodel has a Qwen3.5 packing module that builds `cu_seqlens` once per forward and shares it across GatedDeltaNet layers [full, packing.md excerpt]. So packing for this architecture is real and supported, but it is the less trodden path.
- The 16 full-attention layers need a varlen attention kernel for packing: FlashAttention only [full, same HF page]. FlashAttention on sm_120 (RTX PRO 6000) is shaky: reports of stock wheels without sm_120, source builds crashing nvcc on backward kernels, no FA3 Blackwell instantiations, and an unofficial `flash-attn-4-sm120` bundle [snippet, GitHub issues and HF page]. HF's `kernels-community/flash-attn2` prebuilt option exists [full] but I found no statement it ships sm_120 builds.
- Conclusion [estimate]: packing is risky here and its gain over length-bucketed padding is small, because the main gain of packing at 440 tokens/row is bigger matmuls and fewer kernel launches per token, and bucketed micro-batches deliver the same. Do it only if bucketing fails. If done, an equivalence test is mandatory (section 3, step 3).

### 1.2 Liger Kernel

- Upstream README [full, github.com/linkedin/Liger-Kernel]: `apply_liger_kernel_to_qwen3_5` exists, supports RMSNorm, SwiGLU, CrossEntropyLoss and FusedLinearCrossEntropy. Qwen3-Next is NOT listed. So the fused loss is available for our architecture.
- Why it matters with a 248,320 vocab [estimate]: logits for one 2,048-token row are 2,048 x 248,320 x 4 B (fp32 upcast) = 2.0 GB, plus the bf16 copy and the gradient, so 4-6 GB at the longest rows. FLCE computes the loss in chunks and never builds the full logits. Memory saved: 3-6 GB at max_len 2048. Speed: about 5-10% (the LM head is about 1.27B parameters, 4.7% of 27B, and the upcast and softmax are memory-bound). Total expected gain 1.05-1.15x.
- Caveats [estimate]: apply the patch before `from_pretrained`. With `labels` passed, the patched forward returns the loss and no logits. Our `validate()` and training both use `labels`, so fine. Check that `ignore_index=-100` rows (instr kind) give the same loss as the baseline on 20 rows. Check that the patched forward still accepts the extra kwargs if packing is added later.

### 1.3 Attention backend for the 16 full-attention layers

- Keep PyTorch SDPA (default). At 440-token rows, 16 layers of attention are a small share of the time [estimate]. Do not chase FA2/FA3 on sm_120 unless packing is needed.
- Verify the GDN fast path is really on: if `fla` or `causal-conv1d` failed to import, HF silently uses the torch fallback, which is far slower [full: decorators fall back to reference code; HF docs say the same]. 620 tok/s suggests the fast path is on, but print it. The fla Triton kernels also compile and autotune at first use, which makes the first minutes slow [snippet, Unsloth guide]. Never time the first 3-5 steps. NVIDIA reports a faster FlashInfer GDN kernel on Blackwell for inference, not for training [snippet]; not usable for our backward pass.

### 1.4 Gradient checkpointing, micro-batch, torch.compile

- Compute check [estimate]: LoRA with checkpointing costs about 6 x 27B = 162 GFLOP per token (forward + recompute + activation-gradient; no base weight gradients). At 620 tok/s that is about 100 TFLOPS achieved. I did not find a sourced dense bf16 peak for the RTX PRO 6000 here, so I cannot say the MFU. Treat the GPU as probably under-utilised at 440-token rows, not compute-saturated.
- Larger micro-batch is the main lever: batch 1 x 440 tokens gives matmuls with M=440 and many small Triton launches in 48 GDN layers. Several length-sorted rows per micro-batch (2,048-8,192 padded tokens) raise M. Expected 1.15-1.6x, wide range, MEASURE [estimate].
- Turning checkpointing off is not possible at 20 GB spare: activations for a 64-layer 27B at 2K tokens exceed that [estimate]. Selective: leave about 10-16 layers un-checkpointed (set `gradient_checkpointing=False` on those decoder layers; I did not verify the attribute name in transformers 5). Saves at most about 8% [estimate]. Low priority.
- torch.compile: Triton fla kernels and HF's dynamic masks cause graph breaks; HF says even padding-free detection breaks graphs under compile [full]. Expected 0-10% with high risk. Skip.
- LoRA rank 64 vs 128 [estimate]: adapter FLOPs are about 4% of forward at r=128 (about 1B adapter params vs 27B), so r=64 saves only about 3% compute. Its real value is halving the all-reduce, optimizer memory and checkpoint size. Your own note says low rank learns too little in CPT, so keep 128 and use bf16 all-reduce instead.

### 1.5 Other stacks

- Unsloth: claims Qwen3.5 trains 1.5x faster, 50% less VRAM than FA2 setups [snippet, unsloth.ai Qwen3.5 fine-tune page; vendor claim, not independent]. Page says 27B bf16 LoRA needs about 56 GB, needs transformers v5, warns of slow Triton compile. The page says nothing about packing or multi-node for 27B. Swapping stacks costs more than 15 minutes and the 1.5x is versus a different baseline than ours. Not recommended for the main run.
- ms-swift: a PR handles Qwen3-Next packing in Megatron mode [snippet, github.com/modelscope/ms-swift/pull/5859]. No evidence found for the HF-backend path. Skip.
- NeMo Automodel has a Qwen3.5 packing module [full excerpt]. A real alternative for packing, but a full stack change. Skip under the time limit.

## 2. Multi-machine data parallel over TCP

### 2.1 Network facts

- g7e.2xlarge: 50 Gbps, EBS up to 5 Gbps [full, AWS G7e page]. EFA: not on this size [full, AWS EFA page list]. The doc says AWS describes sizes up to 16 vCPU as "up to X Gbps" with baseline plus burst credits [full]; the G7e page row says 50 Gbps without "up to". Unverified which applies. Check with: `aws ec2 describe-instance-types --instance-types g7e.2xlarge --query "InstanceTypes[].NetworkInfo.NetworkCards[]"` (BaselineBandwidthInGbps, command pattern from the AWS bandwidth page [full]).
- Single TCP flow is limited to 5 Gbps outside a cluster placement group and 10 Gbps inside one; ENA Express can give up to 25 Gbps between eligible instances in one AZ [full, AWS bandwidth page]. I did not verify that g7e.2xlarge is ENA-Express eligible. Consequence: use a cluster placement group, one AZ, and NCCL with several sockets so the traffic is several flows.
- Quota: 6 machines x 8 vCPU = 48 G-family vCPUs; check the account quota in that region [estimate, general knowledge].

### 2.2 What is communicated

Only LoRA gradients. Adapter size is 0.9-1.9B parameters (your figure; `print_trainable_parameters` prints the exact number: use it). With N=6 the ring all-reduce moves 2(N-1)/N = 1.67 x size per node, each direction [estimate, standard ring formula].

Time per all-reduce, assuming 3.1 GB/s achieved (50% of 6.25 GB/s line rate) and a worst case of 1.25 GB/s (one 10 Gbps flow) [estimate, both assumptions, measure]:

| adapter params | grad dtype | size | traffic/node | at 3.1 GB/s | worst 1.25 GB/s |
|---|---|---|---|---|---|
| 1.0B | bf16 | 2 GB | 3.3 GB | 1.1 s | 2.7 s |
| 1.0B | fp32 | 4 GB | 6.7 GB | 2.2 s | 5.4 s |
| 1.9B | bf16 | 3.8 GB | 6.3 GB | 2.0 s | 5.1 s |
| 1.9B | fp32 | 7.6 GB | 12.7 GB | 4.1 s | 10.2 s |

Step time per GPU = accum x 440 tokens / tok/s. At 620 tok/s: accum 16 gives 11 s, accum 32 gives 23 s, accum 64 gives 45 s. At about 930 tok/s: accum 32 gives 15 s, accum 64 gives 30 s. Overhead without overlap, 1.9B bf16, typical to worst: accum 32 at 930 tok/s is 13-34%; accum 64 is 7-17%. With 1.0B bf16: accum 64 gives 4-9%. So: accum 48-64 per GPU and bf16 gradient all-reduce. Global batch then is 6 x 64 x 440 = 169K tokens, about 1,600 steps for 275M tokens, fine for CPT with one cosine pass [estimate].

Accumulation without per-micro-batch sync is the documented pattern (`no_sync`, wrapping forward and backward; wrapping only backward was slower than baseline in one report) [snippet, HF Accelerate docs/forum]. I recommend not using DDP at all: accumulate local fp32 `.grad` as the loop does now, then once per step copy grads into chunk buffers of about 256 MB in bf16, `dist.all_reduce` each chunk, divide by world size, copy back. Fewer moving parts than DDP + checkpointing + PEFT, and no `find_unused_parameters` or static-graph questions. Cost: no overlap with backward, which is small anyway because sync happens once per 32-64 micro-batches. DDP's default 25 MB buckets are fine too, but I found no LoRA-specific benchmark [snippet].

Must-do for the manual path: identical adapter init on all ranks (LoRA A is randomly initialised): after `get_peft_model`, `dist.broadcast` every trainable parameter from rank 0 [estimate; DDP does this for you, a manual loop does not]. Same data order seed, each rank takes `order[rank::world]`. Use `init_process_group(timeout=timedelta(minutes=60))` because rank 0 alone validates and saves and the others wait in the next all-reduce (default timeout is shorter). Save adapter on rank 0 only; optimizer state (about 12 GB at r=128 in fp32 Adam) every 2 h, adapter every 30-60 min: a 12 GB write at EBS 5 Gbps is about 20+ s of stall for everyone [estimate].

### 2.3 NCCL settings without EFA

From NCCL docs [snippet]: on AWS `NCCL_NSOCKS_PERTHREAD` defaults to 8 (1 elsewhere); the product of `NCCL_SOCKET_NTHREADS` x `NCCL_NSOCKS_PERTHREAD` is capped at 64; for generic 100G networks, 4 and 4 is suggested; more threads cost CPU (we have 8 vCPU, enough). Suggested start:

```
export NCCL_SOCKET_IFNAME=ens5          # check `ip -br a`; the ENA name on the AMI
export NCCL_IB_DISABLE=1                # no InfiniBand/EFA on this size
export NCCL_NET=Socket                  # skip aws-ofi-nccl probing [estimate: avoids a failed libfabric attempt if the plugin is installed]
export NCCL_SOCKET_NTHREADS=4
export NCCL_NSOCKS_PERTHREAD=4          # try 8x4 too; keep product <= 64
export NCCL_DEBUG=INFO                  # first run only; confirm "NET/Socket" in the log
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
```

Bandwidth test before the real run (10 min, 2 machines): a 100-line torch script that all-reduces a 2 GB bf16 tensor 10 times, reports GB/s; try the NSOCKS grid. Decide accum and bf16 vs fp32 from that number.

### 2.4 Independent shards + averaged LoRA (fallback only)

- Evidence found is indirect, none on continued pre-training [snippet]: longer-trained LoRA experts merge worse than full fine-tuning experts, about 2% lower multi-task accuracy in one setup (arXiv 2506.14126); merged-adapter performance falls as more adapters are merged, TIES slightly ahead of plain averaging (arXiv 2605.28577); concatenation beats averaging for skill composition (LoRA Soups). So there is no evidence that 6 independent CPT shards average cleanly.
- Math reason [estimate]: averaging A and B separately is not the average of the products BA. Average the deltas BA, then re-factor (SVD, rank up to 6 x 128) or merge into the weights.
- Better fallback if the network is slower than hoped: local SGD. Same init, each machine trains alone, and every H=8-16 optimizer steps all machines average the LoRA parameters (A and B directly; they stay close because they restart from the same average) while keeping their own Adam states. This cuts communication H-fold. I did not find a source on its quality for LoRA CPT; it needs a small ablation. Use only if section 3 step 5 shows comm above about 25% of step time.
- The existing single 6000 at our site is not in the AWS VPC: over the internet it cannot join NCCL at useful speed. Use it for evaluation (MezonBench) or the held-out loss, not as a 7th rank [estimate].

## 3. Ordered plan

Test protocol for every step: same 200 rows (`--limit 200`), skip the first 5 optimizer steps (Triton autotune), report tok/s from steps 6-20, peak VRAM, and loss on 20 fixed validation rows against the baseline. Accept a change only if loss matches within about 1e-2 (bf16 noise) and tok/s rises. Each test about 10-15 min including model load (model load itself may take 2-5 min).

Step 0 (about 10 min): instrument `train_cpt.py`. Add `--bench`, per-step timing with `torch.cuda.synchronize()`, tok/s excluding warmup, padded vs trained token counts. Print whether the `fla` and `causal_conv1d` fast paths are active, and the exact trainable parameter count. Also compute from the data: length histogram and the padding fraction a bucketed batch would have. Expected: baseline 620 tok/s reproduced. On AWS: run the `describe-instance-types` call and the 2-node bandwidth test.

Step 1 (about 15 min): Liger. `from liger_kernel.transformers import apply_liger_kernel_to_qwen3_5; apply_liger_kernel_to_qwen3_5(fused_linear_cross_entropy=True, rms_norm=True, swiglu=True)` before `from_pretrained` (argument names to check in the installed version). Expected 620 to about 650-710 tok/s, VRAM down 3-6 GB [estimate]. Check loss equality including the instr rows.

Step 2 (about 1.5 h to write and test): length-bucketed micro-batches. Within shuffled windows of about 512 rows, sort by length, build micro-batches by a token budget (try padded budgets 2,048 / 4,096 / 8,192 and at most 8 rows), right-pad, `attention_mask` standard, labels -100 on padding. Normalise loss by trained tokens across the whole accumulation window (sum of per-token loss / total trained tokens) instead of per-row mean: a deliberate change, better for CPT, but note it changes the weight of short rows. Equivalence test: 8 rows run alone vs the same 8 rows padded in one batch, losses must agree within about 1e-2 and gradients' cosine > 0.99. Right padding is safe for a causal model; GDN layers zero padded states through `apply_mask_to_padding_states` [full, seen in the HF file]. Expected total 620 to about 800-1,000 tok/s [estimate, wide]. Pick the budget with the best tok/s that stays below about 88 GB peak.

Step 3 (only if step 2 gives under about 900 tok/s; 2-3 h): true packing. `DataCollatorWithFlattening(return_flash_attn_kwargs=True, return_seq_idx=True)`, batch 1 of 4-8K tokens, `attn_implementation` a varlen-capable FlashAttention (must first prove it runs on sm_120). Equivalence test mandatory: pack rows A and B, compare per-row loss to A alone and B alone; a mismatch above about 1e-2 means leakage. Also check the Liger patched forward still passes the kwargs. Expected extra 1.0-1.15x over step 2. Risk: high (sm_120 FlashAttention build, silent leakage).

Step 4 (optional, 30 min): selective checkpointing of 10-16 layers using the memory freed by Liger and fewer padded tokens. Expected 1.03-1.08x.

Step 5 (about 2 h to write, 20 min to test on 2 machines): multi-node training. Changes in `train_cpt.py`:
- `dist.init_process_group("nccl", timeout=timedelta(minutes=60))`; `torch.cuda.set_device(0)` (one GPU per machine, `device_map={"": 0}` as now).
- Broadcast adapter parameters from rank 0 after creating them; load the checkpoint on every rank on resume.
- Tokenise once on one machine, save the encoded rows, ship them with the model; each rank reads `order[rank::world]`. Rows per step = accum x world; recompute `total` and warm-up from it.
- After `accum` micro-batches: chunked bf16 `all_reduce` of `.grad`, divide by world size, clip, step. Validation, logging and saving on rank 0 only, followed by `dist.barrier()`.
- Stop by a deadline: `--deadline` in hours; set the cosine total from the measured tok/s after the first 20 minutes so the schedule ends with the run.
Expected: 90-95% scaling if comm is under 10% of the step; target 6 x about 900 = 5,400 tok/s, about 260M tokens in 13.5 h [estimate].

Launch (6 machines, private IPs, node 0 = 10.0.1.10; run the same line on each, changing only `--node_rank`):

```
torchrun --nnodes=6 --nproc_per_node=1 --node_rank=<0..5> \
  --rdzv_backend=c10d --rdzv_endpoint=10.0.1.10:29500 --rdzv_id=cpt1 --max_restarts=0 \
  -m research.train_cpt --model ~/models/Qwen3.8-27B --accum 48 --out ~/cpt_out
```

Network: one cluster placement group, one AZ, one subnet. Security group: a self-referencing rule that allows all TCP (and ICMP) between members of the group. NCCL picks ephemeral ports, so listing only 29500 is not enough [estimate, general NCCL behaviour]. Add TCP 22 from our IP only. Do not open the rendezvous port to the internet.

Risks and checks:
- Bandwidth baseline lower than 50 Gbps, or burst credits running out mid-run: found by the 2-node test run for longer than 60 minutes, not 2 minutes. Fallback: local SGD with H=8-16, or rank 64.
- Straggler: all ranks wait for the slowest; unequal row lengths per rank matter. Bucketing by token budget evens this out. Balance tokens per step across ranks, not rows.
- Rank 0 saving or validating stalls everyone: long NCCL timeout, validation on a small fixed set, checkpoint every 60 min.
- Spot or machine loss: use on-demand; resume needs all ranks and the same world size (state stores `pos`; restart from `latest`).
- Model load: 54 GB bf16 per machine from EBS at up to 5 Gbps is at least 90 s, realistically minutes; an AMI or snapshot restored lazily reads very slowly the first time, so pre-read the volume with `dd` or use fast snapshot restore [estimate, general knowledge].
- Silent packing leakage (step 3): only the equivalence test catches it.
- Liger and PEFT version drift: pin versions after the 15-minute tests and bake them into the AMI.
- Unverified in this research: the exact adapter parameter count, the ENA-Express eligibility of g7e.2xlarge, FlashAttention sm_120 status today, and the Liger argument names in the installed version.

## 4. Expected tokens/s after each step (all [estimate], measure)

| after step | tok/s per GPU | 6-machine tokens in 13.5 h at 0.9 scaling |
|---|---|---|
| baseline | 620 | 163M |
| 1 Liger | 650-710 | 171-186M |
| 2 bucketing | 800-1,000 | 210-262M |
| 3 packing (optional) | 900-1,150 | 236-302M |
| 4 selective ckpt | +3-8% | |

If step 2 lands at about 800, plan on about 210M tokens and set the schedule to that; do not stretch the deadline silently.

## Sources

- AWS G7e instance page: https://aws.amazon.com/ec2/instance-types/g7e/ [full]
- AWS EFA supported instance types: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa.html [full]
- AWS instance network bandwidth (single-flow limits, "up to" and burst): https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-network-bandwidth.html [full]
- HF padding-free training: https://huggingface.co/docs/transformers/en/padding_free [full]
- HF modeling_qwen3_5.py: https://raw.githubusercontent.com/huggingface/transformers/main/src/transformers/models/qwen3_5/modeling_qwen3_5.py [full]
- Liger Kernel README: https://github.com/linkedin/Liger-Kernel [full]
- NeMo Automodel Qwen3.5 packing: https://docs.nvidia.com/nemo/automodel/latest/nemo-automodel/nemo_automodel/components/models/qwen3_5/packing.md [full, partial]
- Unsloth Qwen3.5 fine-tune guide: https://unsloth.ai/docs/models/qwen3.5/fine-tune [full]
- FlashAttention on sm_120 reports: https://github.com/Dao-AILab/flash-attention/issues/1987 and https://huggingface.co/SecondNatureComputing/flash-attn-4-sm120 [snippet]
- NCCL environment variables: https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html [snippet]
- Accelerate gradient synchronization: https://huggingface.co/docs/accelerate/v0.23.0/concept_guides/gradient_synchronization [snippet]
- LoRA merging: https://arxiv.org/pdf/2506.14126 , https://arxiv.org/pdf/2605.28577 , https://preview.aclanthology.org/setup/2025.coling-industry.55 [snippet]
- ms-swift Qwen3-Next packing PR: https://github.com/modelscope/ms-swift/pull/5859 [snippet]
