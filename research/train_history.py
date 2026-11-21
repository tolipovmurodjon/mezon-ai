"""All Mezon-LM training runs from their real logs (6000): small model (38-law school + internship) and the big run.

    python -X utf8 -m research.train_history   -> docs/img/training_history.png
"""
import ast, re, subprocess
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "training_history.png"
CACHE = ROOT / "data" / "interim" / "train_logs"
STEP = re.compile(r"^step (\d+)/(\d+) loss ([\d.]+)")
HELD = re.compile(r"held-out loss (?:before|at step (\d+)): (\{.*\})")
OR, BK, GR = "#E8590C", "#111111", "#9a9a9a"


def fetch(name: str, live: bool) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / name
    if live or not f.exists():
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "mezon-6000", f"cat ~/mezon/logs/{name}"],
                           capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=180)
        if r.stdout:
            f.write_text(r.stdout, encoding="utf-8")
    return f.read_text(encoding="utf-8", errors="ignore").replace("\r", "\n")


def parse(raw: str, marker: str | None = None):
    if marker and marker in raw:
        raw = raw[raw.rfind(marker):]
    steps, held, total = [], [], None
    for line in raw.splitlines():
        m = STEP.match(line.strip())
        if m:
            steps.append((int(m[1]), float(m[3]))); total = int(m[2])
        h = HELD.search(line)
        if h:
            held.append((int(h[1] or 0), ast.literal_eval(h[2])))
    return steps, held, total


def main() -> None:
    v11 = parse(fetch("cpt_v11.log", False))
    ch1 = parse(fetch("chain.log", False))
    big = parse(fetch("lawschool_v2.log", True), "train 53,")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5})
    fig = plt.figure(figsize=(16, 8.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], hspace=0.55, wspace=0.28)

    def held_lines(ax, held, keys, colors, total):
        for k, c in zip(keys, colors):
            pts = [(s / total if total else s, d[k]) for s, d in held if k in d]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=c, lw=2, ms=5, label=f"held-out · {k}")
            ax.annotate(f"{pts[0][1]:.2f}→{pts[-1][1]:.2f}", pts[-1], textcoords="offset points", xytext=(6, -3 + 9 * keys.index(k) * (1 if k != keys[0] else 0) - (8 if k == keys[0] else 0)), fontsize=8.5, color=c)

    # 1. small model, stage 1: law school v1.1 on the 38-act law store
    s, h, t = v11
    a = fig.add_subplot(gs[0, 0])
    a.plot([x / t for x, _ in s], [y for _, y in s], color=GR, lw=1, label="train loss")
    held_lines(a, h, ["law", "instr", "web"], [OR, BK, GR], t)
    a.set_title("SMALL MODEL · stage 1: law school v1.1\n38 core acts, every edition · 7.2M tokens · 992 steps", loc="left", fontsize=10.5, fontweight="bold")
    a.set_xlabel("epoch"); a.set_ylabel("loss"); a.grid(alpha=.25); a.legend(frameon=False, fontsize=8)

    # 2. small model, stage 2: internship on top (chain v1 = the model that beat Opus closed-book 39 vs 28)
    s, h, t = ch1
    b = fig.add_subplot(gs[0, 1])
    held_lines(b, h, ["legal", "audit_dev", "replay"], [OR, BK, GR], t)
    b.set_title("SMALL MODEL · stage 2: internship (chain v1)\nlaw-tool sessions · 0.16M tokens · 36 steps", loc="left", fontsize=10.5, fontweight="bold")
    b.set_xlabel("epoch"); b.grid(alpha=.25); b.legend(frameon=False, fontsize=8)

    # 3. what the small model achieved
    c = fig.add_subplot(gs[0, 2])
    names = ["base Qwen", "Mezon-LM\n(chain v1)", "Opus 5.5"]; vals = [21, 39, 28]
    bars = c.bar(names, vals, color=[GR, OR, BK], width=.6)
    for bb, v in zip(bars, vals):
        c.text(bb.get_x() + bb.get_width() / 2, v + .8, str(v), ha="center", fontweight="bold")
    c.set_title("Result: right answers from memory\nsame 147 hard questions (MezonBench v2.2)", loc="left", fontsize=10.5, fontweight="bold")
    c.set_ylim(0, 48); c.spines[["top", "right"]].set_visible(False)

    # 4. big model, now: law school v2 on the full corpus
    s, h, t = big
    d = fig.add_subplot(gs[1, :2])
    k = 10
    sm = [sum(y for _, y in s[max(0, i - k + 1):i + 1]) / len(s[max(0, i - k + 1):i + 1]) for i in range(len(s))]
    d.plot([x / t for x, _ in s], [y for _, y in s], color=GR, lw=1, label="train loss")
    d.plot([x / t for x, _ in s], sm, color=OR, lw=2.4, label="smoothed")
    for st, dd in h:
        d.scatter([st / t], [dd.get("law:lessons")], color=BK, s=34, zorder=5)
    d.scatter([], [], color=BK, s=34, label="held-out · law lessons")
    d.set_xlim(0, 1); d.set_xlabel("epoch"); d.set_ylabel("loss"); d.grid(alpha=.25); d.legend(frameon=False, fontsize=8.5)
    d.set_title(f"BIG MODEL · law school v2, running now · full corpus, 45.0M tokens" + chr(10) + f"step {s[-1][0]}/{t} · epoch {s[-1][0] / t:.2f} · loss {sm[-1]:.2f}",
                loc="left", fontsize=10.5, fontweight="bold")

    # 5. scale: tokens per run
    e = fig.add_subplot(gs[1, 2])
    runs = ["law school v1.1\n(small)", "internship\n(small)", "law school v2\n(big)"]; tok = [7.23, 0.16, 45.03]
    bars = e.barh(runs, tok, color=[BK, BK, OR], height=.55)
    for bb, v in zip(bars, tok):
        e.text(v + .8, bb.get_y() + bb.get_height() / 2, f"{v:g}M", va="center", fontweight="bold")
    e.invert_yaxis(); e.set_xlim(0, 55); e.set_title("Trained tokens per run" + chr(10) + "(the big run reads 6x more)", loc="left", fontsize=10.5, fontweight="bold")
    e.spines[["top", "right"]].set_visible(False)

    fig.text(0.01, 0.005, "Source: trainer logs on the training GPU (cpt_v11.log, chain.log, lawschool_v2.log). Held-out = rows never trained on. "
             "Qwen3.8-27B + LoRA, one RTX PRO 6000 (96 GB). Benchmark: data/bench/mezonbench_v2_2.jsonl, research/headline.py.", fontsize=8, color="#444")
    OUT.parent.mkdir(parents=True, exist_ok=True); fig.savefig(OUT, dpi=140, bbox_inches="tight")
    print(OUT, "| v1.1 law held-out", h and "", f"| big step {s[-1][0]}/{t}")


if __name__ == "__main__":
    main()
