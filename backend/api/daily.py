"""每日复盘端点。流式返回：先推 positions+行情，再流 AI 文本，最后 parsed JSON。"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.ai import get_ai_engine
from backend.ai.prompts import render_daily_prompt
from backend.db import repo
from backend.market.aggregator import get_snapshot

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/daily", tags=["daily"])


def _sse(event: str, data: Any) -> bytes:
    return (f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n").encode("utf-8")


def _parse_claude_json(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:].strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError(f"no JSON: {t[:200]}")
    candidate = t[i:j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        import json_repair
        r = json_repair.loads(candidate)
        if not isinstance(r, dict):
            raise ValueError(f"repaired but not dict: {type(r).__name__}")
        return r


async def _enrich_positions() -> list[dict[str, Any]]:
    rows = repo.list_positions()
    if not rows:
        return []

    async def _one(p: dict) -> dict:
        try:
            snap = await get_snapshot(p["symbol"], p["market"])
        except Exception:
            snap = {}
        last = snap.get("last")
        if isinstance(last, (int, float)) and last > 0:
            pnl_pct = round((last / p["cost_price"] - 1) * 100, 2)
        else:
            pnl_pct = None
        return {
            **p,
            "last_price": last,
            "daily_change_pct": snap.get("daily_change_pct"),
            "pnl_pct": pnl_pct,
            "_snapshot": snap,
        }

    return await asyncio.gather(*(_one(p) for p in rows))


def _market_env_from(positions: list[dict]) -> dict[str, Any]:
    """从持仓的 snapshot 里聚一份大盘环境。"""
    env: dict[str, Any] = {}
    for p in positions:
        snap = p.get("_snapshot", {}) or {}
        note = snap.get("index_note")
        if note and p["market"] == "A" and not env.get("a_index"):
            env["a_index"] = note
        if note and p["market"] == "HK" and not env.get("hk_index"):
            env["hk_index"] = note
        if note and p["market"] == "US" and not env.get("us_index"):
            env["us_index"] = note
    return env


@router.post("/review/stream")
async def daily_review_stream():
    async def gen():
        try:
            yield _sse("status", {"phase": "fetching_positions"})
            positions = await _enrich_positions()
            if not positions:
                yield _sse("error", {"message": "暂无持仓，请先添加"})
                return

            # 简化给前端的 position payload（去掉 _snapshot 内部字段）
            client_positions = [{k: v for k, v in p.items() if k != "_snapshot"}
                                for p in positions]
            yield _sse("positions", client_positions)

            market_env = _market_env_from(positions)
            yield _sse("market_env", market_env)

            yield _sse("status", {"phase": "ai_generating"})
            system, prompt = render_daily_prompt(positions, market_env)

            engine = get_ai_engine()
            buf: list[str] = []
            start = datetime.now()
            async for chunk in engine.stream(prompt, system=system):
                buf.append(chunk)
                yield _sse("chunk", {"text": chunk})

            full = "".join(buf)
            latency_ms = int((datetime.now() - start).total_seconds() * 1000)

            parsed: dict[str, Any] = {}
            parse_err = None
            try:
                parsed = _parse_claude_json(full)
            except Exception as e:
                parse_err = str(e)
                log.warning("Daily JSON 解析失败: %s", e)

            if parsed:
                yield _sse("parsed", parsed)

            review_id = repo.insert_review({
                "review_type": "daily",
                "trade_id": None,
                "review_date": datetime.now().strftime("%Y-%m-%d"),
                "scores": None,
                "tags": None,
                "report_md": full,
                "scenarios": parsed.get("priorities"),
                "lesson": parsed.get("portfolio_note"),
                "ai_engine": engine.name,
                "ai_latency_ms": latency_ms,
            })
            yield _sse("done", {
                "review_id": review_id,
                "latency_ms": latency_ms,
                "engine": engine.name,
                "parse_error": parse_err,
            })
        except Exception as e:
            log.exception("每日复盘异常")
            yield _sse("error", {"message": str(e), "type": type(e).__name__})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
