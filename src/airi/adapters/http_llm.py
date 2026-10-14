"""Cliente LLM contra llama.cpp (API compatible con OpenAI) vía aiohttp."""

from __future__ import annotations

import logging

import aiohttp

from airi.ports.llm import LLMMeta

log = logging.getLogger(__name__)


class HttpLlmClient:
    """Implementa `airi.ports.llm.LLMClient` sobre un servidor llama.cpp."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        *,
        timeout: int = 300,
        max_output_tokens: int = 8000,
        temperature: float = 0.6,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

    async def post(self, payload: dict) -> dict:
        """POST crudo a /v1/chat/completions (devuelve la respuesta completa)."""
        async with self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def chat(self, messages, *, schema=None, max_tokens=None, temperature=None):
        content, _meta = await self.chat_with_meta(
            messages, schema=schema, max_tokens=max_tokens, temperature=temperature
        )
        return content

    async def chat_with_meta(self, messages, *, schema=None, max_tokens=None,
                             temperature=None):
        payload = {
            "model": "Qwen3.6-35B-A3B-MTP-UD-IQ3_S",
            "messages": messages,
            "max_tokens": max_tokens or self.max_output_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}
        data = await self.post(payload)
        choices = data.get("choices") or []
        if not choices:
            log.error("llama-server no devolvió choices")
            return "", LLMMeta()
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        meta = LLMMeta(
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )
        return text, meta
