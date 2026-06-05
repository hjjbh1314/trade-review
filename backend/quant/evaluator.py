"""策略绩效归因。

从 trades 表里挑出量化生成的单 (reason LIKE '[quant:...]')，
配对 buy/sell，算每条策略的：胜率、平均收益、夏普、最大回撤。
对未平仓的 buy 用最新收盘价做"浮动盈亏"。
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from backend.db.repo import _connect
from backend.quant.paper_trader import TAG_PREFIX


_STRAT_RE = re.compile(r"\[quant:([^\]]+)\]")


@dataclass
class StrategyPerf:
    strategy: str
    n_open: int
    n_closed: int
    win_rate: float
    avg_return: float
    sharpe: float
    max_drawdown: float


def _latest_close(symbol: str) -> float | None:
    with _connect() as c:
        row = c.execute(
            """SELECT close FROM daily_quotes
               WHERE symbol = ? AND adjust = 'hfq'
               ORDER BY trade_date DESC LIMIT 1""",
            (symbol,),
        ).fetchone()
        return float(row["close"]) if row else None


def evaluate_all() -> list[StrategyPerf]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE reason LIKE ? ORDER BY symbol, trade_time",
            (f"{TAG_PREFIX}%",),
        ).fetchall()
    trades = [dict(r) for r in rows]
    if not trades:
        return []

    by_strat: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        m = _STRAT_RE.search(t.get("reason") or "")
        if not m:
            continue
        by_strat[m.group(1)].append(t)

    out: list[StrategyPerf] = []
    for strat, ts in by_strat.items():
        rets, open_n = _pair_returns(ts)
        if not rets:
            out.append(StrategyPerf(strat, n_open=open_n, n_closed=0,
                                     win_rate=0.0, avg_return=0.0,
                                     sharpe=0.0, max_drawdown=0.0))
            continue
        arr = np.array(rets, dtype="float64")
        win = float((arr > 0).mean())
        mu = float(arr.mean())
        sd = float(arr.std(ddof=0))
        sharpe = (mu / sd * math.sqrt(252)) if sd > 0 else 0.0
        equity = np.cumprod(1.0 + arr)
        peak = np.maximum.accumulate(equity)
        dd = float(((equity - peak) / peak).min()) if len(equity) else 0.0
        out.append(StrategyPerf(
            strategy=strat, n_open=open_n, n_closed=len(rets),
            win_rate=win, avg_return=mu, sharpe=sharpe, max_drawdown=dd,
        ))
    return out


def _pair_returns(ts: list[dict]) -> tuple[list[float], int]:
    """同 symbol 内按时间顺序 FIFO 配对 buy/sell。
    未平仓 buy 用最新收盘价算浮盈,但不进 closed return 序列。"""
    by_sym: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        by_sym[t["symbol"]].append(t)

    closed: list[float] = []
    open_n = 0
    for sym, lst in by_sym.items():
        buys: list[dict] = []
        for t in lst:
            if t["action"] == "buy":
                buys.append(t)
            elif t["action"] == "sell" and buys:
                b = buys.pop(0)
                ret = (t["price"] - b["price"]) / b["price"]
                closed.append(ret)
        open_n += len(buys)
    return closed, open_n


def persist_performance(perfs: list[StrategyPerf], eval_date: str | None = None) -> int:
    eval_date = eval_date or date.today().strftime("%Y-%m-%d")
    rows = [{
        "strategy": p.strategy,
        "eval_date": eval_date,
        "n_trades": p.n_closed,
        "win_rate": p.win_rate,
        "avg_return": p.avg_return,
        "sharpe": p.sharpe,
        "max_drawdown": p.max_drawdown,
        "metrics_json": json.dumps({"n_open": p.n_open}, ensure_ascii=False),
    } for p in perfs]
    with _connect() as c:
        c.executemany(
            """INSERT OR REPLACE INTO strategy_performance
               (strategy, eval_date, n_trades, win_rate, avg_return,
                sharpe, max_drawdown, metrics_json)
               VALUES (:strategy, :eval_date, :n_trades, :win_rate, :avg_return,
                       :sharpe, :max_drawdown, :metrics_json)""",
            rows,
        )
        c.commit()
    return len(rows)


def floating_pnl_open_positions() -> list[dict[str, Any]]:
    """未平仓量化单的浮动盈亏。前端展示用。"""
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE reason LIKE ? AND action = 'buy' ORDER BY trade_time",
            (f"{TAG_PREFIX}%",),
        ).fetchall()
    buys = [dict(r) for r in rows]
    with _connect() as c:
        sells = c.execute(
            "SELECT symbol FROM trades WHERE reason LIKE ? AND action = 'sell'",
            (f"{TAG_PREFIX}%",),
        ).fetchall()
    sold_set = {s["symbol"] for s in sells}
    out = []
    for b in buys:
        if b["symbol"] in sold_set:
            continue
        last = _latest_close(b["symbol"])
        if not last:
            continue
        pnl = (last - b["price"]) / b["price"]
        out.append({
            "trade_id": b["id"],
            "symbol": b["symbol"],
            "name": b.get("name"),
            "buy_price": b["price"],
            "last_close": last,
            "pct": pnl,
            "reason": b.get("reason"),
            "trade_time": b["trade_time"],
        })
    return out


if __name__ == "__main__":
    perfs = evaluate_all()
    if not perfs:
        print("[evaluator] 没有量化交易记录")
    else:
        for p in perfs:
            print(f"  {p.strategy}: closed={p.n_closed} open={p.n_open} "
                  f"win={p.win_rate:.1%} avg_ret={p.avg_return:+.2%} "
                  f"sharpe={p.sharpe:+.2f} mdd={p.max_drawdown:+.2%}")
