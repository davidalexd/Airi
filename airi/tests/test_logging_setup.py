"""Tests del logging con correlation_id (Fase 5).

Cubren el bug histórico: `install_correlation_format()` fijaba un formato con
`%(correlation_id)s` pero no instalaba `CorrelationIdFilter`, de modo que
cualquier log sin `correlation_id` (la mayoría de módulos) rompía al formatear
con `KeyError` y perdía el mensaje.
"""

import io
import logging

import pytest

from airi.observability.logging_setup import (
    CORRELATION_FORMAT,
    CorrelationIdFilter,
    get_logger,
    install_correlation_format,
)


@pytest.fixture
def root_handler():
    """Handler aislado en el root logger; restaura el estado al terminar."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        yield handler, stream
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def test_log_without_correlation_id_does_not_break(root_handler):
    handler, stream = root_handler
    install_correlation_format()

    logging.getLogger("airi.test.nocid").info("mensaje sin cid")
    handler.flush()

    out = stream.getvalue()
    assert "mensaje sin cid" in out
    assert "[cid=-]" in out


def test_log_with_correlation_id_shows_it(root_handler):
    handler, stream = root_handler
    install_correlation_format()

    logging.getLogger("airi.test.cid").info(
        "turno", extra={"correlation_id": "abc123"}
    )
    handler.flush()

    assert "[cid=abc123]" in stream.getvalue()


def test_install_adds_filter_and_formatter(root_handler):
    handler, _ = root_handler
    install_correlation_format()

    assert any(isinstance(f, CorrelationIdFilter) for f in handler.filters)
    assert handler.formatter._fmt == CORRELATION_FORMAT


def test_install_is_idempotent(root_handler):
    handler, _ = root_handler
    install_correlation_format()
    install_correlation_format()

    filters = [f for f in handler.filters if isinstance(f, CorrelationIdFilter)]
    assert len(filters) == 1


def test_install_preserves_existing_cid_format(root_handler):
    handler, _ = root_handler
    handler.setFormatter(logging.Formatter(CORRELATION_FORMAT))

    install_correlation_format()

    assert handler.formatter._fmt == CORRELATION_FORMAT
    assert any(isinstance(f, CorrelationIdFilter) for f in handler.filters)


def test_get_logger_attaches_filter():
    logger = get_logger("airi.test.getlogger")
    assert any(isinstance(f, CorrelationIdFilter) for f in logger.filters)
    # Idempotente: llamarlo de nuevo no duplica el filtro.
    assert get_logger("airi.test.getlogger") is logger
    filters = [f for f in logger.filters if isinstance(f, CorrelationIdFilter)]
    assert len(filters) == 1
