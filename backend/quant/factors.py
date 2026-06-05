"""因子库 v1.1 — 价量 + 价值 + 规模(经 3 年回测验证)。

因子集(全部已统一成"值越大越好"):
  Rev_5       短期反转   -(过去 5 日收益)              ICIR≈+0.30
  LowVol_60   低波动     -std(60 日日收益率)           ICIR≈+0.20
  BP          价值       1/PB (净资产/价格)            ICIR≈+0.24
  SmallSize   小市值     -ln(总市值)                   ICIR≈+0.19
  EP          盈利收益率 1/PE_TTM (默认不入池,可选)     ICIR≈+0.14

v1.0 的 Mom_20 / Mom_60 / AmpUp_5_60 经回测确认在 A 股主板是**负 IC**
(动量反转、追放量被套),已从合成中剔除。详见 backend/quant/backtest.py。

价值/规模因子来自 fundamental_quotes(百度估值 point-in-time)。
全市场截面 winsorize(1/99%) + z-score 后等权合成。
注:仍是全市场 z-score,行业中性化留待后续(SH 行业字段缺失)。
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from backend.db.repo import _connect


# 默认入池的已验证因子(EP 较弱,默认不含,可通过 include 开启)
FACTOR_NAMES = ["Rev_5", "LowVol_60", "BP", "SmallSize"]
ALL_FACTORS = ["Rev_5", "LowVol_60", "BP", "SmallSize", "EP"]


def _winsorize(s: pd.Series, lo: float = 0.01, hi: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s
    qlo, qhi = s.quantile([lo, hi])
    return s.clip(lower=qlo, upper=qhi)


def _zscore(s: pd.Series) -> pd.Series:
    s = _winsorize(s)
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sd


def _price_factors(group: pd.DataFrame) -> dict:
    """单股价量因子。group 按日期升序。"""
    if len(group) < 65:
        return {}
    closes = group["close"].to_numpy(dtype="float64")
    rets = group["pct_chg"].to_numpy(dtype="float64") / 100.0
    rev_5 = -(closes[-1] / closes[-6] - 1.0)
    vol_60 = np.nanstd(rets[-60:])
    low_vol = -vol_60 if vol_60 == vol_60 else np.nan
    return {"Rev_5": rev_5, "LowVol_60": low_vol}


def _latest_fundamentals(as_of: str, symbols: list[str]) -> pd.DataFrame:
    """每只股票截至 as_of 最近一条 PE/PB/市值(point-in-time)。"""
    placeholder = ",".join("?" * len(symbols))
    sql = f"""
        SELECT f.symbol, f.pe_ttm, f.pb, f.total_mv
        FROM fundamental_quotes f
        JOIN (SELECT symbol, MAX(trade_date) md FROM fundamental_quotes
              WHERE trade_date <= ? AND symbol IN ({placeholder})
              GROUP BY symbol) m
          ON f.symbol = m.symbol AND f.trade_date = m.md
    """
    with _connect() as c:
        df = pd.read_sql_query(sql, c, params=[as_of, *symbols])
    return df.set_index("symbol") if not df.empty else df


def compute_factors(as_of: str | None = None,
                    symbols: Iterable[str] | None = None,
                    include: list[str] | None = None,
                    weights: dict[str, float] | None = None) -> pd.DataFrame:
    """计算截至 as_of 的因子值 + composite + rank。
    include 指定参与合成的因子;默认 FACTOR_NAMES(已验证 4 因子)。
    weights 指定各因子权重(未给到的因子按 1.0);None = 等权(与历史行为一致)。"""
    as_of = as_of or date.today().strftime("%Y-%m-%d")
    use = include or FACTOR_NAMES

    sql = "SELECT symbol, trade_date, close, pct_chg FROM daily_quotes WHERE adjust='hfq' AND trade_date <= ?"
    params: list = [as_of]
    if symbols:
        syms = list(symbols)
        placeholder = ",".join("?" * len(syms))
        sql += f" AND symbol IN ({placeholder})"
        params.extend(syms)
    sql += " ORDER BY symbol, trade_date"
    with _connect() as c:
        px = pd.read_sql_query(sql, c, params=params)
    if px.empty:
        return pd.DataFrame()

    # 价量因子
    records = []
    for sym, g in px.groupby("symbol", sort=False):
        d = _price_factors(g)
        if not d:
            continue
        d["symbol"] = sym
        d["latest_close"] = float(g["close"].iloc[-1])
        d["latest_date"] = g["trade_date"].iloc[-1]
        records.append(d)
    out = pd.DataFrame.from_records(records)
    if out.empty:
        return out
    out = out.set_index("symbol")

    # 价值/规模因子
    fund = _latest_fundamentals(as_of, out.index.to_list())
    if not fund.empty:
        pe = fund["pe_ttm"]
        pb = fund["pb"]
        mv = fund["total_mv"]
        out["BP"] = (1.0 / pb.where(pb > 0)).reindex(out.index)
        out["EP"] = (1.0 / pe.where(pe > 0)).reindex(out.index)
        out["SmallSize"] = (-np.log(mv.where(mv > 0))).reindex(out.index)
    for f in ALL_FACTORS:
        if f not in out.columns:
            out[f] = np.nan

    # 只保留入池因子齐全的股票,保证截面公平(缺基本面的不参与排名)
    out = out.dropna(subset=use)
    if out.empty:
        return out.reset_index()

    # 截面 z-score + (加权)合成
    for f in use:
        out[f"{f}_z"] = _zscore(out[f].astype(float))
    z_cols = [f"{f}_z" for f in use]
    if weights:
        w = np.array([float(weights.get(f, 1.0)) for f in use])
        out["composite"] = (out[z_cols].to_numpy() * w).sum(axis=1) / w.sum()
    else:
        out["composite"] = out[z_cols].mean(axis=1)
    out["rank"] = out["composite"].rank(ascending=False, method="min").astype(int)
    out = out.reset_index().sort_values("rank").reset_index(drop=True)
    return out


def persist_snapshot(df: pd.DataFrame, snapshot_date: str,
                     factor_names: list[str] | None = None) -> int:
    import json
    if df.empty:
        return 0
    names = factor_names or FACTOR_NAMES
    rows = []
    for _, r in df.iterrows():
        factors = {f: (None if pd.isna(r.get(f)) else float(r[f])) for f in names}
        rows.append({
            "snapshot_date": snapshot_date,
            "symbol": r["symbol"],
            "factors_json": json.dumps(factors, ensure_ascii=False),
            "composite": (None if pd.isna(r["composite"]) else float(r["composite"])),
            "rank": int(r["rank"]),
        })
    with _connect() as c:
        c.executemany(
            """INSERT OR REPLACE INTO factor_snapshots
               (snapshot_date, symbol, factors_json, composite, rank)
               VALUES (:snapshot_date, :symbol, :factors_json, :composite, :rank)""",
            rows,
        )
        c.commit()
    return len(rows)


if __name__ == "__main__":
    df = compute_factors()
    if df.empty:
        print("[factors] 还没有数据,请先跑 data_loader + fundamental_loader")
    else:
        print(f"[factors] v1.1 截面共 {len(df)} 只  (因子: {FACTOR_NAMES})")
        cols = ["symbol", "composite", "rank"] + [f"{f}_z" for f in FACTOR_NAMES]
        print(df.head(15)[cols].to_string(index=False))
