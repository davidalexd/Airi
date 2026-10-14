"""Detección de mensajes que requieren búsqueda web."""

from __future__ import annotations

import re

SEARCH_PATTERN = re.compile(
    r"\b(?:"
    r"busca(?:r|me)?(?:\s+en\s+(?:internet|la\s+web|la\s+red))?|"
    r"búscame|investiga|consulta\s+en\s+internet|"
    r"noticias\s+recientes|últimas\s+noticias|últimos\s+datos|"
    r"información\s+actualizada|precio\s+actual|cotización\s+actual|"
    r"qué\s+ha\s+pasado|que\s+ha\s+pasado|"
    r"estado\s+actual\s+de|última\s+versión|versión\s+actual"
    r")\b",
    re.IGNORECASE,
)


def needs_web_search(message):
    return bool(SEARCH_PATTERN.search(message))
