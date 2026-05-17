"""盘中闪评端点。P0 先出非流式，前端渲染简单；SSE 放 P3。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ai import get_ai_engine
from backend.ai.prompts import render_flash_prompt
from backend.db import repo
from backend.market.aggregator import get_snapshot
from backend.mindset.rule_engine import MindsetRuleEngine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/flash", tags=["flash"])


class TradeInput(BaseModel):
    symbol: str
    market: str = Field(pattern=r"^(A|HK|US)$")
    name: str | None = None
    action: str = Field(pattern=r"^(buy|sell)$")
    price: float
    quantity: int
    trade_time: str          # "2026-04-24 14:20:00"
    reason: str | None = None
    mood: str | None = None


class FlashReviewResponse(BaseModel):
    ok: bool
    review_id: int | None = None
    trade_id: int | None = None
    engine: str | None = None
    latency_ms: int | None = None
    tags: list[dict[str, Any]] | None = None
    snapshot: dict[str, Any] | None = None
    # Claude 解析后的结构
    scores: dict[str, int] | None = None
    mindset_tags: list[str] | None = None
    mindset_reasoning: str | None = None
    technical_reading: str | None = None
    scenarios: list[dict[str, Any]] | None = None
    one_line_lesson: str | None = None
    # 原始文本（便于调试）
    raw: str | None = None
    error: str | None = None


def _parse_claude_json(text: str) -> dict[str, Any]:
    """Claude 返回 JSON 可能包含未转义的嵌套双引号，用 json-repair 容错。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:].strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError(f"未找到 JSON: {t[:200]}")
    candidate = t[i:j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        import json_repair
        result = json_repair.loads(candidate)
        if not isinstance(result, dict):
            raise ValueError(f"修复后仍非 dict: {type(result).__name__}")
        return result


@router.post("/review", response_model=FlashReviewResponse)
async def flash_review(trade: TradeInput) -> FlashReviewResponse:
    trade_dict = trade.model_dump()

    # 1. 拉行情快照
    try:
        snapshot = await get_snapshot(trade.symbol, trade.market, trade.trade_time)
    except Exception as e:
        log.exception("行情拉取失败")
        snapshot = {"error": str(e)}

    # 2. 规则层打标签
    try:
        rule_engine = MindsetRuleEngine()
        rule_tags = [t.to_dict() for t in rule_engine.tag_trade(trade_dict, snapshot)]
    except Exception as e:
        log.exception("规则引擎失败")
        rule_tags = []

    # 3. 入库（标签之后关联）
    trade_id = repo.insert_trade(trade_dict)
    if rule_tags:
        repo.insert_tags(trade_id, rule_tags)

    # 4. AI 闪评
    system, user_prompt = render_flash_prompt(trade_dict, snapshot, rule_tags)
    try:
        engine = get_ai_engine()
        ai_resp = await engine.complete(user_prompt, system=system)
    except Exception as e:
        log.exception("AI 调用失败")
        return FlashReviewResponse(
            ok=False, trade_id=trade_id, tags=rule_tags, snapshot=snapshot,
            error=f"AI 调用失败: {e}",
        )

    # 5. 解析 AI JSON
    parsed: dict[str, Any] = {}
    parse_err = None
    try:
        parsed = _parse_claude_json(ai_resp.text)
    except Exception as e:
        parse_err = str(e)
        log.warning("Claude JSON 解析失败: %s", e)

    # 6. 落库复盘记录
    review_id = repo.insert_review({
        "review_type": "flash",
        "trade_id": trade_id,
        "review_date": trade.trade_time[:10],
        "scores": parsed.get("scores"),
        "tags": parsed.get("mindset_tags") or [t["tag"] for t in rule_tags],
        "report_md": ai_resp.text,
        "scenarios": parsed.get("scenarios"),
        "lesson": parsed.get("one_line_lesson"),
        "ai_engine": ai_resp.engine,
        "ai_latency_ms": ai_resp.latency_ms,
    })

    return FlashReviewResponse(
        ok=True,
        review_id=review_id,
        trade_id=trade_id,
        engine=ai_resp.engine,
        latency_ms=ai_resp.latency_ms,
        tags=rule_tags,
        snapshot=snapshot,
        scores=parsed.get("scores"),
        mindset_tags=parsed.get("mindset_tags"),
        mindset_reasoning=parsed.get("mindset_reasoning"),
        technical_reading=parsed.get("technical_reading"),
        scenarios=parsed.get("scenarios"),
        one_line_lesson=parsed.get("one_line_lesson"),
        raw=ai_resp.text if parse_err else None,
        error=parse_err,
    )


# ─── SSE 流式闪评 ───────────────────────────────────────────────────
# 事件格式：
#   event: status    data: {"phase":"fetching_market"}
#   event: snapshot  data: {...}
#   event: tags      data: [...]
#   event: chunk     data: {"text":"加仓时点..."}     # 逐字
#   event: parsed    data: {scores, scenarios, ...}   # 尾帧结构化
#   event: done      data: {"review_id":123,"trade_id":456}
#   event: error     data: {"message":"..."}

def _sse(event: str, data: Any) -> bytes:
    return (f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n").encode("utf-8")


@router.post("/review/stream")
async def flash_review_stream(trade: TradeInput):
    trade_dict = trade.model_dump()

    async def gen():
        try:
            # 1. 行情
            yield _sse("status", {"phase": "fetching_market"})
            try:
                snapshot = await get_snapshot(trade.symbol, trade.market, trade.trade_time)
            except Exception as e:
                log.exception("行情拉取失败")
                snapshot = {"error": str(e)}
            yield _sse("snapshot", snapshot)

            # 2. 规则
            yield _sse("status", {"phase": "tagging"})
            try:
                rule_tags = [t.to_dict()
                             for t in MindsetRuleEngine().tag_trade(trade_dict, snapshot)]
            except Exception as e:
                log.exception("规则引擎失败")
                rule_tags = []
            yield _sse("tags", rule_tags)

            # 3. 入库交易 + 标签
            trade_id = repo.insert_trade(trade_dict)
            if rule_tags:
                repo.insert_tags(trade_id, rule_tags)

            # 4. AI 流式
            yield _sse("status", {"phase": "ai_generating"})
            system, user_prompt = render_flash_prompt(trade_dict, snapshot, rule_tags)

            engine = get_ai_engine()
            buf: list[str] = []
            start_time = datetime.now()
            async for chunk in engine.stream(user_prompt, system=system):
                buf.append(chunk)
                yield _sse("chunk", {"text": chunk})

            full_text = "".join(buf)
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # 5. 解析 + 落库
            parsed: dict[str, Any] = {}
            parse_err = None
            try:
                parsed = _parse_claude_json(full_text)
            except Exception as e:
                parse_err = str(e)
                log.warning("Claude JSON 解析失败: %s", e)

            if parsed:
                yield _sse("parsed", parsed)

            review_id = repo.insert_review({
                "review_type": "flash",
                "trade_id": trade_id,
                "review_date": trade.trade_time[:10],
                "scores": parsed.get("scores"),
                "tags": parsed.get("mindset_tags") or [t["tag"] for t in rule_tags],
                "report_md": full_text,
                "scenarios": parsed.get("scenarios"),
                "lesson": parsed.get("one_line_lesson"),
                "ai_engine": engine.name,
                "ai_latency_ms": latency_ms,
            })

            yield _sse("done", {
                "trade_id": trade_id,
                "review_id": review_id,
                "latency_ms": latency_ms,
                "engine": engine.name,
                "parse_error": parse_err,
            })
        except Exception as e:
            log.exception("流式闪评异常")
            yield _sse("error", {"message": str(e), "type": type(e).__name__})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 禁 Nginx 缓冲（未来反代时有用）
        },
    )
