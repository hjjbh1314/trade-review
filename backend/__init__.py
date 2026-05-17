"""Trade Review 后端包。

包初始化阶段做一件事：把国内数据源加入 NO_PROXY，避免 Mac 上的
科学上网代理（ClashX / Surge / V2Ray 等）把这些直连流量也截走。
"""
from __future__ import annotations

import os

# akshare / 上证指数等用到的国内域名（出问题就往这里加）
_BYPASS_DOMAINS = [
    "eastmoney.com",        # akshare 主数据源（push2his / push2 等子域）
    "dfcfw.com",            # 东方财富 CDN
    "sina.com.cn",          # 新浪财经
    "sinajs.cn",            # 新浪行情接口
    "xueqiu.com",           # 雪球
    "163.com",              # 网易财经
    "10jqka.com.cn",        # 同花顺
    "qq.com",               # 腾讯财经
    "iwencai.com",          # 同花顺问财
    "akshare.akfamily.xyz", # akshare 升级检查
    "127.0.0.1",
    "localhost",
]


def _setup_no_proxy() -> None:
    existing = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    changed = False
    for d in _BYPASS_DOMAINS:
        if d not in parts:
            parts.append(d)
            changed = True
    value = ",".join(parts)
    # macOS / Linux 大小写都设置，requests 两个都查
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value
    if changed:
        # 简单 print，因为 logging 还没配
        print(f"[proxy_bypass] NO_PROXY 已注入国内域名直连：{','.join(_BYPASS_DOMAINS)}")


_setup_no_proxy()
