"""对话端点。面向 Dashboard 右侧的追问对话：用户可针对聚焦的持仓自由提问。

P0 简化：每条消息独立调用 Claude（无会话状态保持），前端维护对话历史并每次把最近 N 条发回。
这样既避免服务端状态管理，也可以在 Prompt 里拼更丰富的上下文。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ai import get_ai_engine
from backend.market.aggregator import get_snapshot

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _user_name() -> str:
    return os.environ.get("TR_USER_NAME", "the trader").strip() or "the trader"


class FocusContext(BaseModel):
    symbol: str | None = None
    market: str | None = Field(default=None, pattern=r"^(A|HK|US)$")
    name: str | None = None
    cost_price: float | None = None
    quantity: int | None = None


class ChatMessageIn(BaseModel):
    messages: list[dict[str, str]]            # [{"role":"user"|"assistant","content":"..."}]
    focus: FocusContext | None = None         # 当前聚焦持仓


def _sse(event: str, data: Any) -> bytes:
    return (f"event: {event}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n").encode("utf-8")


def _chat_system() -> str:
    return f"""你是一位风格直接的交易教练，服务对象是「{_user_name()}」。
- 语言：简体中文
- 风格：务实、直接、基于事实；不编造数字
- 任何持仓/行情引用都必须基于系统给出的"聚焦上下文"，不得虚构
- 输出用自然语言 markdown 即可，不需要 JSON
"""


def _render_focus_block(focus: FocusContext | None, snap: dict | None) -> str:
    if not focus or not focus.symbol:
        return "（本轮对话未聚焦任何持仓）"
    parts = [
        f"标的：{focus.symbol} {focus.name or ''} · {focus.market} 市场",
    ]
    if focus.cost_price is not None and focus.quantity is not None:
        parts.append(f"持仓：{focus.quantity} 股 @ 成本 {focus.cost_price}")
    if snap and not snap.get("error"):
        parts.append(
            f"当前：{snap.get('last')} · 日涨 {snap.get('daily_change_pct')}% · "
            f"MA5/20 {snap.get('ma5')}/{snap.get('ma20')} · "
            f"MACD {snap.get('macd_note')} · RSI {snap.get('rsi')}"
        )
        if snap.get("index_note"):
            parts.append(f"大盘：{snap.get('index_note')}")
    return "\n".join(parts)


@router.post("/message/stream")
async def chat_message_stream(payload: ChatMessageIn):
    async def gen():
        try:
            # 拉聚焦持仓的实时快照（让 Claude 有新鲜数据）
            snap = None
            if payload.focus and payload.focus.symbol and payload.focus.market:
                yield _sse("status", {"phase": "fetching_market"})
                try:
                    snap = await get_snapshot(payload.focus.symbol, payload.focus.market)
                except Exception:
                    snap = None

            focus_block = _render_focus_block(payload.focus, snap)

            # 把历史对话 + 当前问题拼成 prompt
            history_lines = []
            for m in payload.messages[:-1]:   # 除最后一条
                role_cn = {"user": "用户", "assistant": "助手"}.get(m.get("role", ""), m.get("role", ""))
                history_lines.append(f"{role_cn}: {m.get('content', '')}")
            history = "\n".join(history_lines) if history_lines else "（无）"

            last = payload.messages[-1] if payload.messages else {"content": "你好"}
            current_q = last.get("content", "")

            prompt = f"""【聚焦上下文】
{focus_block}

【对话历史】
{history}

【用户当前提问】
{current_q}

请基于聚焦上下文和对话历史回答。如果用户提问与聚焦持仓无关，可自由发挥但仍需务实。"""

            yield _sse("status", {"phase": "ai_generating"})
            engine = get_ai_engine()
            start = datetime.now()
            async for chunk in engine.stream(prompt, system=_chat_system()):
                yield _sse("chunk", {"text": chunk})
            latency_ms = int((datetime.now() - start).total_seconds() * 1000)

            yield _sse("done", {
                "latency_ms": latency_ms,
                "engine": engine.name,
            })
        except Exception as e:
            log.exception("chat 异常")
            yield _sse("error", {"message": str(e), "type": type(e).__name__})

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
