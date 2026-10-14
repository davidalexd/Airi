"""Logging con correlation_id para trazar un turno entre módulos.

El correlation_id vive en un `ContextVar`, así que funciona correctamente en
código asíncrono concurrente (cada tarea ve su propio valor) sin necesidad de
pasarlo por `extra=` en cada llamada a log.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

CORRELATION_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s [cid=%(correlation_id)s]: %(message)s"
)

# Correlation_id del turno actual ("-" fuera de un turno).
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(cid: str):
    """Fija el correlation_id del turno; devuelve el token para resetearlo."""
    return correlation_id.set(cid)


def get_correlation_id() -> str:
    """Correlation_id del turno actual ("-" si no hay)."""
    return correlation_id.get()


def reset_correlation_id(token) -> None:
    """Restaura el correlation_id previo al terminar el turno."""
    correlation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Inyecta el correlation_id del ContextVar en cada LogRecord."""

    def filter(self, record):
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id.get()
        return True


def get_logger(name):
    """Logger del paquete con el filtro de correlation_id instalado."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, CorrelationIdFilter) for f in logger.filters):
        logger.addFilter(CorrelationIdFilter())
    return logger


def install_correlation_format():
    """Añade `[cid=...]` al formato raíz y garantiza el filtro (idempotente).

    Sin el filtro, cualquier log que no traiga `correlation_id` explota al
    formatear (`KeyError`) y el mensaje se pierde.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        fmt = handler.formatter
        current = getattr(fmt, "_fmt", "") or ""
        if "correlation_id" not in current:
            handler.setFormatter(logging.Formatter(CORRELATION_FORMAT))
        if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
            handler.addFilter(CorrelationIdFilter())
