"""周度心态画像聚合：
  1. 读本周内的所有 mindset_tags
  2. 计算 6 维雷达分数（纪律/情绪稳定/耐心/独立判断/风控执行/学习力）
  3. 挑 3 个典型错误（优先 heavy > medium）
  4. 生成文字寄语（Claude）
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, timedelta
from typing import Any

from backend.db import repo

log = logging.getLogger(__name__)


def week_bounds(d: date | None = None) -> tuple[str, str, str]:
    """返回 (year_week, week_start, week_end) 字符串，week 按周一起算。"""
    d = d or date.today()
    year, week_num, _ = d.isocalendar()
    monday = d - timedelta(days=d.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    return f"{year}-W{week_num:02d}", monday.isoformat(), sunday.isoformat()


def _radar_from_tags(tag_rows: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, int]:
    """基于规则层标签计算 6 维雷达分数。分数从 100 起扣，每条 heavy/medium/light 有不同扣分权重。"""
    counts: dict[str, list[str]] = {}   # tag -> [severity...]
    for r in tag_rows:
        counts.setdefault(r["tag"], []).append(r.get("severity") or "medium")

    # 基础分 85
    discipline  = 85   # 纪律性：有"拖单/报复性交易"扣
    emotion     = 85   # 情绪稳定：有"追涨/杀跌/报复性交易"扣
    patience    = 85   # 耐心：有"频繁交易/追涨"扣
    autonomy    = 85   # 独立判断：无负面标签时较高；有"过早止盈/追涨"略扣（盲从）
    risk_ctrl   = 85   # 风控执行：有"拖单/止损被动"扣
    learning    = 85   # 学习力：默认 85，每次复盘都做也不会涨（真实学习需看趋势）

    def _deduct(tags: list[str]) -> int:
        return sum({"heavy": 15, "medium": 10, "light": 5}.get(s, 8) for s in tags)

    if "拖单" in counts:
        discipline -= _deduct(counts["拖单"])
        risk_ctrl  -= _deduct(counts["拖单"])
    if "报复性交易" in counts:
        discipline -= _deduct(counts["报复性交易"])
        emotion    -= _deduct(counts["报复性交易"])
    if "追涨" in counts:
        emotion  -= _deduct(counts["追涨"]) // 2
        patience -= _deduct(counts["追涨"])
        autonomy -= _deduct(counts["追涨"]) // 2
    if "杀跌" in counts:
        emotion -= _deduct(counts["杀跌"])
        risk_ctrl -= _deduct(counts["杀跌"]) // 2
    if "频繁交易" in counts:
        patience -= _deduct(counts["频繁交易"])
        discipline -= _deduct(counts["频繁交易"]) // 2
    if "过早止盈" in counts:
        autonomy -= _deduct(counts["过早止盈"])
        patience -= _deduct(counts["过早止盈"]) // 2
    if "逆势" in counts:
        autonomy -= _deduct(counts["逆势"]) // 2
        risk_ctrl -= _deduct(counts["逆势"]) // 2

    # 若本周交易数 < 3，纪律和耐心分不扣"频繁"（样本不足）
    if len(trades) < 3:
        discipline = max(discipline, 80)
        patience = max(patience, 80)

    def _clip(v: int) -> int:
        return max(20, min(100, v))

    return {
        "discipline":  _clip(discipline),
        "emotion":     _clip(emotion),
        "patience":    _clip(patience),
        "autonomy":    _clip(autonomy),
        "risk_ctrl":   _clip(risk_ctrl),
        "learning":    _clip(learning),
    }


def _pick_top_errors(tag_rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    """按严重度排序挑选典型错误。"""
    severity_rank = {"heavy": 0, "medium": 1, "light": 2}
    negative_tags = {"追涨", "杀跌", "拖单", "报复性交易", "逆势", "频繁交易", "过早止盈"}
    filtered = [r for r in tag_rows if r["tag"] in negative_tags]
    filtered.sort(key=lambda r: (severity_rank.get(r.get("severity") or "medium", 3),
                                 r.get("trade_time", "")))
    out = []
    for r in filtered[:limit]:
        evid = r.get("evidence_json")
        try:
            evid_obj = json.loads(evid) if evid else {}
        except Exception:
            evid_obj = {}
        out.append({
            "trade_id": r["trade_id"],
            "symbol":   r["symbol"],
            "trade_time": r.get("trade_time"),
            "tag":      r["tag"],
            "severity": r.get("severity"),
            "evidence": evid_obj,
        })
    return out


def compute_weekly(d: date | None = None) -> dict[str, Any]:
    year_week, start_date, end_date = week_bounds(d)

    tag_rows = repo.list_tags_in_range(start_date, end_date)
    # 取同期所有交易，用于 frequency 判断
    # （repo 没提供 list_trades_in_range，这里借用 list_recent_trades 后筛）
    trades = [t for t in repo.list_recent_trades(limit=500)
              if start_date <= t["trade_time"][:10] <= end_date]

    tag_counter: Counter = Counter()
    for r in tag_rows:
        tag_counter[r["tag"]] += 1

    radar = _radar_from_tags(tag_rows, trades)
    top_errors = _pick_top_errors(tag_rows, 3)

    return {
        "year_week":  year_week,
        "week_start": start_date,
        "week_end":   end_date,
        "trade_count": len(trades),
        "tag_counts": dict(tag_counter),
        "radar":      radar,
        "top_errors": top_errors,
    }
