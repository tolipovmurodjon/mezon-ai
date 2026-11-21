"""Three one-idea charts for the technical deck, from real logs and the benchmark (no jargon on the chart)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from research.train_history import fetch, parse

OR, BK, GR = "#E8590C", "#111111", "#bdbdbd"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15})


def clean(ax):
    ax.spines[["top", "right"]].set_visible(False)


def main():
    # 1. the small model learned the law: mistakes on law text it never saw
    _, held, _ = parse(fetch("cpt_v11.log", False))
    xs = [0, 25, 50, 75, 100]; ys = [d["law"] for _, d in held]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(xs, ys, "-o", color=OR, lw=4, ms=10)
    for x, y in zip(xs, ys):
        ax.text(x, y + .035, f"{y:.2f}", ha="center", fontweight="bold")
    ax.set_xticks(xs, ["start", "25%", "50%", "75%", "done"]); ax.set_ylim(0, 1.05)
    ax.set_ylabel("mistakes (lower = better)"); ax.set_xlabel("how much of the law it has read")
    clean(ax); fig.tight_layout(); fig.savefig("docs/img/deck_1_learned.png", dpi=150); plt.close(fig)

    # 2. it beat Opus from memory
    fig, ax = plt.subplots(figsize=(10, 5.2))
    names, vals, cols = ["Qwen 27B\n(before training)", "Mezon-LM\n(after our training)", "Claude Opus 5.5"], [21, 39, 28], [GR, OR, BK]
    bars = ax.bar(names, vals, color=cols, width=.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + .8, str(v), ha="center", fontsize=22, fontweight="bold")
    ax.set_ylabel("right answers of 147"); ax.set_ylim(0, 46); clean(ax)
    fig.tight_layout(); fig.savefig("docs/img/deck_2_beat_opus.png", dpi=150); plt.close(fig)

    # 3. now the big model, live
    s, _, t = parse(fetch("lawschool_v2.log", True), "train 53,")
    k = 10; ys = [sum(y for _, y in s[max(0, i - k + 1):i + 1]) / len(s[max(0, i - k + 1):i + 1]) for i in range(len(s))]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot([x / t * 100 for x, _ in s], ys, color=OR, lw=4)
    ax.set_xlim(0, 100); ax.set_ylim(0, 1.5)
    ax.set_xlabel("training progress, % (45 million tokens of Uzbek law)"); ax.set_ylabel("mistakes (lower = better)")
    ax.text(s[-1][0] / t * 100 + 1.5, ys[-1], f"now: {ys[-1]:.2f}\n{s[-1][0] / t * 100:.0f}% done", va="center", fontsize=14, fontweight="bold")
    clean(ax); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig("docs/img/deck_3_big_live.png", dpi=150); plt.close(fig)
    print("3 charts written")


if __name__ == "__main__":
    main()
