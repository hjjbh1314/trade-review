"""量化模块 HTTP 接口。

GET /api/quant/strategies                 已注册的可用策略列表
GET /api/quant/signals/latest             最新一批信号 (默认 multifactor_v1)
GET /api/quant/snapshot/{date}            指定日期的因子快照
POST /api/quant/run                       手动触发选股 (body: {strategy, top_n, paper})
GET /api/quant/paper-trades               量化模拟单列表
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.db.repo import _connect
from backend.quant.paper_trader import list_paper_trades, open_positions_from_signals
from backend.quant.signals import Signal, latest_signals, run_strategy
from backend.quant.strategies import all_strategies, get as get_strategy


router = APIRouter(prefix="/api/quant", tags=["quant"])


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    return {"strategies": [{
        "name": s.name,
        "description": s.description,
        "factors": s.factors,
        "weights": s.weights,
        "top_n": s.top_n,
    } for s in all_strategies()]}


@router.get("/signals/latest")
def get_latest_signals(strategy: str | None = "multifactor_v1",
                       limit: int = 50) -> dict[str, Any]:
    rows = latest_signals(strategy=strategy, limit=limit)
    out = []
    for r in rows:
        reason = json.loads(r.get("reason_json") or "{}")
        out.append({
            "strategy": r["strategy"],
            "signal_date": r["signal_date"],
            "symbol": r["symbol"],
            "name": reason.get("name"),
            "side": r["side"],
            "score": r["score"],
            "rank": reason.get("rank"),
            "factor_z": reason.get("factor_z"),
            "consumed": bool(r["consumed"]),
        })
    return {"signals": out, "count": len(out)}


@router.get("/snapshot/{snapshot_date}")
def get_snapshot(snapshot_date: str, limit: int = 200) -> dict[str, Any]:
    with _connect() as c:
        rows = c.execute(
            """SELECT symbol, factors_json, composite, rank FROM factor_snapshots
               WHERE snapshot_date = ? ORDER BY rank LIMIT ?""",
            (snapshot_date, limit),
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"no snapshot for {snapshot_date}")
    return {
        "snapshot_date": snapshot_date,
        "rows": [{
            "symbol": r["symbol"],
            "factors": json.loads(r["factors_json"]),
            "composite": r["composite"],
            "rank": r["rank"],
        } for r in rows],
    }


@router.post("/run")
def trigger_run(payload: dict[str, Any]) -> dict[str, Any]:
    strategy = payload.get("strategy", "multifactor_v1")
    top_n = int(payload.get("top_n", 20))
    paper = bool(payload.get("paper", False))
    try:
        get_strategy(strategy)
    except KeyError as e:
        raise HTTPException(404, str(e))
    signals = run_strategy(strategy=strategy, top_n=top_n)
    trade_ids: list[int] = []
    if paper:
        trade_ids = open_positions_from_signals(signals)
    return {
        "strategy": strategy,
        "count": len(signals),
        "trade_ids": trade_ids,
        "top": [{
            "symbol": s.symbol,
            "name": s.reason.get("name"),
            "rank": s.reason.get("rank"),
            "score": round(s.score, 4),
            "factor_z": s.reason.get("factor_z"),
        } for s in signals[:10]],
    }


@router.get("/paper-trades")
def get_paper_trades(strategy: str | None = None, limit: int = 100) -> dict[str, Any]:
    rows = list_paper_trades(strategy=strategy, limit=limit)
    return {"trades": rows, "count": len(rows)}
