"""向量化回测 — 验证 multifactor_v1 是否有 alpha。

三件事：
  1. Rank-IC 序列    每个调仓日 spearman(composite, 未来 h 日收益)
                     看 IC 均值 / IR(均值/标准差) / IC>0 占比
  2. 分组收益        按 composite 分 5 组,看高分组是否单调跑赢低分组
  3. Top-N 组合净值  每 h 日等权持有 Top N,对比等权基准

全程用后复权 close,正确处理分红除权。
注意:本地数据 ~264 个交易日,扣 130 日预热后约 130 日可评估 —— 这是冒烟
级别的验证,不是定论。IC 方向 + 分组单调性比绝对数值更有参考价值。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.db.repo import _connect
from backend.quant.fundamental_loader import fundamental_panel
from backend.quant.universe import mainboard_universe


WARMUP = 130          # 因子最小历史
MIN_NAMES = 50        # 截面至少多少只才算有效

# 因子方向: +1 表示"值越大越好",-1 表示"值越小越好(取负后入池)"。
# 这里只定义原始构造,符号在 _factor_panels 里已处理成"越大越好"。
PRICE_FACTORS = ["Mom_20", "Mom_60", "Rev_5", "LowVol_60", "AmpUp_5_60"]
VALUE_FACTORS = ["EP", "BP", "SmallSize"]


# ─── 数据加载 + 因子矩阵 ──────────────────────────────────────────────

def _load_wide() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """返回 (close, ret, amount) 三个宽表: index=trade_date, columns=symbol。"""
    universe = {r.symbol for r in mainboard_universe()}
    placeholder = ",".join("?" * len(universe))
    sql = (f"SELECT symbol, trade_date, close, pct_chg, amount FROM daily_quotes "
           f"WHERE adjust='hfq' AND symbol IN ({placeholder}) ORDER BY trade_date")
    with _connect() as c:
        df = pd.read_sql_query(sql, c, params=list(universe))
    close = df.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    amount = df.pivot(index="trade_date", columns="symbol", values="amount").sort_index()
    ret = close.pct_change()
    return close, ret, amount


def _factor_panels(close: pd.DataFrame, ret: pd.DataFrame,
                   amount: pd.DataFrame,
                   with_fundamentals: bool = True) -> dict[str, pd.DataFrame]:
    """向量化算因子,每个返回一个 date×symbol 宽表(已统一成'越大越好')。"""
    mom20 = close / close.shift(20) - 1.0
    mom60 = close / close.shift(60) - 1.0
    rev5 = -(close / close.shift(5) - 1.0)
    lowvol = -ret.rolling(60).std()
    amp = amount.rolling(5).sum() / amount.rolling(60).sum() * 12.0
    panels = {"Mom_20": mom20, "Mom_60": mom60, "Rev_5": rev5,
              "LowVol_60": lowvol, "AmpUp_5_60": amp}

    if with_fundamentals:
        symbols = close.columns.to_list()
        pe = fundamental_panel(symbols, "pe_ttm")
        pb = fundamental_panel(symbols, "pb")
        mv = fundamental_panel(symbols, "total_mv")
        if not pe.empty:
            # 对齐到价格交易日,point-in-time 前向填充(只用当日及之前已知的估值)
            pe = pe.reindex(index=close.index, columns=close.columns).ffill()
            pb = pb.reindex(index=close.index, columns=close.columns).ffill()
            mv = mv.reindex(index=close.index, columns=close.columns).ffill()
            # 价值: 盈利/账面收益率。亏损或负净资产 → NaN(排除出价值排名)
            ep = 1.0 / pe.where(pe > 0)
            bp = 1.0 / pb.where(pb > 0)
            small = -np.log(mv.where(mv > 0))   # 小市值溢价: 市值越小分越高
            panels.update({"EP": ep, "BP": bp, "SmallSize": small})
    return panels


def _cross_z(row: pd.Series) -> pd.Series:
    """单日截面 winsorize(1/99%) + z-score。"""
    s = row.dropna()
    if len(s) < MIN_NAMES:
        return pd.Series(np.nan, index=row.index)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(np.nan, index=row.index)
    return ((row.clip(lo, hi) - mu) / sd)


def _composite(panels: dict[str, pd.DataFrame],
               include: list[str] | None = None,
               weights: dict[str, float] | None = None) -> pd.DataFrame:
    """各因子逐日截面 z-score 后(加权)平均 → composite 宽表。
    include 指定参与的因子名;None = 全部。weights 给权重,None = 等权。"""
    names = [n for n in (include or list(panels.keys())) if n in panels]
    zs = [panels[n].apply(_cross_z, axis=1) for n in names]
    if weights:
        w = [float(weights.get(n, 1.0)) for n in names]
        return sum(z * wi for z, wi in zip(zs, w)) / sum(w)
    return sum(zs) / len(zs)


# ─── 评估 ─────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    horizon: int
    n_dates: int
    ic_mean: float
    ic_ir: float
    ic_pos_ratio: float
    group_returns: list[float]          # 低分→高分 5 组平均未来收益
    long_short: float                   # 高分组 - 低分组
    topn_annual: float
    topn_sharpe: float
    topn_mdd: float
    bench_annual: float
    topn_equity: list[float] = field(default_factory=list)
    bench_equity: list[float] = field(default_factory=list)


def run_backtest(horizon: int = 5, top_n: int = 20,
                 n_groups: int = 5,
                 include: list[str] | None = None,
                 weights: dict[str, float] | None = None) -> BacktestResult:
    close, ret, amount = _load_wide()
    panels = _factor_panels(close, ret, amount)
    comp = _composite(panels, include=include, weights=weights)

    dates = close.index.to_list()
    eval_idx = range(WARMUP, len(dates) - horizon)

    # 未来 h 日收益宽表
    fwd = close.shift(-horizon) / close - 1.0

    ic_list: list[float] = []
    group_acc = np.zeros(n_groups)
    group_cnt = 0
    # 非重叠调仓收益 (Top-N 等权 vs 等权基准)
    topn_rets: list[float] = []
    bench_rets: list[float] = []
    next_rebalance = WARMUP

    for i in eval_idx:
        d = dates[i]
        c_row = comp.loc[d].dropna()
        f_row = fwd.loc[d].dropna()
        common = c_row.index.intersection(f_row.index)
        if len(common) < MIN_NAMES:
            continue
        cr = c_row[common]
        fr = f_row[common]

        # Rank IC
        ic = cr.rank().corr(fr.rank())
        if not np.isnan(ic):
            ic_list.append(ic)

        # 分组(低→高)
        try:
            grp = pd.qcut(cr, n_groups, labels=False, duplicates="drop")
            gmean = fr.groupby(grp).mean()
            if len(gmean) == n_groups:
                group_acc += gmean.to_numpy()
                group_cnt += 1
        except ValueError:
            pass

        # 非重叠调仓:每 horizon 天建一次 Top-N
        if i >= next_rebalance:
            top = cr.sort_values(ascending=False).head(top_n).index
            topn_rets.append(float(fr[top].mean()))
            bench_rets.append(float(fr.mean()))
            next_rebalance = i + horizon

    ic_arr = np.array(ic_list)
    ic_mean = float(ic_arr.mean()) if len(ic_arr) else 0.0
    ic_ir = float(ic_arr.mean() / ic_arr.std(ddof=0)) if ic_arr.std(ddof=0) > 0 else 0.0
    ic_pos = float((ic_arr > 0).mean()) if len(ic_arr) else 0.0

    group_returns = (group_acc / group_cnt).tolist() if group_cnt else [0.0] * n_groups
    long_short = group_returns[-1] - group_returns[0] if group_returns else 0.0

    # 组合净值 (复利)
    topn_eq = np.cumprod(1.0 + np.array(topn_rets)) if topn_rets else np.array([1.0])
    bench_eq = np.cumprod(1.0 + np.array(bench_rets)) if bench_rets else np.array([1.0])
    periods_per_year = 252 / horizon
    n_reb = len(topn_rets)

    def _annual(eq: np.ndarray, n: int) -> float:
        if n == 0 or eq[-1] <= 0:
            return 0.0
        return float(eq[-1] ** (periods_per_year / n) - 1.0)

    topn_arr = np.array(topn_rets)
    topn_sharpe = (float(topn_arr.mean() / topn_arr.std(ddof=0) * np.sqrt(periods_per_year))
                   if len(topn_arr) and topn_arr.std(ddof=0) > 0 else 0.0)
    peak = np.maximum.accumulate(topn_eq)
    mdd = float(((topn_eq - peak) / peak).min()) if len(topn_eq) else 0.0

    return BacktestResult(
        horizon=horizon, n_dates=len(ic_arr),
        ic_mean=ic_mean, ic_ir=ic_ir, ic_pos_ratio=ic_pos,
        group_returns=group_returns, long_short=long_short,
        topn_annual=_annual(topn_eq, n_reb), topn_sharpe=topn_sharpe, topn_mdd=mdd,
        bench_annual=_annual(bench_eq, n_reb),
        topn_equity=topn_eq.tolist(), bench_equity=bench_eq.tolist(),
    )


def factor_ic_breakdown(horizon: int = 10) -> dict[str, dict[str, float]]:
    """每个因子单独的 Rank-IC 均值 / ICIR / IC>0 占比。"""
    close, ret, amount = _load_wide()
    panels = _factor_panels(close, ret, amount)
    fwd = close.shift(-horizon) / close - 1.0
    dates = close.index.to_list()
    out: dict[str, dict[str, float]] = {}
    for name, panel in panels.items():
        ics = []
        for i in range(WARMUP, len(dates) - horizon):
            d = dates[i]
            fr = fwd.loc[d].dropna()
            pr = panel.loc[d].dropna()
            common = fr.index.intersection(pr.index)
            if len(common) < MIN_NAMES:
                continue
            ic = pr[common].rank().corr(fr[common].rank())
            if not np.isnan(ic):
                ics.append(ic)
        arr = np.array(ics)
        out[name] = {
            "ic": float(arr.mean()) if len(arr) else 0.0,
            "icir": float(arr.mean() / arr.std(ddof=0)) if len(arr) and arr.std(ddof=0) > 0 else 0.0,
            "pos": float((arr > 0).mean()) if len(arr) else 0.0,
            "n": len(arr),
        }
    return out


def _ic_series(comp: pd.DataFrame, fwd: pd.DataFrame,
               date_list: list[str]) -> np.ndarray:
    ics = []
    for d in date_list:
        cr = comp.loc[d].dropna()
        fr = fwd.loc[d].dropna()
        common = cr.index.intersection(fr.index)
        if len(common) < MIN_NAMES:
            continue
        ic = cr[common].rank().corr(fr[common].rank())
        if not np.isnan(ic):
            ics.append(ic)
    return np.array(ics)


def _topn_oos(comp: pd.DataFrame, fwd: pd.DataFrame, dates: list[str],
              idx_range: range, horizon: int, top_n: int) -> tuple[float, float, float]:
    """非重叠调仓 Top-N 组合 vs 等权基准。返回 (年化, 夏普, 基准年化)。"""
    topn_rets, bench_rets = [], []
    nxt = idx_range.start
    for i in idx_range:
        if i < nxt:
            continue
        d = dates[i]
        cr = comp.loc[d].dropna()
        fr = fwd.loc[d].dropna()
        common = cr.index.intersection(fr.index)
        if len(common) < MIN_NAMES:
            continue
        top = cr[common].sort_values(ascending=False).head(top_n).index
        topn_rets.append(float(fr[top].mean()))
        bench_rets.append(float(fr[common].mean()))
        nxt = i + horizon
    if not topn_rets:
        return 0.0, 0.0, 0.0
    ppy = 252 / horizon
    n = len(topn_rets)
    teq = np.cumprod(1 + np.array(topn_rets))
    beq = np.cumprod(1 + np.array(bench_rets))
    arr = np.array(topn_rets)
    sharpe = float(arr.mean() / arr.std(ddof=0) * np.sqrt(ppy)) if arr.std(ddof=0) > 0 else 0.0
    ann = float(teq[-1] ** (ppy / n) - 1) if teq[-1] > 0 else 0.0
    bann = float(beq[-1] ** (ppy / n) - 1) if beq[-1] > 0 else 0.0
    return ann, sharpe, bann


def walk_forward(horizon: int = 10, top_n: int = 20,
                 split_date: str = "2025-01-01") -> dict:
    """前段选因子(train),后段检验(test)。split_date 之前 train,之后 test。"""
    close, ret, amount = _load_wide()
    panels = _factor_panels(close, ret, amount)
    fwd = close.shift(-horizon) / close - 1.0
    dates = close.index.to_list()

    eval_dates = dates[WARMUP:len(dates) - horizon]
    train_dates = [d for d in eval_dates if d < split_date]
    test_dates = [d for d in eval_dates if d >= split_date]

    # 1. train 期单因子 IC,挑正 IC 的
    z_panels = {n: p.apply(_cross_z, axis=1) for n, p in panels.items()}
    train_ic = {n: float(_ic_series(z, fwd, train_dates).mean()) for n, z in z_panels.items()}
    test_ic = {n: float(_ic_series(z, fwd, test_dates).mean()) for n, z in z_panels.items()}
    selected = [n for n, ic in train_ic.items() if ic > 0]

    # 2. 用 train 选出的因子在 test 上检验组合
    comp_sel = sum(z_panels[n] for n in selected) / len(selected)
    test_arr = _ic_series(comp_sel, fwd, test_dates)
    ic_mean = float(test_arr.mean()) if len(test_arr) else 0.0
    ic_ir = float(test_arr.mean() / test_arr.std(ddof=0)) if test_arr.std(ddof=0) > 0 else 0.0
    ic_pos = float((test_arr > 0).mean()) if len(test_arr) else 0.0

    test_start_i = next(i for i, d in enumerate(dates) if d >= split_date)
    ann, sharpe, bann = _topn_oos(comp_sel, fwd, dates,
                                  range(test_start_i, len(dates) - horizon), horizon, top_n)
    return {
        "train_range": (train_dates[0], train_dates[-1]),
        "test_range": (test_dates[0], test_dates[-1]),
        "train_ic": train_ic, "test_ic": test_ic, "selected": selected,
        "test_composite_ic": ic_mean, "test_composite_icir": ic_ir, "test_ic_pos": ic_pos,
        "test_topn_annual": ann, "test_topn_sharpe": sharpe, "test_bench_annual": bann,
    }


def backtest_strategy(name: str, horizon: int = 10,
                      top_n: int | None = None) -> BacktestResult:
    """按注册表里的策略名跑回测(用它的因子子集 + 权重)。"""
    from backend.quant.strategies import get

    s = get(name)
    return run_backtest(horizon=horizon, top_n=top_n or s.top_n,
                        include=s.factors, weights=s.weights)


def _report_strategy(name: str) -> None:
    from backend.quant.strategies import get

    s = get(name)
    print(f"\n===== 策略 {name} =====")
    print(f"  因子: {s.factors}  权重: {s.weights or '等权'}  TopN: {s.top_n}")
    print(f"  {'horizon':>8} {'IC':>9} {'ICIR':>8} {'IC>0':>6} {'Top年化':>9} {'夏普':>7} {'基准':>9}")
    for h in (5, 10, 20):
        r = backtest_strategy(name, horizon=h)
        print(f"  {h:>8} {r.ic_mean:>+9.4f} {r.ic_ir:>+8.3f} {r.ic_pos_ratio:>5.0%} "
              f"{r.topn_annual:>+9.1%} {r.topn_sharpe:>+7.2f} {r.bench_annual:>+9.1%}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="向量化回测")
    ap.add_argument("--strategy", help="只回测某个注册策略 (见 backend/quant/strategies)")
    ap.add_argument("--list", action="store_true", help="列出已注册策略")
    args = ap.parse_args()

    if args.list:
        from backend.quant.strategies import all_strategies
        for s in all_strategies():
            print(f"  {s.name:<16} {s.description}")
        raise SystemExit(0)

    if args.strategy:
        _report_strategy(args.strategy)
        raise SystemExit(0)

    close, _, _ = _load_wide()
    print(f"数据跨度: {close.index[0]} .. {close.index[-1]}  ({len(close)} 个交易日, {close.shape[1]} 只)")

    print("\n===== 单因子 Rank-IC (持有 10 日, 全样本) =====")
    print(f"  {'因子':<12} {'IC均值':>9} {'ICIR':>8} {'IC>0':>7} {'截面数':>6}")
    bd = factor_ic_breakdown(horizon=10)
    for name, m in bd.items():
        flag = "  ✓有效" if abs(m["ic"]) >= 0.02 and abs(m["icir"]) >= 0.3 else ""
        print(f"  {name:<12} {m['ic']:>+9.4f} {m['icir']:>+8.3f} {m['pos']:>6.0%} {m['n']:>6}{flag}")

    print("\n===== 组合对比 (持有 10 日) =====")
    for h in (5, 10, 20):
        r = run_backtest(horizon=h, top_n=20)
        groups = " ".join(f"{g:+.1%}" for g in r.group_returns)
        print(f"  [h={h:>2}] IC={r.ic_mean:+.4f} ICIR={r.ic_ir:+.3f} "
              f"分组(低→高)=[{groups}] Top20年化={r.topn_annual:+.1%} "
              f"夏普={r.topn_sharpe:+.2f} vs基准={r.bench_annual:+.1%}")
