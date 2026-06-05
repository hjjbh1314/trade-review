"""模拟盘下单。

把 strategy_signals 表里 consumed=0 的买入信号转成 trades 表里的虚拟订单。
和真实交易共用 trades 表;区分靠 reason 前缀 [quant:strategy_name]。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from backend.db.repo import _connect, insert_trade
from backend.quant.signals import Signal


PAPER_CAPITAL_PER_TRADE = 10000.0  # 每条信号虚拟下单 1 万元
TAG_PREFIX = "[quant:"             # 用于在 reason 里识别量化单


def open_positions_from_signals(signals: Iterable[Signal],
                                 trade_time: str | None = None) -> list[int]:
    """根据信号建立虚拟仓位:用最近收盘价虚拟买入。返回新建的 trade_id 列表。"""
    trade_time = trade_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out: list[int] = []
    for s in signals:
        price = _latest_close(s.symbol)
        if not price:
            continue
        qty = max(int(PAPER_CAPITAL_PER_TRADE // price // 100 * 100), 100)
        reason_str = f"{TAG_PREFIX}{s.strategy}] rank={s.reason.get('rank')} score={s.score:+.3f}"
        tid = insert_trade({
            "symbol": s.symbol,
            "market": "A",
            "name": s.reason.get("name", ""),
            "action": "buy",
            "price": float(price),
            "quantity": qty,
            "trade_time": trade_time,
            "reason": reason_str,
            "mood": "auto",
        })
        out.append(tid)
        _mark_consumed(s)
    return out


def _latest_close(symbol: str) -> float | None:
    with _connect() as c:
        row = c.execute(
            """SELECT close FROM daily_quotes
               WHERE symbol = ? AND adjust = 'hfq'
               ORDER BY trade_date DESC LIMIT 1""",
            (symbol,),
        ).fetchone()
        return float(row["close"]) if row else None


def _mark_consumed(s: Signal) -> None:
    with _connect() as c:
        c.execute(
            """UPDATE strategy_signals SET consumed = 1
               WHERE strategy = ? AND signal_date = ? AND symbol = ? AND side = ?""",
            (s.strategy, s.signal_date, s.symbol, s.side),
        )
        c.commit()


def list_paper_trades(strategy: str | None = None, limit: int = 100) -> list[dict]:
    """筛选 trades 表里量化生成的单。"""
    pattern = f"{TAG_PREFIX}{strategy}]%" if strategy else f"{TAG_PREFIX}%"
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM trades WHERE reason LIKE ? ORDER BY trade_time DESC LIMIT ?",
            (pattern, limit),
        ).fetchall()
    return [dict(r) for r in rows]
