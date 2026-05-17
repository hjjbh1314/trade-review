"""Prompt templates. Flash review enforces strict JSON for the front-end to render."""
from __future__ import annotations

import json
import os
from typing import Any


def _user_name() -> str:
    """The trader's display name (used in system prompts so the coach addresses
    them directly). Override via TR_USER_NAME env var."""
    return os.environ.get("TR_USER_NAME", "the trader").strip() or "the trader"


def _flash_system() -> str:
    return f"""你是一位风格直接的交易教练，服务对象是「{_user_name()}」。
- 语言：简体中文
- 风格：不说废话、直面问题、基于事实
- 必须严格按照用户要求的 JSON schema 输出，不添加任何 markdown 代码块包裹、不添加前后说明文字
- 所有结论必须基于提供的机器识别标签和行情事实，不允许编造数字
"""

FLASH_USER_TEMPLATE = """请对这笔交易输出闪评。

【交易信息】
- 标的：{symbol} {name} · {market} 市场
- 方向：{action_cn} {quantity} 股 @ {price}
- 时间：{trade_time}
- 用户理由：{reason}
- 用户当前心态：{mood}

【机器识别标签】
{rule_tags_block}

【市场快照】
- 开盘：{open}  当前：{last}
- 日内涨跌：{daily_change_pct}%
- 交易前 30 分钟涨跌：{pre30_change_pct}%
- MA5 / MA20：{ma5} / {ma20}
- MACD：{macd_note}
- RSI：{rsi}
- 大盘（上证/恒生/纳指）：{index_note}
- 板块：{sector_note}
- iFinD 摘要：{ifind_text}

【严格 JSON 输出 schema】
{{
  "scores": {{
    "timing": 0-100,     // 时机
    "mindset": 0-100,    // 心态
    "technical": 0-100   // 技术面
  }},
  "mindset_tags": ["标签1", "标签2"],   // 沿用规则层已识别的标签，也可补充
  "mindset_reasoning": "一段文字，基于证据链解释心态判断",
  "technical_reading": "一段文字，读 K 线和指标",
  "scenarios": [
    {{"name": "乐观", "probability": 概率(0-100), "trigger": "触发条件", "action": "对应操作"}},
    {{"name": "中性", "probability": 概率(0-100), "trigger": "...", "action": "..."}},
    {{"name": "悲观", "probability": 概率(0-100), "trigger": "...", "action": "..."}}
  ],
  "one_line_lesson": "一句话教训（不超过 40 字）"
}}

注意：probability 三项加和 = 100；直接返回纯 JSON，不要任何包裹。
"""


def render_flash_prompt(
    trade: dict[str, Any],
    snapshot: dict[str, Any],
    rule_tags: list[dict[str, Any]],
) -> tuple[str, str]:
    """渲染闪评 prompt，返回 (system, user)。"""
    action_cn = {"buy": "买入", "sell": "卖出"}.get(trade["action"], trade["action"])

    if rule_tags:
        rule_tags_block = "\n".join(
            f"- {t['tag']}（{t['severity']}）· 证据：{json.dumps(t.get('evidence', {}), ensure_ascii=False)}"
            for t in rule_tags
        )
    else:
        rule_tags_block = "- 无（本笔交易未触发任何结构化标签）"

    flash_system = _flash_system()
    user = FLASH_USER_TEMPLATE.format(
        symbol=trade["symbol"],
        name=trade.get("name") or "",
        market=trade["market"],
        action_cn=action_cn,
        quantity=trade["quantity"],
        price=trade["price"],
        trade_time=trade["trade_time"],
        reason=trade.get("reason") or "（未填）",
        mood=trade.get("mood") or "（未填）",
        rule_tags_block=rule_tags_block,
        open=snapshot.get("open", "n/a"),
        last=snapshot.get("last", "n/a"),
        daily_change_pct=snapshot.get("daily_change_pct", "n/a"),
        pre30_change_pct=snapshot.get("pre30_change_pct", "n/a"),
        ma5=snapshot.get("ma5", "n/a"),
        ma20=snapshot.get("ma20", "n/a"),
        macd_note=snapshot.get("macd_note", "n/a"),
        rsi=snapshot.get("rsi", "n/a"),
        index_note=snapshot.get("index_note", "n/a"),
        sector_note=snapshot.get("sector_note", "n/a"),
        ifind_text=snapshot.get("ifind_text") or "n/a",
    )
    return flash_system, user


# ─── Daily review ──────────────────────────────────────────────────

def _daily_system() -> str:
    return f"""你是一位风格直接的交易教练，服务对象是「{_user_name()}」。
- 覆盖 A 股、港股、美股三个市场
- 语言：简体中文
- 风格：务实、直接、基于事实
- 必须严格按照 JSON schema 输出；不添加 markdown 包裹、不添加前后说明文字
- 不编造数字：未知用 null，不要凭空给价位
"""

DAILY_USER_TEMPLATE = """请基于当前持仓和行情，生成明日操作建议。

【持仓与行情】
{positions_block}

【市场环境】
{market_env}

【严格 JSON schema】
{{
  "positions": [
    {{
      "symbol": "代码", "market": "A/HK/US", "name": "名称",
      "stage": "起涨|主升|顶部|下跌|筑底",
      "action": "持有|加仓|减仓|止损|观望",
      "action_rationale": "一句话说理由",
      "trigger": "触发条件，如 回踩¥1672不破 或 跌破¥195",
      "technical": "支撑/压力/MA/MACD/RSI 简要解读",
      "fundamental": "基本面要点（已知信息，2-3 条）",
      "risk": "主要风险"
    }}
  ],
  "priorities": ["按优先级列 3-5 条明日要点"],
  "portfolio_note": "组合级评价，如仓位集中度/现金比例建议"
}}

注意：每个持仓都要有对应条目，positions 数组长度必须等于提供的持仓数。
"""


def render_daily_prompt(
    positions_with_quotes: list[dict[str, Any]],
    market_env: dict[str, Any],
) -> tuple[str, str]:
    lines = []
    for i, p in enumerate(positions_with_quotes, 1):
        last = p.get("last_price")
        chg = p.get("daily_change_pct")
        pnl_pct = p.get("pnl_pct")
        snap = p.get("_snapshot", {}) or {}
        lines.append(
            f"{i}. {p['symbol']} {p.get('name', '')} · {p['market']}\n"
            f"   持仓 {p['quantity']} @ 成本 {p['cost_price']}  ·  现价 {last}  "
            f"·  日涨 {chg}%  ·  盈亏 {pnl_pct}%\n"
            f"   MA5/20: {snap.get('ma5')}/{snap.get('ma20')}  "
            f"MACD: {snap.get('macd_note')}  RSI: {snap.get('rsi')}"
        )
    positions_block = "\n".join(lines) if lines else "（无持仓）"

    market_env_text = (
        f"上证: {market_env.get('a_index', 'n/a')}  ·  "
        f"恒生: {market_env.get('hk_index', 'n/a')}  ·  "
        f"纳指: {market_env.get('us_index', 'n/a')}"
    )

    user = DAILY_USER_TEMPLATE.format(
        positions_block=positions_block,
        market_env=market_env_text,
    )
    return _daily_system(), user
