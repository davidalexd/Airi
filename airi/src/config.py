"""Configuración de la aplicación leída del entorno (stdlib, sin dependencias).

Se usa un `dataclass` estándar en lugar de `pydantic-settings` porque en este
entorno no hay red para instalar dependencias nuevas. Los valores se leen una
vez con `Settings.from_env()`, reutilizando el patrón `env_int` del dominio.

Precedencia de nombres: se prefiere el prefijo `AIRI_` y se acepta el nombre
histórico sin prefijo (`AIRI_TRACE_DIR` → `TRACE_DIR`), igual que hace la CLI
`python -m airi.trace`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from airi.domain.config import env_int

DEFAULT_TRACE_KEEP_LAST = 500


def _env_first(*names, default=""):
    """Primer valor de entorno no vacío entre `names`, o `default`."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value
    return default


@dataclass(frozen=True)
class Settings:
    """Ajustes de observabilidad de la aplicación."""

    # Directorio de trazas en disco (vacío = solo ring en memoria).
    trace_dir: str = ""
    # Tamaño del ring buffer en memoria (eventos inspeccionables con !debug).
    trace_keep_last: int = DEFAULT_TRACE_KEEP_LAST

    @classmethod
    def from_env(cls) -> "Settings":
        """Construye los ajustes desde el entorno (una vez, al arrancar)."""
        return cls(
            trace_dir=_env_first("AIRI_TRACE_DIR", "TRACE_DIR", default=""),
            trace_keep_last=env_int(
                "AIRI_TRACE_KEEP_LAST",
                env_int("TRACE_KEEP_LAST", DEFAULT_TRACE_KEEP_LAST),
            ),
        )
