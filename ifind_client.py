#!/usr/bin/env python3
"""
iFinD MCP HTTP 客户端
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api-mcp.51ifind.com:8643/ds-mcp-servers"
DEFAULT_SERVERS = {
    "stock": f"{BASE_URL}/hexin-ifind-ds-stock-mcp",
    "fund": f"{BASE_URL}/hexin-ifind-ds-fund-mcp",
    "edb": f"{BASE_URL}/hexin-ifind-ds-edb-mcp",
    "news": f"{BASE_URL}/hexin-ifind-ds-news-mcp",
}


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class IFindMCPClient:
    def __init__(self) -> None:
        self.auth_token = self._load_auth_token()
        self.verify_ssl = _to_bool(os.environ.get("IFIND_VERIFY_SSL"), default=False)
        self.timeout = int(os.environ.get("IFIND_TIMEOUT_SECONDS", "30"))
        self.sessions: dict[str, str] = {}
        self.req_ids: dict[str, int] = {}

    @staticmethod
    def _load_auth_token() -> str:
        env_token = os.environ.get("IFIND_AUTH_TOKEN", "").strip()
        if env_token:
            return env_token

        config_path = Path(
            os.environ.get(
                "IFIND_MCP_CONFIG",
                str(Path(__file__).parent / "ifind_mcp_config.json"),
            )
        )
        if config_path.exists():
            try:
                content = json.loads(config_path.read_text(encoding="utf-8"))
                file_token = str(content.get("auth_token", "")).strip()
                if file_token:
                    return file_token
            except Exception:
                pass

        raise RuntimeError(
            "未找到 iFinD 鉴权。请在 .env 里设置 IFIND_AUTH_TOKEN，"
            "或创建 ifind_mcp_config.json 并填写 auth_token。"
        )

    def _next_id(self, server_type: str) -> int:
        self.req_ids[server_type] = self.req_ids.get(server_type, 0) + 1
        return self.req_ids[server_type]

    def _headers(self, server_type: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": self.auth_token,
        }
        if server_type in self.sessions:
            headers["Mcp-Session-Id"] = self.sessions[server_type]
        return headers

    def _post(self, server_type: str, payload: dict[str, Any], timeout: int | None = None):
        if server_type not in DEFAULT_SERVERS:
            raise ValueError(f"unknown server_type: {server_type}")
        return requests.post(
            DEFAULT_SERVERS[server_type],
            json=payload,
            headers=self._headers(server_type),
            timeout=timeout or self.timeout,
            verify=self.verify_ssl,
        )

    def _initialize(self, server_type: str) -> None:
        if server_type in self.sessions:
            return

        init_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(server_type),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "trade-review", "version": "1.0.0"},
            },
        }
        resp = self._post(server_type, init_payload, timeout=20)
        resp.raise_for_status()

        session_id = resp.headers.get("Mcp-Session-Id")
        if not session_id:
            raise RuntimeError("initialize 成功但未返回 Mcp-Session-Id")
        self.sessions[server_type] = session_id

        notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._post(server_type, notify, timeout=10)

    def call(self, server_type: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._initialize(server_type)
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(server_type),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = self._post(server_type, payload)

        raw_text = resp.text.strip()
        body: Any = None
        if raw_text:
            try:
                body = resp.json()
            except Exception:
                body = raw_text

        if isinstance(body, dict) and body.get("error"):
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": body.get("error"),
                "raw": body,
            }

        resp.raise_for_status()
        result = body.get("result") if isinstance(body, dict) else body
        return {"ok": True, "status_code": resp.status_code, "result": result, "raw": body}

    def list_tools(self, server_type: str) -> dict[str, Any]:
        self._initialize(server_type)
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(server_type),
            "method": "tools/list",
            "params": {},
        }
        resp = self._post(server_type, payload)
        body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": body.get("error"),
                "raw": body,
            }
        resp.raise_for_status()
        return {"ok": True, "status_code": resp.status_code, "result": body.get("result"), "raw": body}

    @staticmethod
    def extract_text(data: Any) -> str:
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, (int, float, bool)):
            return str(data)
        if isinstance(data, list):
            return "\n".join([IFindMCPClient.extract_text(x) for x in data if x is not None]).strip()
        if isinstance(data, dict):
            if "text" in data and isinstance(data["text"], str):
                return data["text"]
            if "content" in data:
                return IFindMCPClient.extract_text(data["content"])
            return json.dumps(data, ensure_ascii=False, indent=2)
        return str(data)

    def query_stock_info(self, query: str, tool_name: str = "get_stock_info") -> dict[str, Any]:
        result = self.call("stock", tool_name, {"query": query})
        if not result.get("ok"):
            return result
        result["text"] = self.extract_text(result.get("result"))
        return result

    def query_stock_trend(self, code: str, trade_date: str | None = None) -> dict[str, Any]:
        trade_date = trade_date or str(date.today())
        query = f"{code}在{trade_date}的日内走势、开高低收、涨跌幅"
        result = self.query_stock_info(query=query, tool_name="get_stock_info")
        result["query"] = query
        return result
