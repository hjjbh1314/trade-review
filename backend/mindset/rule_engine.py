"""心态诊断规则引擎：7 类标签，先打硬标签再给 AI 软解读。

阈值全部集中在顶部的 THRESHOLDS 字典，便于日后按历史回测调参。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.db import repo

# ─── 可调阈值 ──────────────────────────────────────────────────────
THRESHOLDS: dict[str, Any] = {
    # 追涨
    "chase": {
        "price_vs_open_min":     1.02,  # 买价 ≥ 开盘 × 1.02
        "pre30_rise_min":        1.5,   # 买前 30min 涨幅 ≥ 1.5%
        "daily_rise_min":        2.0,   # 当日涨幅 ≥ 2%
        "light_pre30":          (1.5, 2.5),
        "medium_pre30":         (2.5, 4.0),
        # >4% = heavy
    },
    # 杀跌
    "panic": {
        "price_vs_open_max":     0.98,
        "pre30_fall_min":        1.5,
        "daily_fall_min":        2.0,
        "light_pre30":          (1.5, 2.5),
        "medium_pre30":         (2.5, 4.0),
    },
    # 逆势
    "counter_trend": {
        "index_fall_min":        1.0,
        "sector_fall_min":       1.5,
    },
    # 拖单
    "drag": {
        "loss_pct_min":          5.0,
        "requires_break_ma20":   True,
    },
    # 报复性交易
    "revenge": {
        "within_hours":          2,
    },
    # 频繁交易
    "frequent": {
        "daily_count_min":       4,
    },
}


@dataclass
class Tag:
    tag: str
    severity: str                    # light / medium / heavy
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tag": self.tag, "severity": self.severity, "evidence": self.evidence}


# ─── 市场快照协议 ──────────────────────────────────────────────────
# MindsetRuleEngine 依赖的行情信息。调用方需要提供以下字段（来自 MarketDataAggregator）：
#   open:           当日开盘价
#   close_at_trade: 交易时刻的价（若无则用 price 本身）
#   pre30_change_pct: 交易前 30 分钟涨跌幅（%）
#   daily_change_pct: 交易当日截至现在的涨跌幅（%）
#   index_change_pct: 大盘涨跌幅（%）
#   sector_change_pct: 所属板块涨跌幅（%，可选，无则忽略逆势判断）
#   ma20:           当日 MA20（拖单判断用）
#   has_broken_ma20: 是否已跌破 MA20


class MindsetRuleEngine:
    def __init__(self, thresholds: dict[str, Any] | None = None):
        self.th = thresholds or THRESHOLDS

    def tag_trade(self, trade: dict[str, Any], snapshot: dict[str, Any]) -> list[Tag]:
        tags: list[Tag] = []
        action = trade["action"]

        if action == "buy":
            t = self._check_chase(trade, snapshot)
            if t: tags.append(t)
            t = self._check_counter_trend(trade, snapshot)
            if t: tags.append(t)
            t = self._check_drag_on_add(trade, snapshot)
            if t: tags.append(t)

        if action == "sell":
            t = self._check_panic(trade, snapshot)
            if t: tags.append(t)

        t = self._check_revenge(trade)
        if t: tags.append(t)

        t = self._check_frequent(trade)
        if t: tags.append(t)

        return tags

    # ─── 各规则实现 ───────────────────────────────────────────────

    def _check_chase(self, trade: dict, snap: dict) -> Tag | None:
        cfg = self.th["chase"]
        open_p = snap.get("open")
        pre30 = snap.get("pre30_change_pct")
        daily = snap.get("daily_change_pct")
        price = trade["price"]
        if None in (open_p, pre30, daily) or open_p == 0:
            return None

        if (price / open_p >= cfg["price_vs_open_min"]
            and pre30 >= cfg["pre30_rise_min"]
            and daily >= cfg["daily_rise_min"]):
            severity = self._severity_from_range(pre30, cfg["light_pre30"], cfg["medium_pre30"])
            return Tag("追涨", severity, {
                "price": price, "open": open_p,
                "price_vs_open_pct": round((price / open_p - 1) * 100, 2),
                "pre30_change_pct": pre30, "daily_change_pct": daily,
            })
        return None

    def _check_panic(self, trade: dict, snap: dict) -> Tag | None:
        cfg = self.th["panic"]
        open_p = snap.get("open")
        pre30 = snap.get("pre30_change_pct")
        daily = snap.get("daily_change_pct")
        price = trade["price"]
        if None in (open_p, pre30, daily) or open_p == 0:
            return None

        if (price / open_p <= cfg["price_vs_open_max"]
            and pre30 <= -cfg["pre30_fall_min"]
            and daily <= -cfg["daily_fall_min"]):
            severity = self._severity_from_range(abs(pre30), cfg["light_pre30"], cfg["medium_pre30"])
            return Tag("杀跌", severity, {
                "price": price, "open": open_p,
                "price_vs_open_pct": round((price / open_p - 1) * 100, 2),
                "pre30_change_pct": pre30, "daily_change_pct": daily,
            })
        return None

    def _check_counter_trend(self, trade: dict, snap: dict) -> Tag | None:
        cfg = self.th["counter_trend"]
        idx = snap.get("index_change_pct")
        sec = snap.get("sector_change_pct")
        if idx is None:
            return None
        # 板块数据可选；若无，退化为只看大盘
        sector_bad = sec is None or sec <= -cfg["sector_fall_min"]
        if idx <= -cfg["index_fall_min"] and sector_bad:
            return Tag("逆势", "medium", {
                "index_change_pct": idx,
                "sector_change_pct": sec,
            })
        return None

    def _check_drag_on_add(self, trade: dict, snap: dict) -> Tag | None:
        """买入时的"摊低成本式拖单"不归这里；这里预留，主要给卖出拖单用。"""
        return None

    def _check_revenge(self, trade: dict) -> Tag | None:
        cfg = self.th["revenge"]
        prev = repo.last_trade_before(trade["symbol"], trade["trade_time"])
        if not prev:
            return None
        # 必须前一笔亏损：粗判 = 现在买卖方向与前一笔相同且前一笔是止损卖出，或时间窗内反手
        # 简化规则：2 小时内对同 symbol 再操作 = 疑似报复
        try:
            prev_dt = datetime.fromisoformat(prev["trade_time"])
            curr_dt = datetime.fromisoformat(trade["trade_time"])
        except ValueError:
            return None
        gap_hours = (curr_dt - prev_dt).total_seconds() / 3600
        if 0 < gap_hours <= cfg["within_hours"]:
            return Tag("报复性交易", "light" if gap_hours >= 1 else "medium", {
                "prev_trade_id": prev["id"],
                "prev_time": prev["trade_time"],
                "gap_hours": round(gap_hours, 2),
            })
        return None

    def _check_frequent(self, trade: dict) -> Tag | None:
        cfg = self.th["frequent"]
        date_str = trade["trade_time"][:10]
        # 当前这笔已入库时计数会 +1；未入库则 +1 预判
        n = repo.count_trades_on_date(date_str) + 1
        if n >= cfg["daily_count_min"]:
            return Tag("频繁交易", "medium" if n <= 5 else "heavy", {"daily_count": n})
        return None

    # ─── 工具 ────────────────────────────────────────────────────

    @staticmethod
    def _severity_from_range(value: float,
                             light: tuple[float, float],
                             medium: tuple[float, float]) -> str:
        if light[0] <= value < light[1]:
            return "light"
        if medium[0] <= value < medium[1]:
            return "medium"
        return "heavy"
