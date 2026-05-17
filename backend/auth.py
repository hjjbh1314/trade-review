"""简单 Token 鉴权。

单用户场景，所有请求需带：
  - HTTP header: X-TR-Token: <token>
  - 或 cookie: tr_token=<token>
  - 或 query: ?token=<token>

Token 从环境变量 TR_ACCESS_TOKEN 读取。未设置则不鉴权（本机开发用）。

静态前端资源（/、/assets/*、/favicon.svg 等）不强制鉴权，
前端页面自己负责引导用户输入 token 后再请求 API。
"""
from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


ACCESS_TOKEN_ENV = "TR_ACCESS_TOKEN"


def _get_token() -> str | None:
    tok = os.environ.get(ACCESS_TOKEN_ENV, "").strip()
    return tok or None


def _extract_request_token(req: Request) -> str | None:
    # 优先 header
    h = req.headers.get("x-tr-token")
    if h:
        return h.strip()
    # 再 cookie
    c = req.cookies.get("tr_token")
    if c:
        return c.strip()
    # 最后 query
    q = req.query_params.get("token")
    if q:
        return q.strip()
    return None


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """只对 /api/* 生效。静态资源不拦，让前端能正常加载。"""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        # /api/health 和 /api/auth-status 开放
        if path in {"/api/health", "/api/auth-status"}:
            return await call_next(request)

        expected = _get_token()
        if not expected:
            # 未配置 token 时默认放行（本机开发）
            return await call_next(request)

        got = _extract_request_token(request)
        if got != expected:
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "未授权：缺少或错误的访问 Token"},
            )
        return await call_next(request)


def token_required_for_client() -> bool:
    """前端可通过 /api/auth-status 查询是否需要 token。"""
    return _get_token() is not None
