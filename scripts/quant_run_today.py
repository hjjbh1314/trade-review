"""每日量化运行入口。

流程:
  1. 增量更新主板行情到本地
  2. 跑 multifactor_v1 策略,生成 Top 20 买入信号
  3. (可选) 用 --paper 把信号写入 trades 表做模拟盘

cron 用法 (示例,收盘后):
  30 15 * * 1-5  cd /Users/haiwenbao/Documents/trade_review && \\
                 .venv/bin/python scripts/quant_run_today.py --paper
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.quant.data_loader import load_mainboard
from backend.quant.paper_trader import open_positions_from_signals
from backend.quant.signals import run_strategy


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="子集主板股票数 (调试用)")
    p.add_argument("--skip-load", action="store_true", help="不拉新数据,只用本地缓存")
    p.add_argument("--top-n", type=int, default=20)
    p.add_argument("--paper", action="store_true", help="把信号写入 trades 表 (模拟盘)")
    p.add_argument("--strategy", default="multifactor_v1")
    args = p.parse_args()

    if not args.skip_load:
        print("=== 1/3 增量加载主板行情 ===")
        results = load_mainboard(limit=args.limit, max_workers=2)
        ok = sum(1 for r in results if r.error is None)
        inserted = sum(r.rows_inserted for r in results)
        print(f"   完成 {ok}/{len(results)}, 插入 {inserted} 行\n")

    print("=== 2/3 计算因子 + 选股 ===")
    signals = run_strategy(strategy=args.strategy, top_n=args.top_n)
    print(f"   策略 {args.strategy} 生成 {len(signals)} 条买入信号\n")

    print("=== Top N ===")
    for i, s in enumerate(signals, 1):
        name = s.reason.get("name", "")
        fz = s.reason["factor_z"]
        zs = "  ".join(f"{k}={v:+.2f}" for k, v in fz.items())
        print(f"  #{i:>2}  {s.symbol} {name:<8}  composite={s.score:+.3f}  {zs}")

    if args.paper:
        print("\n=== 3/3 模拟下单 ===")
        ids = open_positions_from_signals(signals)
        print(f"   写入 trades 表 {len(ids)} 条 (虚拟单, source = quant)")
    else:
        print("\n=== 3/3 --paper 未启用,跳过模拟下单 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
