"""Estado compartido de la aplicación (inyectable, sin globales)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from airi.domain.affinity import (
    AFFINITY_DELTA_MAX,
    apply_affinity_delta,
    default_entry,
)
from airi.domain.affinity import (
    entry_points as _entry_points,
)
from airi.domain.memories import user_memories as _user_memories
from airi.observability.trace_store import TraceStore


def _noop(*args, **kwargs):
    return None


def _noop_bool(*args, **kwargs) -> bool:
    return False


def _default_trace_store() -> TraceStore:
    """TraceStore en memoria (sin disco) para no romper tests/existentes."""
    return TraceStore(None)


@dataclass
class AppState:
    """Agrupa todos los estados mutables + callbacks de persistencia.

    Los callbacks se pasan como callables para que la capa externa (bot.py)
    pueda resolverlos en tiempo de llamada (p. ej. tras monkeypatch en tests).
    """

    affinity: dict = field(default_factory=dict)
    world: dict = field(default_factory=dict)
    dates: dict = field(default_factory=dict)
    memories: dict = field(default_factory=dict)
    diary: list = field(default_factory=list)
    users: dict = field(default_factory=dict)
    histories: dict = field(default_factory=dict)

    save_affinity: Callable[[], None] = _noop
    save_world: Callable[[], None] = _noop
    save_dates: Callable[[], None] = _noop
    save_memories: Callable[[], None] = _noop
    save_diary: Callable[[], None] = _noop
    save_users: Callable[[], None] = _noop
    log_diary_event: Callable[[str, Any, str], bool] = _noop_bool
    # Hook opcional para aplicar afinidad vía la fachada externa (bot.py),
    # de modo que se mantengan sus logs y sea monkeypatchable en tests.
    apply_affinity_fn: Callable[..., int] | None = None
    # Almacén de eventos de turno (ring buffer + disco opcional).
    traces: TraceStore = field(default_factory=_default_trace_store)

    # ------------------------------------------------------------------
    # Afinidad
    # ------------------------------------------------------------------

    def affinity_entry(self, user_id) -> dict:
        key = str(user_id)
        entry = self.affinity.get(key)
        if not isinstance(entry, dict):
            entry = default_entry()
            self.affinity[key] = entry
        else:
            for fname, default in default_entry().items():
                entry.setdefault(fname, default)
        return entry

    def entry_points(self, user_id) -> int:
        return _entry_points(self.affinity.get(str(user_id)))

    def apply_affinity(self, user_id, delta, *, now, delta_max=AFFINITY_DELTA_MAX) -> int:
        """Aplica el cambio juzgado por Airi y persiste. Devuelve el aplicado."""
        if self.apply_affinity_fn is not None:
            applied = self.apply_affinity_fn(user_id, delta, now=now, delta_max=delta_max)
            return int(applied or 0)
        entry = self.affinity_entry(user_id)
        applied = apply_affinity_delta(entry, delta, now, delta_max=delta_max)
        self.save_affinity()
        return applied

    # ------------------------------------------------------------------
    # Memorias
    # ------------------------------------------------------------------

    def user_memories(self, user_id) -> list:
        return _user_memories(self.memories, user_id)

    def display_name(self, user_id) -> str:
        entry = self.users.get(str(user_id))
        if isinstance(entry, dict) and entry.get("name"):
            return str(entry["name"])
        return "alguien"
