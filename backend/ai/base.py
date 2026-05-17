"""AI 引擎协议。Claude / Codex 走同一接口，可热切。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass
class AIResponse:
    text: str                  # 完整文本
    latency_ms: int
    engine: str                # "claude-sonnet-4-6" / "codex"


class AIEngine(Protocol):
    name: str
    async def complete(self, prompt: str, system: str | None = None) -> AIResponse: ...
    async def stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]: ...
