"""Instrumentación de eventos que NO pasan por `run_turn`.

Los turnos de conversación ya generan su `TurnEvent` dentro de
`ConversationService`. Esta capa cubre los flujos que ocurren fuera de él
—comandos (`!regalo`, `!afinidad`, ...), selección de escena y acciones de
cita— reutilizando el mismo `TurnEvent` y el mismo `TraceStore`, de modo que
todos los eventos queden en el mismo sitio para `!debug` y `airi.trace`.

Todo es best-effort: capturar o guardar una traza nunca debe romper el flujo
del bot (un fallo se registra y se continúa).
"""

from __future__ import annotations

import functools
import logging
import traceback
import uuid
from contextlib import asynccontextmanager

from airi.domain.affinity import entry_points
from airi.logging_setup import (
    reset_correlation_id,
    set_correlation_id,
)
from airi.observability.trace import TurnEvent

log = logging.getLogger(__name__)


def _snapshot(state, ev, uid):
    """Vuelca el estado ANTES de mutar (replay fiel); best-effort."""
    try:
        if uid is not None:
            snap = dict(state.affinity.get(str(uid), {}))
            ev.state_snapshot_affinity = snap
            ev.state_snapshot_memories = list(state.memories.get(str(uid), []))
            ev.affinity_before = entry_points(snap)
        ev.state_snapshot_world = dict(state.world)
        ev.state_snapshot_diary = list(state.diary[-20:])
    except Exception:
        log.exception("No se pudo capturar el snapshot del evento")


@asynccontextmanager
async def turn_event(
    state,
    *,
    kind,
    user=None,
    channel_id="",
    raw_input="",
    correlation_id=None,
):
    """Registra un `TurnEvent` alrededor de un bloque `async with`.

    Uso::

        async with turn_event(state, kind="gift", user=msg.author) as ev:
            ...  # ev se puede enriquecer aquí
        # al salir: finish(), guardado best-effort y reset del correlation_id
    """
    cid = correlation_id or uuid.uuid4().hex[:12]
    token = set_correlation_id(cid)
    uid = getattr(user, "id", None)
    ev = TurnEvent(
        kind=kind,
        correlation_id=cid,
        user_id=str(uid) if uid is not None else "",
        user_name=getattr(user, "display_name", "") if user is not None else "",
        channel_id=str(channel_id),
        raw_input=raw_input or "",
    )
    _snapshot(state, ev, uid)
    try:
        yield ev
    except Exception as exc:
        ev.errors.append({
            "type": type(exc).__name__,
            "msg": str(exc),
            "tb": traceback.format_exc(),
        })
        ev.error = str(exc)
        raise
    finally:
        ev.finish()
        traces = getattr(state, "traces", None)
        if traces is not None:
            try:
                await traces.save(ev)
            except Exception:
                log.exception("No se pudo guardar el evento %s", cid)
        reset_correlation_id(token)


def _enrich_affinity(state, ev):
    """Completa la afinidad resultante tras ejecutar el handler."""
    if not ev.user_id:
        return
    try:
        after = state.entry_points(ev.user_id)
    except Exception:
        return
    ev.affinity_after = after
    ev.affinity_applied = after - ev.affinity_before


def traced(kind="command"):
    """Decora un handler `async def handle(ctx, message)` como `TurnEvent`.

    No cambia la firma ni el valor de retorno. Si el handler lanza, el error
    queda anotado en el evento y se re-lanza (mismo comportamiento que sin
    instrumentar).
    """

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(ctx, message):
            state = getattr(ctx, "state", None)
            if state is None:
                return await fn(ctx, message)
            channel = getattr(message, "channel", None)
            async with turn_event(
                state,
                kind=kind,
                user=getattr(message, "author", None),
                channel_id=getattr(channel, "id", ""),
                raw_input=getattr(message, "content", ""),
            ) as ev:
                result = await fn(ctx, message)
                _enrich_affinity(state, ev)
            return result

        return wrapper

    return deco
