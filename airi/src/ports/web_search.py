"""Puerto: búsqueda web."""

from __future__ import annotations

from typing import Protocol


class WebSearchClient(Protocol):
    """Búsqueda web que devuelve un contexto formateado o None."""

    async def search(self, query: str) -> str | None:
        ...
