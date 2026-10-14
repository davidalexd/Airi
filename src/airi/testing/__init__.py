"""Herramientas de testing reutilizables: fakes, repos en memoria, utilidades."""

from __future__ import annotations

from .fake_doubles import FakeGif, FakeNotifier, FakeSearch, FakeUser
from .fake_llm import FakeLLM, llm_json
from .in_memory_repo import InMemoryRepository, make_state

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
