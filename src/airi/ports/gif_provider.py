"""Puerto: proveedor de GIFs."""

from __future__ import annotations

from typing import Protocol


class GifProvider(Protocol):
    """Proveedor de GIFs por emoción."""

    async def fetch(self, kind: str) -> bytes | None:
        ...
