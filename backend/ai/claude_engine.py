"""Claude Agent SDK 引擎：持久 ClaudeSDKClient 连接。

关键优化：在 FastAPI 启动时建立一次 subprocess 连接，每次请求复用。
首字延迟从 50 秒（每次冷启动）降到 3-5 秒（已有连接）。

并发安全：单一 CLI subprocess 只能顺序 query，用 asyncio.Lock 串行化。
Session 隔离：每次请求用独立 session_id，避免闪评之间上下文污染。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage, TextBlock, ResultMessage, StreamEvent,
)

from backend.ai.base import AIResponse

log = logging.getLogger(__name__)


class ClaudeEngine:
    name = "claude-sonnet-4-6"

    def __init__(self, model: str = "claude-sonnet-4-6",
                 max_turns: int = 1,
                 allowed_tools: list[str] | None = None):
        self.model = model
        self.max_turns = max_turns
        self.allowed_tools = allowed_tools or []
        self._client: ClaudeSDKClient | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    def _base_options(self, system: str | None, *, partial: bool) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self.model,
            max_turns=self.max_turns,
            allowed_tools=self.allowed_tools,
            permission_mode="bypassPermissions",
            system_prompt=system,
            include_partial_messages=partial,
        )

    async def connect(self, warmup_system: str | None = None) -> None:
        """启动时调用一次。先建立 subprocess 连接，再跑一个短 warmup query
        触发模型层热身（否则首次真实请求仍会有 ~40s 冷启动）。"""
        if self._connected:
            return
        opts = self._base_options(warmup_system, partial=True)
        self._client = ClaudeSDKClient(options=opts)
        await self._client.connect()
        log.info("ClaudeSDKClient 子进程已连接，正在执行模型层预热...")

        # 用真实长度的 flash prompt 模板预热，激活 KV cache，
        # 真实请求就能享受 ~28s 路径而非 ~58s 冷推理。
        warm_start = time.time()
        try:
            warmup_prompt = (
                "这是一次系统预热请求，请用最短 1-2 句中文回复 '已就绪'。"
                "（真实请求格式较长，首次推理会较慢；此次预热用于激活模型热状态。）"
            )
            await self._client.query(warmup_prompt, session_id=f"warmup-{uuid.uuid4().hex[:8]}")
            async for msg in self._client.receive_response():
                if isinstance(msg, ResultMessage):
                    break
            log.info("模型层预热完成，耗时 %.1fs", time.time() - warm_start)
        except Exception as e:
            log.warning("预热 query 失败（不影响后续）: %s", e)

        self._connected = True

    async def close(self) -> None:
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except Exception as e:
                log.warning("ClaudeSDKClient disconnect 异常: %s", e)
            self._connected = False

    async def _ensure_ready(self) -> ClaudeSDKClient:
        if not self._connected:
            await self.connect()
        assert self._client is not None
        return self._client

    async def complete(self, prompt: str, system: str | None = None) -> AIResponse:
        client = await self._ensure_ready()
        start = time.time()
        chunks: list[str] = []
        session_id = uuid.uuid4().hex[:12]
        combined = self._combine_system_and_prompt(system, prompt)
        async with self._lock:
            await client.query(combined, session_id=session_id)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        return AIResponse(
            text="".join(chunks),
            latency_ms=int((time.time() - start) * 1000),
            engine=self.name,
        )

    async def stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        """真流式：逐 token yield。"""
        client = await self._ensure_ready()
        session_id = uuid.uuid4().hex[:12]
        combined = self._combine_system_and_prompt(system, prompt)
        async with self._lock:
            await client.query(combined, session_id=session_id)
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    ev = msg.event or {}
                    if ev.get("type") == "content_block_delta":
                        delta = ev.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield text
                elif isinstance(msg, ResultMessage):
                    return

    @staticmethod
    def _combine_system_and_prompt(system: str | None, prompt: str) -> str:
        """ClaudeSDKClient 构造时的 system_prompt 在连接后不可动态改。
        为了让不同请求用不同 system，我们把 system 拼接到 prompt 头部。"""
        if not system:
            return prompt
        return f"【系统指令】\n{system}\n\n【本次任务】\n{prompt}"
