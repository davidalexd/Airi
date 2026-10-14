"""Tests de instrumentación: el evento se registra aunque el LLM falle."""

from __future__ import annotations

import asyncio

import pytest

from airi.services.conversation import ConversationService, TurnContext
from tests.fakes.fake_doubles import FakeUser
from tests.fakes.fake_llm import FakeLLM, llm_json
from tests.fakes.in_memory_repo import make_state

NOW = 1_000_000.0
DAVID = FakeUser(42, "David")


def run(coro):
    return asyncio.run(coro)


class RaisingLLM:
    """LLM que siempre falla (simula llama-server caído)."""

    async def chat(self, messages, **kwargs):
        raise RuntimeError("llama caído")

    async def chat_with_meta(self, messages, **kwargs):
        raise RuntimeError("llama caído")


def test_llm_error_is_recorded_and_event_still_saved():
    state, _ = make_state()
    svc = ConversationService(llm=RaisingLLM(), state=state, clock=lambda: NOW)

    with pytest.raises(RuntimeError):
        run(svc.run_turn(
            DAVID, [(DAVID, "hola")], TurnContext(correlation_id="boom")
        ))

    ev = state.traces.by_correlation_id("boom")
    assert ev is not None
    assert ev.error
    assert ev.errors and ev.errors[0]["type"] == "RuntimeError"
    assert ev.kind == "message"


def test_event_kind_is_injectable():
    state, _ = make_state()
    llm = FakeLLM(replies=[llm_json("hola")])
    svc = ConversationService(llm=llm, state=state, clock=lambda: NOW)

    run(svc.run_turn(DAVID, [(DAVID, "hola")], TurnContext(kind="command")))

    assert state.traces.last(1)[0].kind == "command"
