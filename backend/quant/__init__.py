"""量化选股 / 模拟盘子系统。

模块切分：
  universe.py     主板股票池过滤
  data_loader.py  akshare → 本地 daily_quotes 表
  factors.py      因子库 + 行业 z-score 打分
  signals.py      策略组合：因子加总 → Top N 候选
  strategies/     可插拔策略注册表（内置 + 用户自定义,import 时自动发现）
  backtest.py     向量化回测：单因子 IC / 分组 / Top-N 组合 / walk-forward
  paper_trader.py 模拟盘下单写 trades 表
  evaluator.py    策略归因（按 source 标签聚合）
"""
