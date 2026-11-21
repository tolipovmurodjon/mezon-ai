"""Live chart of the law-school v2 run from its real log (6000): loss per step, smoothed, epoch, LR, speed, held-out.

    .venv/Scripts/python.exe -X utf8 -m research.train_chart [--log PATH]   -> docs/img/lawschool_v2_live.png
"""
import argparse, re, subprocess
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "lawschool_v2_live.png"
STEP = re.compile(r"^step (\d+)/(\d+) loss ([\d.]+) lr ([\d.e+-]+) (\d+) tok/s vram ([\d.]+) GB (\d+) min, ETA (\d+) min")
HELD = re.compile(r"held-out loss (?:before|at step (\d+)): (\{.*\})")


def read_log(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "mezon-6000",
                           "cat ~/mezon/logs/lawschool_v2.log"], capture_output=True, text=True, encoding="utf-8",
                          errors="ignore", timeout=120).stdout


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--log"); a = ap.parse_args()
    raw = read_log(a.log).replace("\r", "\n")
    main_run = raw[raw.rfind("train 53,"):] if "train 53," in raw else raw   # skip the smoke test
    rows, held = [], []
    for line in main_run.splitlines():
        m = STEP.match(line.strip())
        if m:
            rows.append(tuple(float(x) for x in m.groups()))
        h = HELD.search(line)
        if h:
            d = eval(h.group(2), {"__builtins__": {}})  # the trainer prints a plain dict of floats
            held.append((float(h.group(1) or 0), d))
    if not rows:
        raise SystemExit("no step lines yet")
    s = [r[0] for r in rows]; loss = [r[2] for r in rows]; lr = [r[3] for r in rows]; tps = [r[4] for r in rows]
    total = rows[-1][1]; k = 10
    smooth = [sum(loss[max(0, i - k + 1):i + 1]) / len(loss[max(0, i - k + 1):i + 1]) for i in range(len(loss))]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(14, 8))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.1, 1], hspace=0.42, wspace=0.18)
    a0 = fig.add_subplot(gs[0, :])
    a0.plot(s, loss, color="#bbbbbb", lw=1, label="train loss (every 10 steps)")
    a0.plot(s, smooth, color="#E8590C", lw=2.4, label="smoothed (10-point mean)")
    for st, d in held:
        a0.scatter([st], [d.get("law:lessons")], color="#111", zorder=5, s=36)
    if held:
        a0.scatter([], [], color="#111", s=36, label="held-out loss, law lessons (unseen)")
        last = held[-1][1]
        a0.text(0.995, 0.03, "held-out (step %d): " % held[-1][0] + " · ".join(f"{k} {v:.3f}" for k, v in last.items() if k != "step"),
                transform=a0.transAxes, ha="right", fontsize=8.5, color="#333")
    a0.set_xlim(0, total); a0.set_ylabel("loss (lower = better)"); a0.grid(alpha=.25)
    sec = a0.secondary_xaxis("top", functions=(lambda x: x / total, lambda e: e * total)); sec.set_xlabel("epoch")
    a0.set_title(f"Mezon-LM law school v2 · Qwen3.8-27B + LoRA r128 · step {int(s[-1])}/{int(total)} "
                 f"(epoch {s[-1] / total:.2f}) · loss {loss[-1]:.3f} · ETA {int(rows[-1][7]) // 60} h {int(rows[-1][7]) % 60} min",
                 loc="left", fontsize=12.5, fontweight="bold", pad=28)
    a0.legend(loc="upper right", frameon=False)
    b1 = fig.add_subplot(gs[1, 0]); b1.plot(s, lr, color="#111"); b1.ticklabel_format(axis="y", style="sci", scilimits=(0, 0)); b1.set_title("learning rate", loc="left"); b1.grid(alpha=.25)
    b2 = fig.add_subplot(gs[1, 1]); b2.plot(s, tps, color="#111"); b2.set_title("speed, tokens/s (RTX PRO 6000, 96 GB)", loc="left")
    b2.set_ylim(0, max(tps) * 1.2); b2.grid(alpha=.25)
    for b in (b1, b2): b.set_xlabel("step")
    fig.text(0.01, 0.005, "Source: ~/mezon/logs/lawschool_v2.log on mezon-6000 (real trainer output). 45.0M trained tokens, 53,420 rows, "
             "batch accum 16, max-len 3,072. Held-out = 100 unseen rows per group.", fontsize=8.5, color="#444")
    OUT.parent.mkdir(parents=True, exist_ok=True); fig.savefig(OUT, dpi=140)
    print(f"{OUT} · step {int(s[-1])}/{int(total)} · loss {loss[-1]:.4f} · smoothed {smooth[-1]:.4f} · held-out points {len(held)}")


if __name__ == "__main__":
    main()
