"""AI 引擎选择器。返回进程级单例，保证持久会话被复用。"""
from __future__ import annotations

import os

from backend.ai.base import AIEngine, AIResponse

_instance: AIEngine | None = None


def get_ai_engine() -> AIEngine:
    global _instance
    if _instance is not None:
        return _instance
    name = os.environ.get("TR_AI_ENGINE", "claude").lower()
    if name == "claude":
        from backend.ai.claude_engine import ClaudeEngine
        _instance = ClaudeEngine()
    elif name == "deepseek":
        from backend.ai.deepseek_engine import DeepSeekEngine
        _instance = DeepSeekEngine()
    elif name == "codex":
        from backend.ai.codex_engine import CodexEngine
        _instance = CodexEngine()
    else:
        raise ValueError(f"未知 AI 引擎: {name}。可选: claude, deepseek, codex")
    return _instance


__all__ = ["get_ai_engine", "AIEngine", "AIResponse"]
