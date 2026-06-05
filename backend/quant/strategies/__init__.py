"""可插拔策略注册表 —— 写你自己的选股策略。

一个策略 = 选用哪些**已回测验证**的因子 + 各自权重 + 取前几名。

要加自己的策略,有两种方式:
  1. 在本目录新建一个 .py 文件,在里面 `register(Strategy(...))`。
     文件会在导入 strategies 包时被自动发现并注册。模板见 custom_example.py。
  2. 直接在代码里 `from backend.quant.strategies import register, Strategy`
     然后 register 一个 Strategy 实例。

注册后即可:
  - 跑选股:    .venv/bin/python scripts/quant_run_today.py --strategy <name>
  - 跑回测:    .venv/bin/python -m backend.quant.backtest --strategy <name>
  - HTTP:      GET /api/quant/strategies   POST /api/quant/run {"strategy": "<name>"}

可用因子(全部已统一成"值越大越好",详见 factors.py / backtest.py):
  Rev_5  LowVol_60  BP  SmallSize  EP
注:动量类 Mom_20 / Mom_60 / AmpUp_5_60 经 3 年回测确认在 A 股主板是负 IC,
   已从可入池因子中剔除,这里不开放。
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field

from backend.quant.factors import ALL_FACTORS, FACTOR_NAMES


@dataclass(frozen=True)
class Strategy:
    """一个选股策略的声明式定义。

    name        唯一名字(信号表 / API / CLI 都用它)
    description 一句话说明,会出现在 /api/quant/strategies 里
    factors     参与合成的因子,必须是 ALL_FACTORS 的子集
    weights     各因子权重(未列出的按 1.0);None = 等权
    top_n       默认取前几名
    """
    name: str
    description: str
    factors: list[str] = field(default_factory=lambda: list(FACTOR_NAMES))
    weights: dict[str, float] | None = None
    top_n: int = 20

    def __post_init__(self) -> None:
        bad = [f for f in self.factors if f not in ALL_FACTORS]
        if bad:
            raise ValueError(f"未知因子 {bad};可用因子: {ALL_FACTORS}")
        if not self.factors:
            raise ValueError("factors 不能为空")
        if self.weights:
            stray = [f for f in self.weights if f not in self.factors]
            if stray:
                raise ValueError(f"weights 含不在 factors 里的因子 {stray}")


_REGISTRY: dict[str, Strategy] = {}


def register(strategy: Strategy, *, overwrite: bool = False) -> Strategy:
    """登记一个策略。重名默认报错,overwrite=True 可覆盖。"""
    if strategy.name in _REGISTRY and not overwrite:
        raise ValueError(f"策略 {strategy.name!r} 已存在(传 overwrite=True 可覆盖)")
    _REGISTRY[strategy.name] = strategy
    return strategy


def get(name: str) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(f"未知策略 {name!r};已注册: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def all_strategies() -> list[Strategy]:
    return list(_REGISTRY.values())


# ─── 内置策略 ─────────────────────────────────────────────────────────
# multifactor_v1 必须与历史行为一致:等权 FACTOR_NAMES。
register(Strategy(
    name="multifactor_v1",
    description="等权 4 因子(短期反转 + 低波动 + 价值BP + 小市值),3 年回测验证为正 Rank-IC。",
    factors=list(FACTOR_NAMES),
))
register(Strategy(
    name="value_tilt",
    description="价值/防御倾斜:BP + EP + 低波动,价值因子加权更高。",
    factors=["BP", "EP", "LowVol_60"],
    weights={"BP": 1.5, "EP": 1.0, "LowVol_60": 1.0},
))
register(Strategy(
    name="low_vol",
    description="纯低波动单因子,作为基准对照。",
    factors=["LowVol_60"],
))
register(Strategy(
    name="contrarian",
    description="短期反转 + 小市值:超跌小盘的反弹篮子。",
    factors=["Rev_5", "SmallSize"],
))


def _autodiscover() -> None:
    """导入本包内其余模块,让用户丢进来的策略文件在 import 时自注册。"""
    import backend.quant.strategies as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{mod.name}")


_autodiscover()
