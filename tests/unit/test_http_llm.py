"""Tests de `airi.adapters.http_llm.HttpLlmClient`."""

import asyncio
from unittest.mock import MagicMock

import pytest

from airi.adapters.http_llm import DEFAULT_MAX_OUTPUT_TOKENS, HttpLlmClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    """Elimina variables LLM del entorno para cada test."""
    for key in ("LLM_MODEL", "LLM_TIMEOUT", "LLM_TEMPERATURE", "LLM_MAX_TOKENS"):
        monkeypatch.delenv(key, raising=False)


def _make_session():
    """Devuelve un objeto falso con el atributo `post`."""
    return MagicMock()


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Valores por defecto (sin variables de entorno)
# ---------------------------------------------------------------------------


def test_defaults_no_env():
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.model == "Qwen3.6-35B-A3B-MTP-UD-IQ3_S"
    assert client.timeout == 300
    assert client.temperature == 0.6
    assert client.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS


# ---------------------------------------------------------------------------
# Lectura desde variables de entorno
# ---------------------------------------------------------------------------


def test_reads_llm_model_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "MiModelo")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.model == "MiModelo"


def test_reads_llm_timeout_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "600")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.timeout == 600


def test_reads_llm_temperature_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.85")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.temperature == 0.85


def test_reads_llm_max_tokens_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.max_output_tokens == 4096


# ---------------------------------------------------------------------------
# Valores inválidos en env → fallback a default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["abc", "", "   ", "1.2.3"])
def test_invalid_timeout_fallback(monkeypatch, value):
    monkeypatch.setenv("LLM_TIMEOUT", value)
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.timeout == 300


@pytest.mark.parametrize("value", ["abc", "", "   ", "xyz"])
def test_invalid_temperature_fallback(monkeypatch, value):
    monkeypatch.setenv("LLM_TEMPERATURE", value)
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.temperature == 0.6


@pytest.mark.parametrize("value", ["abc", "", "   ", "1.2.3"])
def test_invalid_max_tokens_fallback(monkeypatch, value):
    monkeypatch.setenv("LLM_MAX_TOKENS", value)
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
    )
    assert client.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS


# ---------------------------------------------------------------------------
# Prioridad: explícito > env > default
# ---------------------------------------------------------------------------


def test_explicit_model_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "DelEnv")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        model="Explicito",
    )
    assert client.model == "Explicito"


def test_explicit_timeout_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "999")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        timeout=120,
    )
    assert client.timeout == 120


def test_explicit_temperature_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        temperature=0.95,
    )
    assert client.temperature == 0.95


def test_explicit_max_tokens_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "9999")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        max_output_tokens=512,
    )
    assert client.max_output_tokens == 512


def test_none_explicit_uses_env(monkeypatch):
    """`timeout=None` (valor por defecto) debe respetar la variable de entorno."""
    monkeypatch.setenv("LLM_TIMEOUT", "420")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        timeout=None,
    )
    assert client.timeout == 420


def test_none_explicit_uses_env_temperature(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.42")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        temperature=None,
    )
    assert client.temperature == 0.42


def test_none_explicit_uses_env_max_tokens(monkeypatch):
    """`max_output_tokens=None` (por defecto) debe respetar LLM_MAX_TOKENS."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "777")
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=_make_session(),
        max_output_tokens=None,
    )
    assert client.max_output_tokens == 777


# ---------------------------------------------------------------------------
# Payload: `max_tokens` en la petición usa el valor correcto
# ---------------------------------------------------------------------------


def _make_async_session():
    """Sesión doble con `post` que captura el payload."""
    session = MagicMock()

    class _Resp:
        async def json(self):
            return {"choices": [{"message": {"content": "hi"}}]}

        def raise_for_status(self):
            pass

    class _PostCtx:
        def __init__(self):
            self._captured = None

        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *exc_info):
            return False

    def fake_post(url, json=None, timeout=None):
        session._captured = json
        return _PostCtx()

    session.post = fake_post
    return session


def test_payload_uses_max_output_tokens():
    """Verifica que `chat_with_meta` envía `max_tokens` correcto en el payload."""
    session = _make_async_session()
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=session,
        max_output_tokens=1234,
    )
    run(
        client.chat_with_meta(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
        )
    )
    payload = session._captured
    assert payload["max_tokens"] == 1234


def test_payload_explicit_max_tokens_overrides_adapter():
    """`max_tokens` explícito en el payload pisa el valor del adapter."""
    session = _make_async_session()
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=session,
        max_output_tokens=9999,
    )
    run(
        client.chat_with_meta(
            [{"role": "user", "content": "hi"}],
            max_tokens=42,
            temperature=0.5,
        )
    )
    payload = session._captured
    assert payload["max_tokens"] == 42


def test_payload_max_tokens_zero_uses_adapter():
    """`max_tokens=0` (truthy-falsy) usa el valor del adapter por `or`."""
    session = _make_async_session()
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=session,
        max_output_tokens=500,
    )
    run(
        client.chat_with_meta(
            [{"role": "user", "content": "hi"}],
            max_tokens=0,
            temperature=0.5,
        )
    )
    payload = session._captured
    assert payload["max_tokens"] == 500


def test_payload_llm_max_tokens_minus_one_is_unlimited(monkeypatch):
    """LLM_MAX_TOKENS=-1 → payload["max_tokens"] == -1 (ilimitado)."""
    monkeypatch.setenv("LLM_MAX_TOKENS", "-1")
    session = _make_async_session()
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=session,
    )
    run(
        client.chat_with_meta(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
        )
    )
    payload = session._captured
    assert payload["max_tokens"] == -1


def test_payload_llm_max_tokens_zero_is_no_output(monkeypatch):
    """LLM_MAX_TOKENS=0 → payload["max_tokens"] == 0.

    Footgun: en llama.cpp, max_tokens=0 produce respuesta vacía.
    El usuario que quiera sin límite debe usar -1.
    """
    monkeypatch.setenv("LLM_MAX_TOKENS", "0")
    session = _make_async_session()
    client = HttpLlmClient(
        base_url="http://localhost:8080",
        session=session,
    )
    run(
        client.chat_with_meta(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
        )
    )
    payload = session._captured
    assert payload["max_tokens"] == 0
