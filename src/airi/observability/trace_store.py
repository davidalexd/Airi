"""Almacén de eventos de turno: ring buffer en memoria + disco best-effort.

`TraceStore` mantiene SIEMPRE un `deque(maxlen=keep_last)` en memoria y, si
`base_dir` está definido, persiste cada evento como
`<base_dir>/<YYYY-MM-DD>/<correlation_id>.json` de forma atómica y sin bloquear
el event loop. Ninguna operación lanza excepciones: un fallo de disco se
registra y el turno continúa.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from airi.observability.events import TurnEvent

log = logging.getLogger(__name__)


class TraceStore:
    """Ring buffer de eventos con persistencia opcional a disco."""

    def __init__(self, base_dir: Path | str | None, keep_last: int = 500):
        self.base_dir = str(base_dir) if base_dir else None
        self.keep_last = keep_last
        self._ring: deque[TurnEvent] = deque(maxlen=keep_last)

    # ------------------------------------------------------------------
    # Ring buffer (memoria, síncrono)
    # ------------------------------------------------------------------

    def last(self, n: int = 1) -> list[TurnEvent]:
        """Los últimos `n` eventos (del más reciente al más antiguo)."""
        items = list(self._ring)
        items.reverse()
        return items[:n]

    def by_correlation_id(self, cid: str) -> TurnEvent | None:
        """Evento con ese correlation_id, o None."""
        for ev in reversed(self._ring):
            if ev.correlation_id == cid:
                return ev
        return None

    def all(self) -> list[TurnEvent]:
        """Todos los eventos del ring, del más antiguo al más reciente."""
        return list(self._ring)

    def clear(self) -> None:
        """Vacía el ring buffer."""
        self._ring.clear()

    def __len__(self) -> int:
        return len(self._ring)

    # ------------------------------------------------------------------
    # Persistencia (disco, asíncrona y best-effort)
    # ------------------------------------------------------------------

    async def save(self, ev: TurnEvent) -> str | None:
        """Guarda el evento en el ring y, si aplica, en disco.

        Devuelve la ruta del fichero escrito, o None si no hay `base_dir`
        o falló la escritura (nunca lanza).
        """
        self._ring.append(ev)
        if self.base_dir is None:
            return None
        return await asyncio.to_thread(self._write, ev)

    async def update(self, ev: TurnEvent) -> str | None:
        """Reemplaza en el ring el evento con ese correlation_id y reescribe.

        Pensado para completar campos calculados después del turno (p. ej.
        `date_event`). Si el evento no está en el ring, se añade. Nunca lanza.
        """
        self._replace_in_ring(ev)
        if self.base_dir is None:
            return None
        return await asyncio.to_thread(self._write, ev)

    def _replace_in_ring(self, ev: TurnEvent) -> None:
        for i in range(len(self._ring) - 1, -1, -1):
            if self._ring[i] is ev or self._ring[i].correlation_id == ev.correlation_id:
                self._ring[i] = ev
                return
        self._ring.append(ev)

    def _write(self, ev: TurnEvent) -> str | None:
        """Escritura atómica en un hilo (tmp + os.replace)."""
        path = self._path_for(ev.correlation_id)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(ev.to_json())
            os.replace(tmp_path, path)
            return path
        except OSError:
            log.exception("No se pudo guardar el evento %s", ev.correlation_id)
            return None

    def _path_for(self, correlation_id: str, *, now=None) -> str:
        """Ruta `<base_dir>/<YYYY-MM-DD>/<cid>.json`."""
        now = now or datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        safe_cid = (
            "".join(c for c in correlation_id if c.isalnum() or c in "-_") or "x"
        )
        return os.path.join(self.base_dir, day, f"{safe_cid}.json")


def load_events_from_dir(base_dir: Path | str) -> list[TurnEvent]:
    """Carga todos los eventos JSON de un directorio de trazas (para la CLI).

    Devuelve los eventos ordenados por `started_at`. Ignora ficheros ilegibles.
    """
    events: list[TurnEvent] = []
    if not base_dir or not os.path.isdir(str(base_dir)):
        return events
    for dirpath, _dirnames, filenames in os.walk(str(base_dir)):
        for name in sorted(filenames):
            if not name.endswith(".json"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    events.append(TurnEvent.from_dict(json.load(fh)))
            except (OSError, json.JSONDecodeError, TypeError):
                log.warning("Traza ilegible ignorada: %s", path)
    events.sort(key=lambda e: e.started_at)
    return events
