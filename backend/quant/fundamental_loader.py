"""基本面日频数据落地(百度估值)。

百度估值 stock_zh_valuation_baidu 给的是 point-in-time 日频序列:
  PE-TTM / PB / 总市值 —— period='近三年' 拿满 3 年日频。
用于价值因子(EP=1/PE, BP=1/PB)和规模因子(Size=-ln(MV))的回测,
避免用最新财报回填历史造成的未来函数(look-ahead bias)。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import akshare as ak
import pandas as pd

from backend.db.repo import _connect
from backend.quant.universe import mainboard_universe


_INDICATORS = {
    "市盈率(TTM)": "pe_ttm",
    "市净率": "pb",
    "总市值": "total_mv",
}


@dataclass
class FundLoadResult:
    symbol: str
    rows: int
    error: str | None = None


def _fetch_indicator(symbol: str, indicator: str, period: str) -> pd.Series | None:
    for attempt in range(3):
        try:
            df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period=period)
            if df is None or df.empty:
                return None
            s = df.set_index("date")["value"]
            s.index = pd.to_datetime(s.index).strftime("%Y-%m-%d")
            return s
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return None


def load_one_fundamental(symbol: str, period: str = "近三年") -> FundLoadResult:
    series: dict[str, pd.Series] = {}
    try:
        for ind, col in _INDICATORS.items():
            s = _fetch_indicator(symbol, ind, period)
            if s is not None:
                series[col] = s
    except Exception as e:
        return FundLoadResult(symbol, 0, error=str(e)[:120])
    if not series:
        return FundLoadResult(symbol, 0, error="no data")

    df = pd.DataFrame(series)
    df.index.name = "trade_date"
    df = df.reset_index()
    df["symbol"] = symbol
    for col in ("pe_ttm", "pb", "total_mv"):
        if col not in df.columns:
            df[col] = None
    rows = df[["symbol", "trade_date", "pe_ttm", "pb", "total_mv"]].to_dict("records")
    with _connect() as c:
        c.executemany(
            """INSERT OR REPLACE INTO fundamental_quotes
               (symbol, trade_date, pe_ttm, pb, total_mv)
               VALUES (:symbol, :trade_date, :pe_ttm, :pb, :total_mv)""",
            rows,
        )
        c.commit()
    return FundLoadResult(symbol, len(rows))


def load_fundamentals(symbols=None, limit: int | None = None,
                      max_workers: int = 3, period: str = "近三年") -> list[FundLoadResult]:
    if symbols is None:
        rows = mainboard_universe()
        if limit:
            rows = rows[:limit]
        symbols = [r.symbol for r in rows]
    print(f"[fundamental] 加载 {len(symbols)} 只 × 3 指标 ({period}) ...")
    results: list[FundLoadResult] = []
    done = err = 0
    total = len(symbols)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(load_one_fundamental, s, period): s for s in symbols}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if r.error:
                err += 1
            if done % 25 == 0 or done == total:
                print(f"  [fundamental] {done}/{total}  err={err}", flush=True)
    return results


def fundamental_panel(symbols, col: str) -> pd.DataFrame:
    """读 fundamental_quotes 为宽表 (index=date, columns=symbol)。col ∈ pe_ttm/pb/total_mv。"""
    syms = list(symbols)
    placeholder = ",".join("?" * len(syms))
    sql = (f"SELECT symbol, trade_date, {col} FROM fundamental_quotes "
           f"WHERE symbol IN ({placeholder}) ORDER BY trade_date")
    with _connect() as c:
        df = pd.read_sql_query(sql, c, params=syms)
    if df.empty:
        return df
    return df.pivot(index="trade_date", columns="symbol", values=col).sort_index()


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    res = load_fundamentals(limit=limit)
    ok = sum(1 for r in res if r.error is None)
    rows = sum(r.rows for r in res)
    print(f"  完成 {ok}/{len(res)}, 插入 {rows} 行")
