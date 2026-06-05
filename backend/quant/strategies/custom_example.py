"""Example custom strategy — copy this file to write your own.

Drop any ``.py`` file in this folder that calls ``register(Strategy(...))`` and it
is auto-discovered at import time. No wiring needed: it immediately shows up in

    .venv/bin/python -m backend.quant.backtest --strategy my_reversal
    .venv/bin/python scripts/quant_run_today.py --strategy my_reversal
    GET /api/quant/strategies

A strategy is declarative: pick which *backtest-validated* factors to combine,
how to weight them, and how many names to hold. Available factors (all already
oriented so that "higher = better"):

    Rev_5       short-term reversal      -(5-day return)
    LowVol_60   low volatility           -std(60-day daily returns)
    BP          value                    1 / PB
    SmallSize   small-cap premium        -ln(market cap)
    EP          earnings yield           1 / PE_TTM

Momentum (Mom_20/60) and chase-volume (AmpUp) are intentionally NOT available:
3 years of backtest showed they print *negative* Rank-IC on the A-share
mainboard. See backend/quant/backtest.py.
"""
from __future__ import annotations

from backend.quant.strategies import Strategy, register

register(Strategy(
    name="my_reversal",
    description="Example: short-term reversal, weighted up, plus a low-vol filter.",
    factors=["Rev_5", "LowVol_60", "SmallSize"],
    weights={"Rev_5": 2.0, "LowVol_60": 1.0, "SmallSize": 1.0},
    top_n=15,
))
