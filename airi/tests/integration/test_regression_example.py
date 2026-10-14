"""Test de regresión generado desde la traza example_bug.json.

Usa el fixture de traza real en `tests/fixtures/traces/example_bug.json`.
"""

import asyncio
import os

from airi.replay import replay_trace

TRACE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "traces",
    "example_bug.json",
)


def test_regression_example_bug():
    result = asyncio.run(replay_trace(TRACE))
    assert result.reproducible, "la traza no tiene raw_llm"
    assert result.matches_original, f"divergencia: {result.checks}"
