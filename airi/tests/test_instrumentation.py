"""Tests de la instrumentación de eventos fuera de `run_turn`.

Cubre el helper `turn_event`, el decorador `traced` y que el registro de
comandos los aplique (kind="command" / kind="gift").
"""

import asyncio

from airi.discord_bot.commands import (
    affinity as affinity_cmd,
)
from airi.discord_bot.commands import (
    build_registry,
)
from airi.discord_bot.commands import (
    gifts as gifts_cmd,
)
from airi.domain.affinity import default_entry
from airi.observability.instrumentation import traced, turn_event
from airi.observability.logging_setup import get_correlation_id
from airi.services.state import AppState


class FakeUser:
    def __init__(self, uid, name="Ana"):
        self.id = uid
        self.display_name = name


class FakeChannel:
    id = 7


class FakeMessage:
    def __init__(self, content, author):
        self.content = content
        self.author = author
        self.channel = FakeChannel()


class FakeCtx:
    def __init__(self, state):
        self.state = state


def run(coro):
    return asyncio.run(coro)


def test_traced_records_command_event():
    state = AppState()
    ctx = FakeCtx(state)
    msg = FakeMessage("!afinidad", FakeUser(1))

    @traced("command")
    async def handler(ctx, message):
        return "ok"

    assert run(handler(ctx, msg)) == "ok"

    events = state.traces.all()
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "command"
    assert ev.user_id == "1"
    assert ev.user_name == "Ana"
    assert ev.channel_id == "7"
    assert ev.raw_input == "!afinidad"
    assert ev.finished_at > 0
    assert ev.total_latency_ms >= 0


def test_traced_gift_captures_affinity_delta():
    state = AppState()
    state.affinity["1"] = default_entry()
    state.affinity["1"]["points"] = 10
    ctx = FakeCtx(state)
    msg = FakeMessage("!regalo rosas", FakeUser(1))

    @traced("gift")
    async def handler(ctx, message):
        ctx.state.affinity["1"]["points"] += 3

    run(handler(ctx, msg))

    ev = state.traces.all()[0]
    assert ev.kind == "gift"
    assert ev.affinity_before == 10
    assert ev.affinity_after == 13
    assert ev.affinity_applied == 3


def test_traced_records_error_and_reraises():
    state = AppState()
    ctx = FakeCtx(state)
    msg = FakeMessage("!boom", FakeUser(1))

    @traced("command")
    async def handler(ctx, message):
        raise RuntimeError("boom")

    try:
        run(handler(ctx, msg))
    except RuntimeError:
        pass
    else:  # pragma: no cover - salvaguarda
        raise AssertionError("el error debería propagarse")

    ev = state.traces.all()[0]
    assert ev.error == "boom"
    assert ev.errors and ev.errors[0]["type"] == "RuntimeError"


def test_traced_passes_through_when_no_state():
    ctx = object()
    msg = FakeMessage("!x", FakeUser(1))

    @traced("command")
    async def handler(ctx, message):
        return "sin estado"

    assert run(handler(ctx, msg)) == "sin estado"


def test_turn_event_sets_and_resets_correlation_id():
    state = AppState()

    async def scenario():
        async with turn_event(
            state, kind="scene_select", user=FakeUser(5), raw_input="la playa"
        ) as ev:
            assert get_correlation_id() == ev.correlation_id

    run(scenario())

    assert get_correlation_id() == "-"
    ev = state.traces.all()[0]
    assert ev.kind == "scene_select"
    assert ev.raw_input == "la playa"


def test_turn_event_snapshot_is_pre_mutation():
    state = AppState(world={"season": 1}, diary=[{"x": 1}])
    state.affinity["9"] = {"points": 5}

    async def scenario():
        async with turn_event(state, kind="command", user=FakeUser(9)):
            state.affinity["9"]["points"] = 99
            state.diary.append({"y": 2})

    run(scenario())

    ev = state.traces.all()[0]
    assert ev.state_snapshot_affinity["points"] == 5
    assert ev.affinity_before == 5
    assert ev.state_snapshot_diary == [{"x": 1}]
    assert ev.state_snapshot_world == {"season": 1}


def test_build_registry_wraps_handlers():
    registry = build_registry()
    assert registry.match("!regalo rosas").__wrapped__ is gifts_cmd.handle
    assert registry.match("!afinidad").__wrapped__ is affinity_cmd.handle_afinidad
