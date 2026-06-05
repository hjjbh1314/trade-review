"""主板股票池构建。

排除项 (用户硬性偏好):
  - 创业板 (SZ 30x)
  - 科创板 (SH 688x / 689x)
  - 北交所 (BJ 4xx/8xx/9xx)
  - ST / *ST / 退市
  - 上市不足 365 个自然日的次新股 (basis 效应让 Mom_60 失真)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

import akshare as ak
import pandas as pd


@dataclass(frozen=True)
class UniverseRow:
    symbol: str            # 6位代码 600519
    name: str
    exchange: str          # SH / SZ
    is_mainboard: bool
    listing_date: str = "" # YYYY-MM-DD
    industry: str = ""
    total_shares: float = 0.0
    float_shares: float = 0.0


def _classify(symbol: str) -> tuple[str, bool]:
    """返回 (exchange, is_mainboard)。"""
    if symbol.startswith("6"):
        if symbol.startswith(("688", "689")):
            return "SH", False
        return "SH", True
    if symbol.startswith(("000", "001", "002", "003")):
        return "SZ", True
    if symbol.startswith("3"):
        return "SZ", False
    if symbol.startswith(("4", "8", "9")):
        return "BJ", False
    return "?", False


def _coalesce(*vals) -> str:
    """跨交易所列名容错: 取第一个非空非 NaN 的字符串值。"""
    for v in vals:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except (TypeError, ValueError):
            pass
        s = str(v).strip()
        if s and s.lower() != "nan":
            return s
    return ""


def _parse_shares(v) -> float:
    """'19,405,918,198' → 1.94e10。"""
    if v is None:
        return 0.0
    s = str(v).replace(",", "").strip()
    if not s or s in ("-", "--"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@lru_cache(maxsize=1)
def _enriched_listing() -> pd.DataFrame:
    """主板专用:深交所 + 上交所主板列表,含上市日期/总股本/行业。"""
    frames = []
    for attempt in range(3):
        try:
            sz = ak.stock_info_sz_name_code(symbol="A股列表")
            sz = sz[sz["板块"].astype(str).str.contains("主板", na=False)].copy()
            sz["exchange"] = "SZ"
            frames.append(sz)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    for attempt in range(3):
        try:
            sh = ak.stock_info_sh_name_code(symbol="主板A股")
            sh["exchange"] = "SH"
            frames.append(sh)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    df = pd.concat(frames, ignore_index=True, sort=False)
    return df


def mainboard_universe(exclude_st: bool = True,
                       min_days_since_listing: int = 365) -> list[UniverseRow]:
    """主板股票池。默认排除 ST 和上市不足 1 年的次新。"""
    df = _enriched_listing()
    cutoff = (date.today() - timedelta(days=min_days_since_listing)).strftime("%Y-%m-%d")

    rows: list[UniverseRow] = []
    for _, r in df.iterrows():
        sym = _coalesce(r.get("A股代码"), r.get("证券代码"))
        sym = sym.zfill(6) if sym else ""
        name = _coalesce(r.get("A股简称"), r.get("证券简称"))
        if not sym or len(sym) != 6 or not sym.isdigit():
            continue
        exch, mb = _classify(sym)
        if not mb:
            continue
        if exclude_st and ("ST" in name.upper() or name.startswith("退")):
            continue
        ld = _coalesce(r.get("A股上市日期"), r.get("上市日期"))
        # SH 接口返回的可能是 datetime.date,统一成 YYYY-MM-DD
        if ld and ld > cutoff:
            continue  # 次新过滤

        rows.append(UniverseRow(
            symbol=sym, name=name, exchange=exch, is_mainboard=True,
            listing_date=ld,
            industry=_coalesce(r.get("所属行业")),
            total_shares=_parse_shares(_coalesce(r.get("A股总股本"), r.get("总股本"))),
            float_shares=_parse_shares(_coalesce(r.get("A股流通股本"), r.get("流通股本"))),
        ))
    # 去重 (深沪重叠的极少数情况)
    seen: set[str] = set()
    uniq: list[UniverseRow] = []
    for r in rows:
        if r.symbol in seen:
            continue
        seen.add(r.symbol)
        uniq.append(r)
    return uniq


def symbol_to_ak(sym: str) -> str:
    """akshare 历史行情接口要的是纯 6 位数字（不带前缀）。"""
    return sym


def symbol_with_prefix(sym: str) -> str:
    """有些接口需要 SH600519 / SZ000001 形式。"""
    exch, _ = _classify(sym)
    return f"{exch}{sym}"


if __name__ == "__main__":
    rows = mainboard_universe()
    print(f"[universe] 主板共 {len(rows)} 只 (排除 ST + 次新 <365 日)")
    by_ex: dict[str, int] = {}
    by_ind: dict[str, int] = {}
    for r in rows:
        by_ex[r.exchange] = by_ex.get(r.exchange, 0) + 1
        by_ind[r.industry] = by_ind.get(r.industry, 0) + 1
    print(f"  按交易所: {by_ex}")
    top_ind = sorted(by_ind.items(), key=lambda x: -x[1])[:8]
    print(f"  主要行业: {top_ind}")
    print("  样本前 5:")
    for r in rows[:5]:
        mc = r.total_shares / 1e8
        print(f"    {r.symbol} {r.name:<8} 上市={r.listing_date}  总股本={mc:>6.1f}亿  {r.industry}")
