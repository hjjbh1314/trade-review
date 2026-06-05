"""行情数据落地。

策略：
  - 用 akshare.stock_zh_a_hist（后复权）逐只拉，并发 ThreadPoolExecutor。
  - 增量更新：查本地最新日期，从下一日开始拉。
  - 落到 SQLite 的 daily_quotes 表（schema 已在 backend/db/schema.sql 定义）。
"""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

import akshare as ak
import pandas as pd

from backend.db.repo import DB_PATH, _connect
from backend.quant.universe import UniverseRow, mainboard_universe, _classify


def _tx_symbol(sym: str) -> str:
    """腾讯接口要 sh600519 / sz000001 这种小写前缀。"""
    exch, _ = _classify(sym)
    return f"{exch.lower()}{sym}"


@dataclass
class LoadResult:
    symbol: str
    rows_inserted: int
    error: str | None = None


def _existing_latest(symbol: str) -> str | None:
    with _connect() as c:
        row = c.execute(
            "SELECT MAX(trade_date) AS d FROM daily_quotes WHERE symbol = ? AND adjust = 'hfq'",
            (symbol,),
        ).fetchone()
        return row["d"] if row and row["d"] else None


def _fetch_one(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """腾讯接口拉后复权日线。返回长表，列含 pct_chg（本地从 close 推导）。"""
    last_err: Exception | None = None
    tx_sym = _tx_symbol(symbol)
    for attempt in range(4):
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=tx_sym, start_date=start, end_date=end, adjust="hfq",
            )
            if df is None or df.empty:
                return None
            df = df.rename(columns={"date": "trade_date"})
            df["symbol"] = symbol
            df["adjust"] = "hfq"
            df["volume"] = df["amount"]
            df["turnover"] = None
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
            df = df.sort_values("trade_date").reset_index(drop=True)
            df["pct_chg"] = df["close"].pct_change() * 100.0
            keep = ["symbol", "trade_date", "open", "high", "low", "close",
                    "volume", "amount", "turnover", "pct_chg", "adjust"]
            return df[keep]
        except Exception as e:
            last_err = e
            time.sleep(min(2 ** attempt, 8))
    if last_err:
        raise last_err
    return None


def _bulk_insert(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    rows = df.to_dict("records")
    with _connect() as c:
        c.executemany(
            """INSERT OR REPLACE INTO daily_quotes
               (symbol, trade_date, open, high, low, close, volume, amount,
                turnover, pct_chg, adjust)
               VALUES (:symbol, :trade_date, :open, :high, :low, :close,
                       :volume, :amount, :turnover, :pct_chg, :adjust)""",
            rows,
        )
        c.commit()
    return len(rows)


def _fmt(d: str | date) -> str:
    """统一日期格式 YYYY-MM-DD（腾讯接口要这个格式）。"""
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    if "-" in d:
        return d
    # YYYYMMDD → YYYY-MM-DD
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def load_one(symbol: str, lookback_days: int = 250,
             end_date: str | None = None, backfill: bool = False) -> LoadResult:
    """单股加载（腾讯接口）。end_date 接受 YYYY-MM-DD 或 YYYYMMDD。

    backfill=True 时忽略增量逻辑,拉满 lookback 整段;靠 INSERT OR REPLACE
    幂等覆盖重叠行(同为 hfq,数据一致),并补上更早的历史 —— 非破坏性。
    """
    end_str = _fmt(end_date) if end_date else date.today().strftime("%Y-%m-%d")
    full_start = (date.today() - timedelta(days=int(lookback_days * 1.6))).strftime("%Y-%m-%d")
    if backfill:
        start_str = full_start
    else:
        latest = _existing_latest(symbol)
        if latest:
            next_day = datetime.strptime(latest, "%Y-%m-%d").date() + timedelta(days=1)
            start_str = next_day.strftime("%Y-%m-%d")
            if start_str > end_str:
                return LoadResult(symbol, 0)
        else:
            start_str = full_start
    try:
        df = _fetch_one(symbol, start_str, end_str)
        n = _bulk_insert(df) if df is not None else 0
        return LoadResult(symbol, n)
    except Exception as e:
        return LoadResult(symbol, 0, error=str(e)[:120])


def load_batch(symbols: Sequence[str], lookback_days: int = 250,
               max_workers: int = 2, end_date: str | None = None,
               progress: bool = True, backfill: bool = False) -> list[LoadResult]:
    """并发批量加载。max_workers 默认 2 (eastmoney 限流敏感)。"""
    results: list[LoadResult] = []
    total = len(symbols)
    done = 0
    err = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(load_one, s, lookback_days, end_date, backfill): s for s in symbols}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if r.error:
                err += 1
            if progress and (done % 20 == 0 or done == total):
                print(f"  [data_loader] {done}/{total}  err={err}", flush=True)
    return results


def load_mainboard(lookback_days: int = 250, max_workers: int = 2,
                   limit: int | None = None) -> list[LoadResult]:
    """主板全量（可 limit 跑子集做冒烟测试）。"""
    rows = mainboard_universe()
    if limit:
        rows = rows[:limit]
    print(f"[data_loader] mainboard total = {len(rows)}, lookback = {lookback_days}d")
    syms = [r.symbol for r in rows]
    return load_batch(syms, lookback_days=lookback_days, max_workers=max_workers)


def quotes_panel(symbols: Iterable[str], n_days: int = 250) -> pd.DataFrame:
    """读取本地 daily_quotes 为长表（symbol, trade_date, open, ..., turnover, pct_chg）。"""
    syms = list(symbols)
    if not syms:
        return pd.DataFrame()
    placeholder = ",".join("?" * len(syms))
    sql = f"""SELECT symbol, trade_date, open, high, low, close, volume, amount,
                     turnover, pct_chg
              FROM daily_quotes
              WHERE adjust = 'hfq' AND symbol IN ({placeholder})
              ORDER BY symbol, trade_date"""
    with _connect() as c:
        df = pd.read_sql_query(sql, c, params=syms)
    return df


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"[smoke] 加载前 {limit} 只主板的近 250 个交易日…")
    t0 = time.time()
    res = load_mainboard(limit=limit, max_workers=2)
    ok = sum(1 for r in res if r.error is None)
    inserted = sum(r.rows_inserted for r in res)
    print(f"  完成 {ok}/{len(res)},  插入 {inserted} 行,  耗时 {time.time()-t0:.1f}s")
    syms = [r.symbol for r in res if r.error is None]
    panel = quotes_panel(syms)
    print(f"  panel shape: {panel.shape}")
    if not panel.empty:
        print(panel.tail(5).to_string(index=False))
