# 8-GPU rental prices for a ~24 h LoRA fine-tune of a 27B model

Date seen: 2026-11-21 (all fetches that day). Prices are list prices in USD, before tax. "EST" = my own estimate, not a published number. Anything marked "not verified" could not be confirmed.

## 1. Price table (one 8-GPU machine)

| Option | $/hour (machine) | 24 h cost | Source (seen 2026-11-21) | Notes |
|---|---|---|---|---|
| AWS g7e.48xlarge, 8x RTX PRO 6000 Blackwell (96 GB each, 768 GB), us-east-1 on-demand | 33.144 | 795 | https://instances.vantage.sh/aws/ec2/g7e.48xlarge (updated 2026-11-20); same $33.1443 at https://calculator.holori.com/aws/ec2/g7e.48xlarge | Name and 8 GPUs confirmed at https://aws.amazon.com/ec2/instance-types/g7e/ (192 vCPU, 2048 GiB, 1600 Gbps). AWS page shows no price. us-west-2 price and availability: not verified. |
| g7e.48xlarge spot | 18.79 (Vantage); 12.5-12.6 (older trackers) | 451 / ~300 | https://instances.vantage.sh/aws/ec2/g7e.48xlarge | Can be interrupted. Region not stated: not verified. |
| AWS p5.48xlarge, 8x H100, on-demand | 55.04 | 1,321 | https://instances.vantage.sh/aws/ec2/p5.48xlarge | Shown for "us-east-1 and us-west-2", not split: not verified per region. Spot 30.58. |
| AWS p5en.48xlarge, 8x H200, on-demand | 63.296 | 1,519 | https://instances.vantage.sh/aws/ec2/p5en.48xlarge (updated 2026-11-20) | Spot 38.34. Region split not verified. |
| AWS p6-b200.48xlarge, 8x B200, on-demand | 113.933 | 2,734 | https://instances.vantage.sh/aws/ec2/p6-b200.48xlarge | Spot 63.71. Region split not verified. |
| AWS Capacity Block p5.48xlarge (H100), us-east-1 and us-west-2 | 47.757 | 1,146 | https://aws.amazon.com/ec2/capacityblocks/pricing/ | $5.970 per GPU-hour. |
| AWS Capacity Block p5en.48xlarge (H200), both regions | 63.158 | 1,516 | same | $7.895 per GPU-hour. |
| AWS Capacity Block p6-b200.48xlarge (B200), both regions | 113.666 | 2,728 | same | $14.208 per GPU-hour. Page says next price update January 2027. |
| AWS Capacity Block for g7e | not offered | n/a | https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-using.html | g7e is not in the supported instance list. |
| Lambda 8x B200 (HGX, 180 GB each) | 61.52 ($7.69/GPU) | 1,476 | https://lambda.com/pricing | Self-serve, "deploys in minutes", no minimum stated, 22 TiB SSD included. Stock: not verified. |
| Lambda 8x H100 | 36.72 ($4.59/GPU) | 881 | same | 8x H200 not on the page: not verified. |
| RunPod Clusters (no commitment, up to 64 GPUs) | H100 SXM 38.32; H200 50.80; B200 76.72 | 920 / 1,219 / 1,841 | https://www.runpod.io/pricing | $4.79 / $6.35 / $9.59 per GPU-hour. Pods: RTX PRO 6000 $2.69/GPU (21.52 for 8), H200 $5.29, B200 $7.99; 8-GPU pod stock not verified (aggregator says RunPod 8x RTX PRO 6000 is reserved/custom only). The page structured data shows lower "community" rates (RTX PRO 6000 $1.69): not verified. Storage: volume disk $0.10/GB-month running, network storage $0.07/GB-month. |
| CoreWeave 8x RTX PRO 6000 Blackwell (High Memory), US | 20.00 | 480 | https://www.coreweave.com/pricing | Spot 11.09 ($266 per 24 h). Standard-memory variant: contact sales. Europe on-demand also 20.00. |
| CoreWeave 8x H100 / H200 / B200, US on-demand | 49.24 / 50.44 / 68.80 | 1,182 / 1,211 / 1,651 | same | Spot 19.71 / 20.93 / 34.11. Self-serve today: not verified. |
| Nebius per GPU: H100 $4.50, H200 $5.40, B200 $8.50, B300 $9.50, RTX PRO 6000 $1.80 | 8x: 36.00 / 43.20 / 68.00 / 76.00 / 14.40 | 864 / 1,037 / 1,632 / 1,824 / 346 | https://nebius.com/prices | Preemptible from $0.79-0.99/GPU. Region and 8-GPU self-serve limits are not on the page: not verified. |
| Together.ai clusters per GPU: H100 $3.99, H200 $5.99, B200 $9.29 | 31.92 / 47.92 / 74.32 | 766 / 1,150 / 1,784 | https://www.together.ai/pricing | Preemptible H100 1.99, H200 2.99, B200 4.65. Reserved 3-30 days is cheaper (3.69 / 4.99 / 8.69). Capacity today: not verified. |
| Google Cloud a3-ultragpu-8g (8x H200) | on-demand ~84.81; Flex-start 42.40; calendar 59.36 | 2,035 / 1,018 / 1,425 | Localized official pages via https://cloud.google.com/products/compute/pricing/accelerator-optimized and https://cloud.google.com/products/dws/pricing (read from search snippets; the page itself did not render for me) | us-central1 split not verified. A spot figure of ~6.1-6.3 on trackers looks implausible: not verified. |
| Azure Standard_ND96isr_H200_v5 (8x H200) | 84.80 (East US 2, Linux PAYG); other trackers 106-121 | 2,035 | https://www.azurespeed.com/AzureVmPricing/Standard_ND96isr_H200_v5 (third-party copy of Azure retail prices) | Quota and stock: not verified. |
| Vast.ai | no 8-GPU quote found | n/a | https://markaicode.com/pricing/vast-ai-pricing/ (2026-11-16), https://computeprices.com/providers/vast/gpus/rtx-pro-6000 | Marketplace, host-set prices. H200 median about $5.25/GPU-h (one tracker) vs $3.85 (another). RTX PRO 6000 from about $1.20-1.53/GPU-h. Multi-GPU rows often show per-GPU price. Host location varies, so not suitable if data must stay private. 8-GPU stock: not verified. |
| Hyperbolic | not verified | n/a | https://www.hyperbolic.ai/pricing returned 404 | |
| Other 8x RTX PRO 6000 (aggregator, 2026-11-20) | Lium 12.80; GPUhub 11.02; GPU.ai 14.40; EcoHash 15.12; Runcrate 18.32; Verda spot 11.92 (on-demand $2.98/GPU = 23.84); Exoscale 15.97; Oracle 36.00; Lightning 37.04; Latitude 48.00 (out of stock) | 265-1,150 | https://getdeploying.com/reference/cloud-gpu/nvidia-rtx-pro-6000 | Aggregator list rates. Marked in stock: Lium, GPUhub, GPU.ai, EcoHash, Runcrate. Out of stock: Geodd, UpCloud. Small providers: vet them; data sits on their machines. Akamai announced 8-card RTX PRO 6000 instances on 2026-07-31, no price: https://techdocs.akamai.com/cloud-computing/changelog/july-31-2026-nvidia-rtx-pro-6000-blackwell-8-card-gpu-instances |

Storage and egress: Lambda includes 22 TiB SSD on 8x nodes (egress: not verified). RunPod storage as above. AWS egress and EBS: not fetched, not verified.

## 2. AWS rules

- Capacity Blocks (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-purchase.html, capacity-blocks-using.html): duration in 1-day steps up to 14 days, so 1 day can be booked. Offerings can start in as little as 30 minutes, up to 8 weeks ahead. Every block ends 11:30 UTC; termination starts 11:00 UTC. Prepaid, cancellation is not allowed. First come, first served; availability on a given day: not verified. Supported: p5, p5e, p5en, p6-b200, p6-b300. Not g7e.
- Quotas (https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html): all default 0 and adjustable. g7e needs "Running On-Demand G and VT instances" (L-DB2E81BA) of at least 192 vCPU; for spot, "All G and VT Spot Instance Requests" (L-3819A6DF). p5/p5en/p6 need "Running On-Demand P instances" (L-417A185B) of at least 192 vCPU; spot "All P Spot Instance Requests" (L-7212CCBC). Capacity Blocks have their own quotas, for example "Concurrent P5 Capacity Blocks per account" (L-DA6814F2) and P5en (L-4F9BB70B), default 0; instances inside a block do not count against on-demand limits. A B200 block quota was not listed: not verified.
- Typical approval time: not documented on the pages I fetched, so not verified. Request it now.

## 3. Relative speed

Fetched: NVIDIA page for RTX PRO 6000 Server Edition lists 96 GB GDDR7, 1,597 GB/s, BF16 "1 PFLOP" without a dense/sparse label, PCIe Gen 5, no NVLink, up to 600 W (https://www.nvidia.com/en-us/data-center/rtx-pro-6000-blackwell-server-edition/). NVIDIA usually quotes sparse numbers, so dense BF16 is probably about half, around 500 TFLOPS (EST, not verified). AWS confirms H100 80 GB and "up to 900 GB/s NVSwitch" per instance (https://aws.amazon.com/ec2/instance-types/p5/).

From my memory of NVIDIA datasheets, not fetched this session (not verified): H100/H200 SXM dense BF16 about 989 TFLOPS, NVLink 900 GB/s, HBM3 3.35 TB/s (H100) and HBM3e 4.8 TB/s with 141 GB (H200); B200 about 2,250 TFLOPS dense BF16, 180 GB, about 8 TB/s, NVLink 1.8 TB/s.

What it means (all EST):
- LoRA on a 27B model with gradient checkpointing costs about 6 x 27e9 = 162 GFLOP per token (forward, recompute, activation gradient; no base-weight gradients). Our 620 tok/s is about 100 TFLOPS, roughly 20 % of a 500 TFLOPS dense card. The run is unoptimised and has headroom.
- No NVLink is not a blocker for LoRA. With DDP each GPU holds the 27B bf16 weights (about 54 GB) plus adapters and activations inside 96 GB, and only adapter gradients cross PCIe (r128 adapters are well under 1 GB per step). I assume 85-95 % scaling; measure it. FSDP or full fine-tuning would suffer on PCIe, but we are not doing that.
- Per-GPU speed assumed relative to RTX PRO 6000 with the same code: H100 about 2.0x, H200 about 2.2x, B200 about 4x. These are my guesses from dense TFLOPS and bandwidth ratios. A 10-minute benchmark on the rented box will replace them.

## 4. Time and cost for 300M tokens (EST)

One card: 300M / 620 = 483,871 s = 134 GPU-hours. Assumes 90 % multi-GPU scaling, ignores 1-2 h of setup and model download.

| 8-GPU machine | Assumed tok/s | Hours for 300M | Price used ($/h) | Cost to finish | Cost for full 24 h |
|---|---|---|---|---|---|
| 8x RTX PRO 6000 (620 x 8 x 0.9), AWS g7e | 4,464 | 18.7 | 33.144 | 620 | 795 |
| same, CoreWeave HM | 4,464 | 18.7 | 20.00 | 374 | 480 |
| same, Nebius | 4,464 | 18.7 | 14.40 | 269 | 346 |
| 8x H100 (2.0x), Lambda | 8,928 | 9.3 | 36.72 | 343 | 881 |
| 8x H100, AWS Capacity Block (1 day minimum) | 8,928 | 9.3 | 47.757 | 1,146 (prepaid 24 h) | 1,146 |
| 8x H200 (2.2x), Nebius | 9,821 | 8.5 | 43.20 | 367 | 1,037 |
| 8x B200 (4x), Lambda | 17,856 | 4.7 | 61.52 | 289 | 1,476 |
| 8x B200, Nebius / CoreWeave | 17,856 | 4.7 | 68.00 / 68.80 | 320 / 323 | 1,632 / 1,651 |
| 8x B200, AWS p6 on-demand | 17,856 | 4.7 | 113.933 | 535 | 2,734 |

## 5. Recommendation (scaling is assumed; benchmark first)

Fastest for about 1 day under about $1,000: 8x B200 on Lambda ($61.52/h) or Nebius ($68/h), billed hourly, not as a 24 h reservation. 300M tokens in about 5 h (EST) costs about $300-$350. At half the assumed speed it is about 10 h and about $620-$680. Lambda B200 for 16 h is $984. If B200 stock is missing, 8x H100 on Lambda ($36.72/h, about 9 h, about $340) is the fallback. Skip AWS Capacity Blocks: a 1-day H100 block is $1,146, B200 is $2,728, and blocks cannot be cancelled.

Cheapest that finishes 300M tokens in about 1 day: 8x RTX PRO 6000 at our measured speed, about 19 h (EST at 90 % scaling; about 21 h at 80 %). Cheapest verified: Nebius ($14.40/h, about $270-$310 for the run) and CoreWeave HM on-demand ($20/h, about $375-$420); CoreWeave spot is $11.09/h but can be preempted. Several small providers list $11-15/h (not verified, vet them). On AWS, g7e.48xlarge on-demand is $33.144/h, about $620-$700 for the run, but the quota defaults to 0 and approval time is not documented. Slack is thin at 19 h: one failed run breaks the 1-day window, which is why I would still pick H100 or B200 billed hourly.

Caveat: stock, region and minimums at Lambda, Nebius, CoreWeave and Together were not confirmed for today. No sign-ups or forms were used; nothing was ordered.
