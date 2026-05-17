"""持仓 CRUD + 批量现价查询（供前端仪表盘一次拉齐）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import repo
from backend.market.aggregator import get_snapshot

router = APIRouter(prefix="/api/positions", tags=["positions"])


class PositionIn(BaseModel):
    symbol: str
    market: str = Field(pattern=r"^(A|HK|US)$")
    name: str | None = None
    quantity: int = Field(gt=0)
    cost_price: float = Field(gt=0)


@router.get("")
def list_positions() -> dict:
    rows = repo.list_positions()
    return {"ok": True, "items": rows, "count": len(rows)}


@router.post("")
def upsert_position(pos: PositionIn) -> dict:
    repo.upsert_position(pos.model_dump())
    return {"ok": True}


@router.delete("/{market}/{symbol}")
def delete_position(market: str, symbol: str) -> dict:
    if market not in {"A", "HK", "US"}:
        raise HTTPException(400, "market must be A/HK/US")
    repo.delete_position(symbol, market)
    return {"ok": True}


@router.get("/with-quotes")
async def list_positions_with_quotes() -> dict:
    """返回持仓 + 每只现价、日涨跌、市值、浮盈亏。前端仪表盘一次调用即可。"""
    rows = repo.list_positions()
    if not rows:
        return {"ok": True, "items": [], "summary": _empty_summary()}

    async def _enrich(p: dict) -> dict:
        try:
            snap = await get_snapshot(p["symbol"], p["market"])
        except Exception:
            snap = {}
        last = snap.get("last")
        daily_chg = snap.get("daily_change_pct")
        if isinstance(last, (int, float)) and last > 0:
            market_value = last * p["quantity"]
            pnl = (last - p["cost_price"]) * p["quantity"]
            pnl_pct = round((last / p["cost_price"] - 1) * 100, 2)
        else:
            market_value = p["cost_price"] * p["quantity"]
            pnl = 0.0
            pnl_pct = 0.0
        return {
            **p,
            "last_price": last,
            "daily_change_pct": daily_chg,
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": pnl_pct,
        }

    items = await asyncio.gather(*(_enrich(p) for p in rows))

    # 汇总（按市场分币种，不做跨币种换算）
    by_market: dict[str, dict] = {}
    for it in items:
        m = it["market"]
        bucket = by_market.setdefault(m, {"market_value": 0.0, "pnl": 0.0, "count": 0})
        bucket["market_value"] += it["market_value"]
        bucket["pnl"] += it["pnl"]
        bucket["count"] += 1

    for m, b in by_market.items():
        b["market_value"] = round(b["market_value"], 2)
        b["pnl"] = round(b["pnl"], 2)

    return {"ok": True, "items": items, "summary": by_market}


def _empty_summary() -> dict:
    return {}
