"""Multi-market quote aggregator.

Returns the snapshot used by flash review:
  open / last / daily_change_pct / pre30_change_pct / ma5 / ma20 /
  macd_note / rsi / index_change_pct / ifind_text (A-share, optional)

A-share: akshare (numbers) + optional iFinD enrichment (natural-language)
HK / US: yfinance
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from backend.market.ifind_adapter import enrich_with_ifind_text

log = logging.getLogger(__name__)


def _finite(x: Any) -> float | None:
    """Coerce a value to a JSON-safe float, or None for NaN / inf / non-numeric."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _sanitize(d: dict[str, Any]) -> dict[str, Any]:
    """Replace NaN / inf with None so the dict round-trips through json.dumps."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = _finite(v)
        elif isinstance(v, dict):
            out[k] = _sanitize(v)
        else:
            out[k] = v
    return out


def _symbol_to_yf(symbol: str, market: str) -> str:
    if market == "HK":
        # 港股：剥离前导零后补齐到 4 位。00700/0700/700 -> 0700.HK
        core = symbol.lstrip("0") or "0"
        return f"{core.zfill(4)}.HK"
    if market == "US":
        return symbol.upper()
    if market == "A":
        # A 股 fallback：6 字头 → 上交（.SS），其他（0/3）→ 深交（.SZ）
        suffix = "SS" if symbol.startswith("6") else "SZ"
        return f"{symbol}.{suffix}"
    raise ValueError(f"unknown market: {market}")


async def get_snapshot(symbol: str, market: str, trade_time: str | None = None) -> dict[str, Any]:
    """Return the snapshot fields used by flash review.

    Failures are surfaced as `None` rather than exceptions to avoid blocking the
    AI call. The result is sanitized: any NaN / inf is replaced with None so it
    is JSON-safe.
    """
    if market == "A":
        return _sanitize(_a_share_snapshot(symbol, trade_time))
    if market in ("HK", "US"):
        return _sanitize(_yf_snapshot(symbol, market, trade_time))
    return {"error": f"unsupported market: {market}"}


def _a_share_snapshot(symbol: str, trade_time: str | None) -> dict[str, Any]:
    snap: dict[str, Any] = {"market": "A"}
    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        return {**snap, "error": "akshare 未安装"}

    # 日线：近 60 日用于算 MA/MACD/RSI
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
        df_daily = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                      start_date=start, end_date=end, adjust="qfq")
    except Exception as e:
        log.warning("A股日线拉取失败 %s: %s", symbol, e)
        df_daily = None

    if df_daily is not None and len(df_daily) > 0:
        close = df_daily["收盘"].astype(float)
        open_p = df_daily["开盘"].astype(float)
        snap["open"] = float(open_p.iloc[-1])
        snap["last"] = float(close.iloc[-1])
        snap["daily_change_pct"] = round(
            (snap["last"] - snap["open"]) / snap["open"] * 100, 2
        ) if snap["open"] else None
        snap["ma5"] = round(float(close.tail(5).mean()), 2)
        snap["ma20"] = round(float(close.tail(20).mean()), 2)
        # 简化 MACD: DIF=EMA12-EMA26
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_hist = dif - dea
        last_hist = float(macd_hist.iloc[-1])
        prev_hist = float(macd_hist.iloc[-2]) if len(macd_hist) > 1 else last_hist
        direction = "红柱放大" if last_hist > prev_hist and last_hist > 0 else \
                    "红柱缩小" if last_hist > 0 else \
                    "绿柱放大" if last_hist < prev_hist else "绿柱缩小"
        golden_cross = "金叉" if last_hist > 0 and prev_hist <= 0 else \
                       "死叉" if last_hist < 0 and prev_hist >= 0 else "延续"
        snap["macd_note"] = f"{golden_cross} · {direction}"
        # RSI14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        snap["rsi"] = round(float(rsi.iloc[-1]), 1)

    # 盘中 5min K：算 pre30_change_pct
    if trade_time:
        try:
            date_compact = trade_time[:10].replace("-", "")
            df_min = ak.stock_zh_a_hist_min_em(
                symbol=symbol, period="5",
                start_date=f"{date_compact} 09:25:00",
                end_date=f"{date_compact} 15:05:00", adjust="qfq",
            )
            if len(df_min) > 0:
                # trade_time 格式: "2026-04-24 14:20:00"
                target = datetime.fromisoformat(trade_time)
                time_col = [c for c in df_min.columns if "时间" in c][0]
                close_col = [c for c in df_min.columns if "收盘" in c][0]
                df_min["_t"] = df_min[time_col].apply(
                    lambda x: datetime.fromisoformat(str(x).replace("/", "-")))
                before_30 = target - timedelta(minutes=30)
                now_row = df_min[df_min["_t"] <= target].tail(1)
                past_row = df_min[df_min["_t"] <= before_30].tail(1)
                if len(now_row) and len(past_row):
                    p_now = float(now_row[close_col].iloc[0])
                    p_past = float(past_row[close_col].iloc[0])
                    if p_past:
                        snap["pre30_change_pct"] = round((p_now - p_past) / p_past * 100, 2)
        except Exception as e:
            log.warning("A股分时拉取失败 %s: %s", symbol, e)

    # 大盘：上证
    try:
        df_idx = ak.stock_zh_index_daily_em(symbol="sh000001")
        if len(df_idx) > 1:
            last_c = _finite(df_idx["close"].iloc[-1])
            prev_c = _finite(df_idx["close"].iloc[-2])
            if last_c is not None and prev_c not in (None, 0):
                pct = round((last_c - prev_c) / prev_c * 100, 2)
                snap["index_change_pct"] = pct
                snap["index_note"] = f"上证 {last_c:.0f} ({pct:+.2f}%)"
    except Exception as e:
        log.warning("上证指数拉取失败: %s", e)

    snap["sector_note"] = "n/a"  # 板块占位，待 iFinD 板块数据接入

    # akshare 完全没拿到（学校网络封 eastmoney / 反爬等）→ yfinance 兜底
    if "last" not in snap or snap.get("last") is None:
        log.info("A股 %s akshare 无数据，转 yfinance 兜底", symbol)
        yf_snap = _yf_snapshot(symbol, "A", trade_time)
        if yf_snap.get("last") is not None:
            yf_snap["market"] = "A"
            yf_snap["source"] = "yfinance-fallback"
            yf_snap["sector_note"] = snap.get("sector_note", "n/a")
            snap = yf_snap

    # Optional iFinD natural-language enrichment. Skipped silently if no token.
    ifind_text = enrich_with_ifind_text(symbol, (trade_time or "")[:10] or None)
    if ifind_text:
        snap["ifind_text"] = ifind_text
    elif snap.get("last") is not None:
        # Fallback: build a one-line Chinese summary from the akshare numbers we
        # already have, so the prompt always carries a human-readable line even
        # without iFinD.
        snap["ifind_text"] = _compose_summary(symbol, snap)

    return snap


def _compose_summary(symbol: str, snap: dict[str, Any]) -> str:
    """One-line Chinese summary, built from local numbers — open-source friendly
    fallback for users who don't have an iFinD token."""
    parts = [f"{symbol}"]
    last = snap.get("last")
    chg = snap.get("daily_change_pct")
    if last is not None and chg is not None:
        parts.append(f"现价 {last}（{'+' if chg >= 0 else ''}{chg}%）")
    ma5 = snap.get("ma5")
    ma20 = snap.get("ma20")
    if ma5 is not None and ma20 is not None:
        parts.append(f"MA5 {ma5} / MA20 {ma20}")
    if snap.get("macd_note"):
        parts.append(f"MACD {snap['macd_note']}")
    if snap.get("rsi") is not None:
        parts.append(f"RSI {snap['rsi']}")
    if snap.get("index_note"):
        parts.append(f"大盘 {snap['index_note']}")
    return "；".join(parts)


def _yf_snapshot(symbol: str, market: str, trade_time: str | None) -> dict[str, Any]:
    snap: dict[str, Any] = {"market": market}
    try:
        import yfinance as yf
    except ImportError:
        return {**snap, "error": "yfinance 未安装"}

    try:
        ticker = yf.Ticker(_symbol_to_yf(symbol, market))
        hist = ticker.history(period="6mo", interval="1d", auto_adjust=True)
    except Exception as e:
        log.warning("yfinance 日线失败 %s: %s", symbol, e)
        return {**snap, "error": str(e)}

    if len(hist) == 0:
        return {**snap, "error": "yfinance 无数据"}

    close = hist["Close"]
    open_p = hist["Open"]
    snap["open"] = round(float(open_p.iloc[-1]), 2)
    snap["last"] = round(float(close.iloc[-1]), 2)
    snap["daily_change_pct"] = round((snap["last"] - snap["open"]) / snap["open"] * 100, 2)
    snap["ma5"] = round(float(close.tail(5).mean()), 2)
    snap["ma20"] = round(float(close.tail(20).mean()), 2)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist_macd = dif - dea
    last_h = float(hist_macd.iloc[-1])
    prev_h = float(hist_macd.iloc[-2]) if len(hist_macd) > 1 else last_h
    snap["macd_note"] = ("金叉 · " if last_h > 0 and prev_h <= 0 else
                         "死叉 · " if last_h < 0 and prev_h >= 0 else "延续 · ")
    snap["macd_note"] += ("红柱放大" if last_h > prev_h and last_h > 0 else
                          "红柱缩小" if last_h > 0 else
                          "绿柱放大" if last_h < prev_h else "绿柱缩小")

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    snap["rsi"] = round(float(rsi.iloc[-1]), 1)

    # 盘中 30 分钟变化（用 5m 或 15m）
    if trade_time:
        try:
            intra = ticker.history(period="2d", interval="5m", auto_adjust=True)
            if len(intra) > 6:
                target = datetime.fromisoformat(trade_time)
                before_30 = target - timedelta(minutes=30)
                # yfinance 时间带时区
                intra_idx_naive = intra.index.tz_localize(None) if intra.index.tz else intra.index
                mask_now = intra_idx_naive <= target
                mask_past = intra_idx_naive <= before_30
                if mask_now.any() and mask_past.any():
                    p_now = float(intra.loc[mask_now, "Close"].iloc[-1])
                    p_past = float(intra.loc[mask_past, "Close"].iloc[-1])
                    if p_past:
                        snap["pre30_change_pct"] = round((p_now - p_past) / p_past * 100, 2)
        except Exception as e:
            log.warning("yfinance 分时失败 %s: %s", symbol, e)

    # 大盘
    try:
        if market == "A":
            idx_symbol = "000001.SS"
            idx_name = "上证"
        elif market == "HK":
            idx_symbol = "^HSI"
            idx_name = "恒生"
        else:
            idx_symbol = "^IXIC"
            idx_name = "纳指"
        idx = yf.Ticker(idx_symbol).history(period="5d", interval="1d")
        if len(idx) > 1:
            last_c = _finite(idx["Close"].iloc[-1])
            prev_c = _finite(idx["Close"].iloc[-2])
            if last_c is not None and prev_c not in (None, 0):
                pct = round((last_c - prev_c) / prev_c * 100, 2)
                snap["index_change_pct"] = pct
                snap["index_note"] = f"{idx_name} {last_c:.0f} ({pct:+.2f}%)"
    except Exception as e:
        log.warning("大盘指数失败: %s", e)

    snap["sector_note"] = "n/a"
    return snap
