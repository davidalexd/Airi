"""Lógica pura del simulador de citas de Airi."""

# Compatibilidad: game.py ahora es un shim sobre airi.domain.*.
# El código nuevo debe importar de airi.domain directamente.

import os
import sys

# Permite importar `airi` sin instalar el paquete (src/ layout).
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from airi.adapters.json_repo import load_json, load_json_list, save_json  # noqa: E402,F401
from airi.domain.affinity import *  # noqa: E402,F401,F403
from airi.domain.config import *  # noqa: E402,F401,F403
from airi.domain.dates import *  # noqa: E402,F401,F403
from airi.domain.diary import *  # noqa: E402,F401,F403
from airi.domain.gifts import *  # noqa: E402,F401,F403

