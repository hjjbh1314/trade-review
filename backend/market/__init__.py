"""市场数据子包。导入时再保险一次：注入国内域名 NO_PROXY。"""
from __future__ import annotations

# 触发 backend.__init__ 中的 _setup_no_proxy（幂等）
from backend import _BYPASS_DOMAINS  # noqa: F401
