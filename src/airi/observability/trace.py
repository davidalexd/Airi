"""Trazas por turno: serialización, sanitizado y guardado best-effort.

Este módulo re-exporta TurnEvent y utilidades desde events.py para
mantener compatibilidad con código externo. También re-exporta la CLI
desde cli.py para que `python -m airi.trace` funcione.
"""

from __future__ import annotations

# Re-exportar la CLI desde cli.py
from airi.observability.cli import main

# Re-exportar todo desde events.py para mantener compatibilidad
from airi.observability.events import (
    MAX_RAW_LLM_CHARS,
    TurnEvent,
    TurnTrace,
    load_turn_event,
    load_turn_trace,
    save_turn_trace,
    trace_path,
)

__all__ = [
    "MAX_RAW_LLM_CHARS",
    "TurnEvent",
    "TurnTrace",
    "trace_path",
    "save_turn_trace",
    "load_turn_trace",
    "load_turn_event",
    "main",
]
