# Renting 8 × RTX PRO 6000 on Nebius for the full law school: step by step

Written 21 Nov 2026. Price from docs/research/gpu_prices.md: **8 × RTX PRO 6000 ≈ $14.40/h (≈ $346 per day)**,
billed hourly (confirm on Nebius before ordering; stock is not guaranteed). Steps marked **[Boss]** are yours (account,
payment, passwords). Steps marked **[Claude]** I do once you give me the SSH address.

---

## Part A: before you order (do these first)

1. **Wait for the pilot exam result** (~1 h). Rent only if the law school helps (taught-half scores go up).
2. **[Claude]** Make training ~2× faster on our own 6000 first (packing, faster kernels) and make it multi-GPU
   (8 cards on one machine, PyTorch `torchrun`). Every hour saved here saves ~$14 later.
3. **[Claude]** Run the full refinery on the L40S → the full law-school dataset, uploaded to R2. The rented machine
   should start training the minute it's ready, not wait for data.

## Part B: order the machine **[Boss]**

1. Create a Nebius AI Cloud account (nebius.com) and add a payment method. Check the hourly price shown for
   **8 × NVIDIA RTX PRO 6000 Blackwell** and the region (data location; EU or US both fine for public lex.uz text).
2. Create an **SSH key pair on the laptop** (once), in Git Bash:
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/nebius_mezon -C mezon
   ```
   Paste the content of `~/.ssh/nebius_mezon.pub` (the .pub file only, never the other one) into Nebius when it
   asks for an SSH key.
3. Create the virtual machine:
   - GPUs: **8 × RTX PRO 6000** (one VM with all 8).
   - Image: **Ubuntu 22.04 with NVIDIA drivers / CUDA** (Nebius offers GPU-ready images).
   - Boot disk: **500 GB** or more (model 56 GB + data + checkpoints).
   - Public IP: yes; SSH allowed only from your IP if the console offers it.
4. Send me: **the public IP and the user name** (often `ubuntu`). Nothing else: no passwords, no API keys in chat.

## Part C: setup on the machine **[Claude]** (~30-45 min)

1. Add `Host mezon-nebius` to `~/.ssh/config` (IP, user, key `~/.ssh/nebius_mezon`). Check `nvidia-smi` shows 8 GPUs.
2. Copy from R2 (fast, data-centre to data-centre): the model `Qwen3.8-27B`, the law-school dataset, the code.
   R2 keys are piped in unseen, never printed.
3. Install the training environment (same versions as the 6000: torch with Blackwell support, transformers, peft,
   flash-linear-attention, causal-conv1d) and run a **10-minute smoke test on 8 GPUs** (speed in tokens/s).
4. Start the run in tmux with checkpoints every 30 min copied to R2 (so nothing is lost if the machine stops).

## Part D: the run and the bill

1. Training: the smart 300M tokens ≈ 19 h on 8 × RTX PRO 6000 (estimate, from 620 tok/s per card; the smoke test
   gives the real number). Full ~1B ≈ 2.5-3 days.
2. **MezonBench after each stage**, on the machine itself.
3. When done: final adapter → R2 and our 6000, then **you delete the VM in the Nebius console** (billing stops only
   when it's deleted/stopped). I'll tell you the exact moment.
4. Cost control: I report the running cost every few hours; you can stop it any time.

## What never goes there
- No secrets in chat, no passwords typed by me. The R2 key is piped unseen.
- Citizens' names are masked by the refinery before any data leaves our boxes.
- The golden exam cases and the "unseen" exam half never go into the training data.
