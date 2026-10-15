"""Tests del método `AppState.log_diary_event` (escritura real del diario).

En producción la migración dejó este método cableado a un logger vacío; estos
tests garantizan que el AppState por defecto escribe y persiste las entradas.
"""

import time

from airi.services.state import AppState

NOW = 1_000_000.0


class _FakeUser:
    def __init__(self, uid, name):
        self.id = uid
        self.display_name = name


def _state(**overrides):
    saved = []
    state = AppState(
        world={"season": 3},
        users={"7": {"name": "David"}},
        save_diary=lambda: saved.append(True),
        **overrides,
    )
    return state, saved


def test_log_diary_event_persists_entry():
    state, saved = _state()

    assert state.log_diary_event("meet", 7, "Hoy he conocido a David.", now=NOW)

    assert len(state.diary) == 1
    entry = state.diary[0]
    assert entry["kind"] == "meet"
    assert entry["user_id"] == "7"
    assert entry["user_name"] == "David"
    assert entry["text"] == "Hoy he conocido a David."
    assert entry["season"] == 3
    assert entry["ts"] == NOW
    assert saved == [True]


def test_log_diary_event_accepts_user_object():
    state, saved = _state()

    assert state.log_diary_event("gift", _FakeUser(7, "David"), "Le gustó.")

    assert state.diary[0]["user_id"] == "7"
    assert state.diary[0]["user_name"] == "David"
    assert saved == [True]


def test_log_diary_event_uses_clock_when_now_missing():
    state, _ = _state()

    state.log_diary_event("level", 7, "¡Amiga!")

    assert abs(state.diary[0]["ts"] - time.time()) < 5


def test_log_diary_event_empty_text_is_not_saved():
    state, saved = _state()

    assert state.log_diary_event("meet", 7, "") is False
    assert state.log_diary_event("meet", 7, None) is False

    assert state.diary == []
    assert saved == []


def test_log_diary_event_unknown_user_falls_back_to_someone():
    state, _ = _state()

    assert state.log_diary_event("confession", "99", "Quiero estar con esa persona.")

    assert state.diary[0]["user_name"] == "alguien"


def test_log_diary_event_is_monotonic_after_state_creation():
    # El nombre del usuario se resuelve en tiempo de llamada (tras registrarse).
    state, saved = _state()
    state.users["7"] = {"name": "DAVID"}

    state.log_diary_event("meet", 7, "Hola.")

    assert state.diary[0]["user_name"] == "DAVID"
    assert saved == [True]
