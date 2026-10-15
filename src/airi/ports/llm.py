"""Puerto: cliente de LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMMeta:
    """Metadatos de una respuesta del modelo (además del texto)."""

    finish_reason: str | None = None
    usage: dict | None = field(default_factory=dict)


class LLMClient(Protocol):
    """Cliente de LLM local (llama.cpp u otro compatible con OpenAI API)."""

    async def chat(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        disable_thinking: bool = False,
        strict_schema: bool = False,
    ) -> str:
        """Devuelve el texto de la respuesta del modelo.

        `disable_thinking` desactiva el razonamiento del modelo si lo soporta.
        """
        ...

    async def chat_with_meta(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        disable_thinking: bool = False,
        strict_schema: bool = False,
    ) -> tuple[str, LLMMeta]:
        """Igual que `chat` pero además devuelve los metadatos del turno."""
        ...
