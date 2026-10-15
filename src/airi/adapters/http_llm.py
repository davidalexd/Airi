"""Cliente LLM contra llama.cpp (API compatible con OpenAI) vía aiohttp."""

from __future__ import annotations

import logging
import os

import aiohttp

from airi.domain.constants import env_int
from airi.ports.llm import LLMMeta

log = logging.getLogger(__name__)

DEFAULT_MAX_OUTPUT_TOKENS = 8000


class HttpLlmClient:
    """Implementa `airi.ports.llm.LLMClient` sobre un servidor llama.cpp."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        *,
        model: str | None = None,
        timeout: int | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.model = model or os.environ.get(
            "LLM_MODEL", "Qwen3.6-35B-A3B-MTP-UD-IQ3_S"
        )
        if timeout is not None:
            self.timeout = timeout
        else:
            try:
                self.timeout = int(os.environ.get("LLM_TIMEOUT", "300"))
            except (ValueError, TypeError):
                log.warning("LLM_TIMEOUT tiene valor inválido, usando 300")
                self.timeout = 300
        if max_output_tokens is not None:
            self.max_output_tokens = max_output_tokens
        else:
            self.max_output_tokens = env_int("LLM_MAX_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)
        if temperature is not None:
            self.temperature = temperature
        else:
            try:
                self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.6"))
            except (ValueError, TypeError):
                log.warning("LLM_TEMPERATURE tiene valor inválido, usando 0.6")
                self.temperature = 0.6

    async def post(self, payload: dict) -> dict:
        """POST crudo a /v1/chat/completions (devuelve la respuesta completa).

        El servidor es multi-modelo y exige `model`; se inyecta sin mutar el
        dict del llamador (si ya trae `model`, se respeta el suyo).
        """
        payload = {"model": self.model, **payload}
        async with self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def chat(self, messages, *, schema=None, max_tokens=None, temperature=None,
                   disable_thinking: bool = False, strict_schema: bool = False):
        content, _meta = await self.chat_with_meta(
            messages, schema=schema, max_tokens=max_tokens, temperature=temperature,
            disable_thinking=disable_thinking, strict_schema=strict_schema,
        )
        return content

    async def chat_with_meta(self, messages, *, schema=None, max_tokens=None,
                             temperature=None, disable_thinking: bool = False,
                             strict_schema: bool = False):
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_output_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        if schema is not None:
            if strict_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "strict": True,
                        "schema": schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        if disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
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
