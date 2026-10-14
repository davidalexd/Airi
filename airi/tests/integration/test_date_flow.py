"""Tests de integración del flujo de citas con DateService (sin Discord)."""

import asyncio

from airi.domain.config import DATE_MAX_TURNS
from airi.domain.dates import new_date_session
from airi.domain.texts import DATE_CRISIS_TEXT
from airi.services.date_service import DateService
from tests.fakes.fake_doubles import FakeNotifier, FakeUser
from tests.fakes.in_memory_repo import make_state

ANA = FakeUser(1, "Ana")
NOW = 1_000_000.0


def make_service(state, notifier):
    return DateService(state=state, notifier=notifier, clock=lambda: NOW)


def run(coro):
    return asyncio.run(coro)


def step(service, session, **kw):
    defaults = dict(
        user=ANA, text="hola", delta=0, points=40,
        date_decision="continue", date_reason="none",
        last_chance_result="none", now=NOW,
    )
    defaults.update(kw)
    return run(service.process_turn(session, **defaults))


def test_continue_saves_without_messages():
    state, counters = make_state()
    session = new_date_session("paseo", 40, now=NOW)
    state.dates["1"] = session
    notifier = FakeNotifier()
    service = make_service(state, notifier)

    event = step(service, session)

    assert event == "continue"
    assert notifier.sent == []
    assert counters["dates"] == 1
    assert session["turns"] == 1
    assert session["state"] == "active"


def test_crisis_notifies_and_enters_last_chance():
    state, counters = make_state()
    session = new_date_session("paseo", 40, now=NOW)
    session["turns"] = 3  # DATE_CRISIS_MIN_TURNS
    state.dates["1"] = session
    notifier = FakeNotifier()
    service = make_service(state, notifier)

    event = step(service, session, date_decision="crisis", date_reason="se incomodó",
                 points=36)

    assert event == "crisis"
    assert session["state"] == "last_chance"
    assert session["crisis_reason"] == "se incomodó"
    assert notifier.sent == [DATE_CRISIS_TEXT]
    assert counters["dates"] == 1


def test_end_keyword_closes_and_logs_diary():
    state, _ = make_state()
    session = new_date_session("paseo", 40, now=NOW)
    session["turns"] = 4
    state.dates["1"] = session
    state.users["1"] = {"name": "Ana"}
    notifier = FakeNotifier()
    service = make_service(state, notifier)

    event = step(service, session, text="adiós, nos vemos")

    assert event == "ending"
    assert "1" not in state.dates
    assert session["state"] == "closed"
    assert any(e.get("kind") == "date" for e in state.diary)
    assert notifier.sent  # mensaje de cierre


def test_recovery_applies_affinity_and_closes():
    state, _ = make_state(affinity={"1": {"points": 36, "last_interaction": NOW,
                                          "last_gain": 0.0, "milestones": []}})
    session = new_date_session("paseo", 40, now=NOW)
    session["state"] = "last_chance"
    session["last_chance_used"] = True
    session["turns"] = 3
    state.dates["1"] = session
    state.users["1"] = {"name": "Ana"}
    notifier = FakeNotifier()
    service = make_service(state, notifier)

    event = step(service, session, points=36, last_chance_result="success")

    assert event == "recovered"
    # Recuperación = min(12, 40 - 36) = 4.
    assert state.entry_points(1) == 40
    assert "1" not in state.dates


def test_failed_last_chance_closes_without_recovery():
    state, _ = make_state(affinity={"1": {"points": 30, "last_interaction": NOW,
                                          "last_gain": 0.0, "milestones": []}})
    session = new_date_session("paseo", 40, now=NOW)
    session["state"] = "last_chance"
    session["last_chance_used"] = True
    session["turns"] = 3
    state.dates["1"] = session
    state.users["1"] = {"name": "Ana"}
    service = make_service(state, FakeNotifier())

    event = step(service, session, points=30, last_chance_result="fail")

    assert event == "failed_last_chance"
    assert state.entry_points(1) == 30  # sin recuperación
    assert "1" not in state.dates


def test_full_date_happy_path():
    state, _ = make_state()
    session = new_date_session("cena", 40, now=NOW)
    state.dates["1"] = session
    state.users["1"] = {"name": "Ana"}
    notifier = FakeNotifier()
    service = make_service(state, notifier)

    events = [step(service, session) for _ in range(DATE_MAX_TURNS)]

    # Al agotar los turnos la cita cierra con "ending".
    assert events[-1] == "ending"
    assert session["state"] == "closed"
    assert "1" not in state.dates
    assert notifier.sent  # hubo mensaje de cierre
