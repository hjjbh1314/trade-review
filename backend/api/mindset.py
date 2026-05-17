"""周度心态画像端点。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

from backend.ai import get_ai_engine
from backend.db import repo
from backend.mindset.weekly import compute_weekly, week_bounds

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mindset", tags=["mindset"])


MINDSET_SYSTEM = """你是一位务实的交易教练。基于结构化数据生成一段简短的本周寄语，
用中文，3-4 句话，指出最值得关注的问题和下周建议。不编造未提供的数据。
"""


def _build_mindset_prompt(data: dict[str, Any]) -> str:
    errs = data.get("top_errors") or []
    err_lines = [
        f"- {e.get('trade_time', '')[:16]} {e.get('symbol', '')} · {e.get('tag', '')}（{e.get('severity', '')}）"
        for e in errs
    ] or ["- 无"]
    radar = data.get("radar", {})
    counts = data.get("tag_counts", {}) or {}
    return f"""本周（{data['year_week']}，{data['week_start']} ~ {data['week_end']}）心态画像数据：

【交易量】{data.get('trade_count', 0)} 笔

【标签分布】{counts if counts else '无负面标签'}

【雷达分数】
- 纪律性: {radar.get('discipline')}
- 情绪稳定: {radar.get('emotion')}
- 耐心: {radar.get('patience')}
- 独立判断: {radar.get('autonomy')}
- 风控执行: {radar.get('risk_ctrl')}
- 学习力: {radar.get('learning')}

【本周典型错误】
{chr(10).join(err_lines)}

请输出一段 3-4 句话的寄语：点出最大短板 + 1 条下周具体可执行的改进建议。纯文本，不要列表。"""


@router.get("/weekly")
async def weekly_mindset(
    week: str | None = Query(None, description="如 2026-W17，不传为本周"),
    ai_message: bool = Query(True, description="是否生成 AI 寄语（默认是）"),
) -> dict[str, Any]:
    # 解析目标日期
    target: date | None = None
    if week:
        try:
            y, w = week.split("-W")
            target = datetime.strptime(f"{y}-W{int(w)}-1", "%G-W%V-%u").date()
        except Exception:
            return {"ok": False, "error": f"无效的 week 参数: {week}"}

    data = compute_weekly(target)

    # AI 寄语
    message = None
    if ai_message:
        try:
            engine = get_ai_engine()
            prompt = _build_mindset_prompt(data)
            ai_resp = await engine.complete(prompt, system=MINDSET_SYSTEM)
            message = ai_resp.text.strip()
        except Exception as e:
            log.warning("AI 寄语失败: %s", e)

    data["ai_message"] = message
    return {"ok": True, **data}


@router.get("/weeks")
def available_weeks(limit: int = Query(12, ge=1, le=52)) -> dict[str, Any]:
    """返回最近 N 周的 label 列表（便于前端切换）。"""
    today = date.today()
    weeks = []
    for offset in range(limit):
        target = today - timedelta(weeks=offset)
        year_week, ws, we = week_bounds(target)
        weeks.append({"year_week": year_week, "start": ws, "end": we})
    return {"ok": True, "items": weeks}