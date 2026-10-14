"""Re-exports de airi.testing para compatibilidad con tests antiguos.

Nuevo código: importa directamente de ``airi.testing``.
"""

from __future__ import annotations

from airi.testing import (
    FakeGif,
    FakeLLM,
    FakeNotifier,
    FakeSearch,
    FakeUser,
    InMemoryRepository,
    llm_json,
    make_state,
)

__all__ = [
    "FakeGif",
    "FakeLLM",
    "FakeNotifier",
    "FakeSearch",
    "FakeUser",
    "InMemoryRepository",
    "llm_json",
    "make_state",
]
