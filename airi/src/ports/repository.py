"""Puerto: repositorio de persistencia."""

from __future__ import annotations

from typing import Any, Protocol


class Repository(Protocol):
    """Almacenamiento genérico load/save."""

    def load(self) -> Any:
        ...

    def save(self, data: Any) -> None:
        ...
