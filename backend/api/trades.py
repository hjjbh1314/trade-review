"""交易流水 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import repo

router = APIRouter(prefix="/api/trades", tags=["trades"])


class TradeIn(BaseModel):
    symbol: str
    market: str = Field(pattern=r"^(A|HK|US)$")
    name: str | None = None
    action: str = Field(pattern=r"^(buy|sell)$")
    price: float
    quantity: int
    trade_time: str
    reason: str | None = None
    mood: str | None = None


@router.post("")
def create_trade(trade: TradeIn) -> dict:
    trade_id = repo.insert_trade(trade.model_dump())
    return {"ok": True, "trade_id": trade_id}


@router.get("")
def list_trades(symbol: str | None = None, limit: int = 50) -> dict:
    rows = repo.list_recent_trades(symbol=symbol, limit=min(max(limit, 1), 500))
    return {"ok": True, "items": rows, "count": len(rows)}


@router.get("/journal")
def journal(symbol: str | None = None, tag: str | None = None, limit: int = 100) -> dict:
    """交易日志专用：trade + tags + review 一次拉齐。"""
    rows = repo.list_trades_with_context(
        symbol=symbol, tag=tag, limit=min(max(limit, 1), 500)
    )
    return {"ok": True, "items": rows, "count": len(rows)}


@router.get("/{trade_id}")
def get_trade(trade_id: int) -> dict:
    row = repo.get_trade(trade_id)
    if not row:
        raise HTTPException(404, "trade not found")
    return {"ok": True, "item": row}
