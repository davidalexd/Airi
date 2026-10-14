"""Shim de compatibilidad → airi.discord_bot.views.date.

El código nuevo debe importar de `airi.discord_bot.views.date` directamente.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from airi.discord_bot.views.date import (  # noqa: E402,F401
    DATE_EMBED_COLOR,
    DISCORD_LABEL_MAX,
    DISCORD_MAX_BUTTONS,
    FREE_TEXT_LABEL,
    DateChoiceView,
    SceneSelectView,
    build_date_embed,
    clamp_label,
)
