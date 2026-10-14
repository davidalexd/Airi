"""Tests del TraceStore: ring en memoria, disco atómico y best-effort."""

from __future__ import annotations

import asyncio
import os

from airi.observability.trace import TurnEvent
from airi.observability.trace_store import TraceStore, load_events_from_dir


def run(coro):
    return asyncio.run(coro)


def test_ring_keeps_last_and_finds_by_cid():
    store = TraceStore(None, keep_last=3)
    for i in range(5):
        run(store.save(TurnEvent(correlation_id=f"c{i}")))

    assert len(store) == 3
    assert [e.correlation_id for e in store.last(2)] == ["c4", "c3"]
    assert store.by_correlation_id("c4").correlation_id == "c4"
    assert store.by_correlation_id("c0") is None
    store.clear()
    assert len(store) == 0


def test_save_writes_file_and_loads(tmp_path):
    store = TraceStore(tmp_path, keep_last=10)
    path = run(store.save(
        TurnEvent(correlation_id="abc", user_id="1", final_reply="hola")
    ))

    assert path is not None and os.path.exists(path)
    events = load_events_from_dir(tmp_path)
    assert [e.correlation_id for e in events] == ["abc"]
    assert events[0].final_reply == "hola"


def test_update_replaces_without_duplicating(tmp_path):
    store = TraceStore(tmp_path, keep_last=10)
    ev = TurnEvent(correlation_id="dup", user_id="1")
    run(store.save(ev))

    ev.date_event = "recovered"
    run(store.update(ev))

    assert len(store) == 1
    assert store.by_correlation_id("dup").date_event == "recovered"
    events = load_events_from_dir(tmp_path)
    assert len(events) == 1
    assert events[0].date_event == "recovered"


def test_write_failure_returns_none_without_raising(tmp_path):
    # Directorio convertido en fichero: makedirs falla → None, sin excepción.
    blocker = tmp_path / "bloqueado"
    blocker.write_text("x")
    store = TraceStore(blocker / "sub", keep_last=10)

    ev = TurnEvent(correlation_id="cid", user_id="1")
    assert run(store.save(ev)) is None
    assert run(store.update(ev)) is None
    # El ring en memoria sigue funcionando aunque el disco falle.
    assert store.by_correlation_id("cid") is not None
