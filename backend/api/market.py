"""行情数据 API。K 线 + 技术指标。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market", tags=["market"])


def _to_float(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@router.get("/kline")
def get_kline(
    symbol: str,
    market: str = Query(pattern=r"^(A|HK|US)$"),
    period: str = Query("daily", pattern=r"^(daily|weekly|monthly)$"),
    limit: int = Query(120, ge=1, le=500),
) -> dict:
    """返回 [{time, open, high, low, close, volume}]，time 是 'YYYY-MM-DD' 字符串。
    同时算 MA5 / MA20 均线序列，便于前端叠加。
    A 股优先 akshare（eastmoney），失败时自动转 yfinance（yahoo finance）。"""
    if market == "A":
        rows = _a_kline(symbol, period, limit)
        if not rows:
            log.info("A股 %s K 线 akshare 无数据，转 yfinance 兜底", symbol)
            rows = _yf_kline(symbol, "A", period, limit)
    else:
        rows = _yf_kline(symbol, market, period, limit)

    if not rows:
        raise HTTPException(404, f"no kline data for {symbol} ({market})")

    # 均线
    closes = [r["close"] for r in rows]
    ma5 = _moving_avg(closes, 5)
    ma20 = _moving_avg(closes, 20)

    return {
        "ok": True,
        "symbol": symbol,
        "market": market,
        "period": period,
        "bars": rows,
        "ma5": [{"time": rows[i]["time"], "value": v}
                for i, v in enumerate(ma5) if v is not None],
        "ma20": [{"time": rows[i]["time"], "value": v}
                 for i, v in enumerate(ma20) if v is not None],
    }


def _moving_avg(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
        else:
            window_values = values[i + 1 - window : i + 1]
            result.append(round(sum(window_values) / window, 2))
    return result


def _a_kline(symbol: str, period: str, limit: int) -> list[dict]:
    try:
        import akshare as ak
    except ImportError:
        return []
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=max(365, limit * 2))).strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period=period,
                                start_date=start, end_date=end, adjust="qfq")
    except Exception as e:
        log.warning("A股 K 线失败 %s: %s", symbol, e)
        return []
    if df is None or len(df) == 0:
        return []
    df = df.tail(limit)
    # 兼容列名
    cols = {c: c for c in df.columns}
    out = []
    for _, row in df.iterrows():
        date_raw = row.get("日期") or row.get("date") or row.get("time")
        if date_raw is None:
            continue
        out.append({
            "time":   str(date_raw)[:10],
            "open":   _to_float(row.get("开盘") or row.get("open")),
            "high":   _to_float(row.get("最高") or row.get("high")),
            "low":    _to_float(row.get("最低") or row.get("low")),
            "close":  _to_float(row.get("收盘") or row.get("close")),
            "volume": _to_float(row.get("成交量") or row.get("volume")),
        })
    return [r for r in out if None not in (r["open"], r["close"])]


def _yf_kline(symbol: str, market: str, period: str, limit: int) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return []
    if market == "HK":
        core = symbol.lstrip("0") or "0"
        yf_symbol = f"{core.zfill(4)}.HK"
    elif market == "A":
        yf_symbol = f"{symbol}.{'SS' if symbol.startswith('6') else 'SZ'}"
    else:
        yf_symbol = symbol.upper()
    interval = {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}[period]
    try:
        hist = yf.Ticker(yf_symbol).history(period="2y", interval=interval, auto_adjust=True)
    except Exception as e:
        log.warning("yfinance K 线失败 %s: %s", yf_symbol, e)
        return []
    if len(hist) == 0:
        return []
    hist = hist.tail(limit)
    out = []
    for ts, row in hist.iterrows():
        out.append({
            "time":   ts.strftime("%Y-%m-%d"),
            "open":   round(float(row["Open"]),   2),
            "high":   round(float(row["High"]),   2),
            "low":    round(float(row["Low"]),    2),
            "close":  round(float(row["Close"]),  2),
            "volume": float(row["Volume"]),
        })
    return out
