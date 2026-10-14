"""Test de regresión generado desde la traza affinity_delta_without_reason.json.

Usa el fixture de traza real en `tests/fixtures/traces/affinity_delta_without_reason.json`.
"""

import asyncio
import os

from airi.observability.replay import replay_trace

TRACE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "traces",
    "affinity_delta_without_reason.json",
)


def test_regression_affinity_delta_without_reason():
    result = asyncio.run(replay_trace(TRACE))
    assert result.reproducible, "la traza no tiene raw_llm"
    assert result.matches_original, f"divergencia: {result.checks}"
