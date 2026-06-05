"""选股信号生成。

把因子打分包装成"策略"：每个策略一个名字、参数集、Top N。
v1 只有一个策略 multifactor_v1（等权 5 因子）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pandas as pd

from backend.db.repo import _connect
from backend.quant.factors import compute_factors, persist_snapshot
from backend.quant.strategies import get as get_strategy
from backend.quant.universe import mainboard_universe


@dataclass
class Signal:
    strategy: str
    signal_date: str
    symbol: str
    side: str          # 'buy' / 'sell'
    score: float
    reason: dict


def run_strategy(strategy: str = "multifactor_v1",
                 top_n: int | None = None,
                 as_of: str | None = None) -> list[Signal]:
    """跑一遍策略,落 snapshot 表 + 返回 Top N 买入信号。
    strategy 必须是 strategies 注册表里的名字;top_n=None 时用策略自带默认。"""
    strat = get_strategy(strategy)
    factors = strat.factors
    top_n = top_n if top_n is not None else strat.top_n
    as_of = as_of or date.today().strftime("%Y-%m-%d")
    universe = {r.symbol for r in mainboard_universe()}
    df = compute_factors(as_of=as_of, symbols=universe,
                         include=factors, weights=strat.weights)
    if df.empty:
        return []

    persist_snapshot(df, snapshot_date=as_of, factor_names=factors)

    top = df.head(top_n)
    signals: list[Signal] = []
    name_map = _symbol_name_map()
    for _, r in top.iterrows():
        sym = r["symbol"]
        reason = {
            "rank": int(r["rank"]),
            "composite": round(float(r["composite"]), 4),
            "name": name_map.get(sym, ""),
            "factors": {f: round(float(r[f]), 4) for f in factors if not pd.isna(r[f])},
            "factor_z": {f: round(float(r[f"{f}_z"]), 3) for f in factors},
        }
        signals.append(Signal(
            strategy=strategy,
            signal_date=as_of,
            symbol=sym,
            side="buy",
            score=float(r["composite"]),
            reason=reason,
        ))
    _persist_signals(signals)
    return signals


def _symbol_name_map() -> dict[str, str]:
    return {r.symbol: r.name for r in mainboard_universe()}


def _persist_signals(signals: list[Signal]) -> int:
    if not signals:
        return 0
    rows = [{
        "strategy": s.strategy,
        "signal_date": s.signal_date,
        "symbol": s.symbol,
        "side": s.side,
        "score": s.score,
        "reason_json": json.dumps(s.reason, ensure_ascii=False),
    } for s in signals]
    with _connect() as c:
        c.executemany(
            """INSERT OR REPLACE INTO strategy_signals
               (strategy, signal_date, symbol, side, score, reason_json)
               VALUES (:strategy, :signal_date, :symbol, :side, :score, :reason_json)""",
            rows,
        )
        c.commit()
    return len(rows)


def latest_signals(strategy: str | None = None, limit: int = 50) -> list[dict]:
    """前端用：查最新一批信号。"""
    sql = "SELECT * FROM strategy_signals"
    params: list = []
    if strategy:
        sql += " WHERE strategy = ?"
        params.append(strategy)
    sql += " ORDER BY signal_date DESC, score DESC LIMIT ?"
    params.append(limit)
    with _connect() as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    sigs = run_strategy(top_n=20)
    print(f"[signals] 生成 {len(sigs)} 条信号")
    for i, s in enumerate(sigs, 1):
        name = s.reason.get("name", "")
        fz = s.reason["factor_z"]
        zs = "  ".join(f"{k}={v:+.2f}" for k, v in fz.items())
        print(f"  #{i:>2}  {s.symbol} {name:<8}  score={s.score:+.3f}  {zs}")
