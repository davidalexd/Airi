"""Puerto: notificador de mensajes (abstrae Discord)."""

from __future__ import annotations

from typing import Any, Protocol


class Notifier(Protocol):
    """Canal de mensajería."""

    async def send(self, content: str) -> Any:
        ...
