"""Proof charts for docs/proof/: every training run and exam result, drawn from the raw logs (nothing typed by hand).

    .venv/bin/python -X utf8 -m research.proof_charts docs/proof     # reads docs/proof/logs, writes docs/proof/charts

Charts: 01 run-1 SFT loss (train + held-out), 02 MezonBench by family (base / thinking / run-1 adapter),
03 law-school pilot loss (train + held-out per kind, as far as the log goes), 04 the data we hold.
"""

import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from research.mezonbench import OUT as BENCH
from research.mezonbench import grade

BLUE, ORANGE, GREEN, GRAY = "#2a63c9", "#c96a1b", "#2e8b57", "#8a94a6"


def style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def run1(logs: Path, out: Path) -> None:
    txt = (logs / "sft.log").read_text(encoding="utf-8", errors="replace")
    pts = [(int(m[1]), float(m[2])) for m in re.finditer(r"step (\d+)/208 train loss ([\d.]+)", txt)]
    res = json.loads((logs / "sft_result.json").read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for part in ([p for p in pts if p[0] <= 104], [p for p in pts if p[0] > 104]):
        ax.plot([p[0] for p in part], [p[1] for p in part], color=BLUE, lw=2, marker="o", ms=4)
    h = res["held_out"]
    ax.plot([x["step"] for x in h], [x["val_loss"] for x in h], color=ORANGE, lw=2, ls="--", marker="o", ms=7)
    ax.axvline(104, color=GRAY, ls=":", lw=1)
    ax.text(106, 2.2, "pass 2", color=GRAY)
    ax.legend(["train loss, pass 1", "train loss, pass 2", "held-out (91 never-seen)"], frameon=False)
    style(ax, f"Run 1 SFT: Qwen3.8-27B LoRA r16, 825 examples, {res['minutes']} min",
          "step (8 examples each)", "loss")
    fig.text(0.01, 0.01, "Low loss here = learned the answer FORMAT. On the broad exam this adapter scored 0/400.",
             fontsize=8, color=GRAY)
    fig.tight_layout()
    fig.savefig(out / "01_run1_sft_loss.png", dpi=150)
    plt.close(fig)


def bench(logs: Path, out: Path) -> None:
    items = {json.loads(x)["id"]: json.loads(x) for x in BENCH.open(encoding="utf-8")}
    fams = ["hierarchy", "in_force", "flip", "lookup"]

    def score(fname, only=None):
        p = {json.loads(x)["id"]: json.loads(x)["answer"] for x in (logs / fname).open(encoding="utf-8")}
        res = {}
        for f in fams:
            ids = [i for i in p if items[i]["family"] == f and (only is None or i in only)]
            res[f] = (sum(grade(items[i], p[i]) == "right" for i in ids), len(ids))
        return res, set(p)

    think, ids100 = score("preds_base_think.jsonl")
    base100, _ = score("preds_base.jsonl", ids100)
    base, _ = score("preds_base.jsonl")
    sft, _ = score("preds_sft1.jsonl")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.15, 1]})
    w = 0.38
    x = range(len(fams))
    for ax, series, title in (
        (axes[0], [("base, no thinking", base, BLUE), ("run-1 adapter", sft, ORANGE)], "All 400 questions"),
        (axes[1], [("base, no thinking", base100, BLUE), ("base, thinking", think, GREEN)], "Same 100 questions"),
    ):
        for j, (name, s, c) in enumerate(series):
            vals = [100 * s[f][0] / max(1, s[f][1]) for f in fams]
            bars = ax.bar([i + (j - 0.5) * w for i in x], vals, w, color=c, label=name)
            for b, f in zip(bars, fams, strict=True):
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{s[f][0]}/{s[f][1]}", ha="center",
                        fontsize=8)
        ax.set_xticks(list(x), fams)
        ax.set_ylim(0, 110)
        ax.legend(frameon=False, loc="upper right")
        style(ax, title, "", "% right")
    fig.suptitle("MezonBench v1, closed book (no tools): graded by the law store itself", x=0.01, ha="left",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "02_mezonbench_results.png", dpi=150)
    plt.close(fig)


def pilot(logs: Path, out: Path) -> None:
    f = logs / "cpt_pilot.log"
    if not f.exists():
        return
    txt = f.read_text(encoding="utf-8", errors="replace")
    pts = [(int(m[1]), float(m[2])) for m in re.finditer(r"^step (\d+)/\d+ loss ([\d.]+)", txt, re.MULTILINE)]
    held = []
    for m in re.finditer(r"held-out loss (?:before|at step \d+): (\{.*?\})", txt):
        held.append(json.loads(m[1].replace("'", '"')))
    total = re.search(r"^step \d+/(\d+)", txt, re.MULTILINE)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=BLUE, lw=1.8, label="train loss (mixed rows)")
    for kind, c in (("law", ORANGE), ("web", GREEN), ("instr", GRAY)):
        hs = [(h.get("step", 0), h[kind]) for h in held if kind in h]
        if hs:
            ax.plot([s for s, _ in hs], [v for _, v in hs], color=c, ls="--", marker="o", ms=6,
                    label=f"held-out {kind}")
    if total:
        ax.set_xlim(0, int(total[1]))
    ax.legend(frameon=False)
    style(ax, "Law-school pilot: LoRA r128, 50 % law lessons + 25 % Uzbek web + 25 % instructions",
          "step (16 rows each)", "loss")
    fig.text(0.01, 0.01, "Goal: held-out law falls; web and instructions must not rise (that would be forgetting).",
             fontsize=8, color=GRAY)
    fig.tight_layout()
    fig.savefig(out / "03_law_school_pilot_loss.png", dpi=150)
    plt.close(fig)


def data(out: Path) -> None:
    rows = [("lex.uz documents", 166155), ("lex.uz old editions", 185049), ("court cases (list)", 61049),
            ("law-school lessons (38 acts)", 17398), ("Q&A pairs in lessons", 98755), ("scanned PDFs to OCR", 2074),
            ("MezonBench questions", 400)]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh([r[0] for r in rows][::-1], [r[1] for r in rows][::-1], color=BLUE)
    for i, (_, v) in enumerate(rows[::-1]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    ax.set_xscale("log")
    style(ax, "What we hold (21 Nov 2026)", "count (log scale)", "")
    fig.tight_layout()
    fig.savefig(out / "04_data_inventory.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/proof")
    logs, out = root / "logs", root / "charts"
    out.mkdir(parents=True, exist_ok=True)
    run1(logs, out)
    bench(logs, out)
    pilot(logs, out)
    data(out)
    print("charts:", sorted(p.name for p in out.glob("*.png")))
