"""DeepSeek / OpenAI-compatible chat completions engine."""
from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

import httpx

from backend.ai.base import AIResponse


class DeepSeekEngine:
    """Adapter for DeepSeek's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.name = f"deepseek:{self.model}"
        self.timeout = float(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "120"))

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY。请在 .env 中填写后重启。")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _messages(self, prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _payload(self, prompt: str, system: str | None, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(prompt, system),
            "stream": stream,
        }
        temperature = os.environ.get("DEEPSEEK_TEMPERATURE")
        if temperature:
            payload["temperature"] = float(temperature)
        max_tokens = os.environ.get("DEEPSEEK_MAX_TOKENS")
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        return payload

    async def complete(self, prompt: str, system: str | None = None) -> AIResponse:
        start = time.time()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._endpoint,
                headers=self._headers(),
                json=self._payload(prompt, system, stream=False),
            )
            self._raise_for_status(resp)
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        return AIResponse(
            text=text,
            latency_ms=int((time.time() - start) * 1000),
            engine=self.name,
        )

    async def stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self._endpoint,
                headers=self._headers(),
                json=self._payload(prompt, system, stream=True),
            ) as resp:
                self._raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(f"DeepSeek API 请求失败: HTTP {exc.response.status_code} {detail}") from exc
