"""Codex 引擎 stub。暂未接入，待 Claude 触发限额时再实现。

两种实现方案备选：
1. subprocess 调 `codex -p "prompt"` CLI
2. 通过 OpenAI SDK + ChatGPT OAuth token
"""
from __future__ import annotations

from typing import AsyncIterator

from backend.ai.base import AIResponse


class CodexEngine:
    name = "codex"

    async def complete(self, prompt: str, system: str | None = None) -> AIResponse:
        raise NotImplementedError("Codex 引擎待实现。当前请使用 TR_AI_ENGINE=claude")

    async def stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        raise NotImplementedError("Codex 引擎待实现。")
        yield  # pragma: no cover
