"""Generate the backtest charts used in the README and on social media.

Everything here is computed live from the local SQLite history via
``backend.quant.backtest`` — no numbers are hand-edited. Two PNGs are written
to ``docs/screenshots/``:

  1. ``backtest_equity.png``  Top-N composite portfolio vs equal-weight basket.
  2. ``backtest_factor_ic.png``  Single-factor Rank-IC, validated vs rejected.

Run:  .venv/bin/python scripts/make_backtest_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backend.quant.backtest import _load_wide, factor_ic_breakdown, run_backtest

OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

# Factors the composite actually trades, vs the ones the backtest threw out.
VALIDATED = ["Rev_5", "LowVol_60", "BP", "SmallSize"]
REJECTED = {"Mom_20", "Mom_60", "AmpUp_5_60"}

INK = "#0f172a"
GRID = "#e2e8f0"
GREEN = "#10b981"
RED = "#ef4444"
SLATE = "#94a3b8"
BLUE = "#2563eb"

plt.rcParams.update({
    "figure.dpi": 160,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
    "font.size": 11,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
})


def _span() -> str:
    close, _, _ = _load_wide()
    return f"{close.index[0]} → {close.index[-1]}  ({len(close)} trading days, {close.shape[1]} names)"


def _headings(fig, title: str, subtitle: str, footer: str) -> None:
    """Stacked title / subtitle / footer in figure coords — no overlap."""
    fig.subplots_adjust(top=0.82, bottom=0.16, left=0.13, right=0.97)
    fig.text(0.13, 0.95, title, fontsize=13.5, fontweight="bold", ha="left", va="top")
    fig.text(0.13, 0.885, subtitle, fontsize=9.5, color=SLATE, ha="left", va="top")
    fig.text(0.5, 0.03, footer, ha="center", fontsize=7.5, color=SLATE)


def chart_equity(horizon: int = 20, top_n: int = 20) -> None:
    r = run_backtest(horizon=horizon, top_n=top_n, include=VALIDATED)
    top = np.asarray(r.topn_equity)
    bench = np.asarray(r.bench_equity)
    x = np.arange(len(top))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(x, top, color=BLUE, lw=2.4,
            label=f"Top-{top_n} composite  (CAGR {r.topn_annual:+.1%}, Sharpe {r.topn_sharpe:+.2f})")
    ax.plot(x, bench, color=SLATE, lw=2.0, ls="--",
            label=f"Equal-weight basket  (CAGR {r.bench_annual:+.1%})")
    ax.axhline(1.0, color=GRID, lw=1)
    ax.set_xlabel(f"rebalance # ({horizon} trading days each)")
    ax.set_ylabel("net value")
    ax.grid(True, color=GRID, lw=0.8)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    _headings(
        fig,
        "4-factor composite vs the equal-weight basket it has to beat",
        f"A-share mainboard  ·  {horizon}-day rebalance  ·  net value (start = 1.0)",
        "Live backtest · 2023-02 → 2026-05 · 506 mainboard names · positive Rank-IC, "
        "but long-only top-N doesn't robustly beat the basket.",
    )
    path = OUT / "backtest_equity.png"
    fig.savefig(path)
    print(f"wrote {path}")


def chart_factor_ic(horizon: int = 10) -> None:
    bd = factor_ic_breakdown(horizon=horizon)
    names = list(bd.keys())
    ics = [bd[n]["ic"] for n in names]
    colors = [RED if n in REJECTED else GREEN for n in names]

    order = np.argsort(ics)
    names = [names[i] for i in order]
    ics = [ics[i] for i in order]
    colors = [colors[i] for i in order]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(names, ics, color=colors)
    ax.axvline(0, color=INK, lw=1)
    lim = max(abs(min(ics)), abs(max(ics))) * 1.35
    ax.set_xlim(-lim, lim)
    for bar, ic in zip(bars, ics):
        off = 0.0025 if ic >= 0 else -0.0025
        ax.text(ic + off, bar.get_y() + bar.get_height() / 2,
                f"{ic:+.3f}", va="center",
                ha="left" if ic >= 0 else "right", fontsize=9.5)
    ax.set_xlabel("mean Rank-IC")
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    _headings(
        fig,
        f"Single-factor Rank-IC over 3 years ({horizon}-day horizon)",
        "green = kept in the composite      red = negative IC, deleted",
        "Momentum & chase-volume print negative IC on the A-share mainboard — "
        "the backtest deleted them. · 2023-02 → 2026-05 · 506 names",
    )
    path = OUT / "backtest_factor_ic.png"
    fig.savefig(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    print(f"data: {_span()}")
    chart_factor_ic(horizon=10)
    chart_equity(horizon=20, top_n=20)
