"""Filtro heurístico anti-alucinación sobre respuestas con contexto web."""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# [CAMBIO] Filtro heurístico: detecta datos concretos que no aparecen en
# las fuentes y que por tanto podrían ser alucinaciones.
def reply_seems_grounded(reply, web_context):
    """Comprueba datos concretos contra las fuentes con criterio tolerante.
    Reglas:
      - Un año (2026) o un mes-año suelto: NO se considera inventado
        (suele ser el tema de la consulta).
      - Una fecha concreta (día + mes) que no aparezca en fuentes: se marca
        como "sospechosa" pero no tumba la respuesta por sí sola.
      - Se rechaza la respuesta solo si hay 3+ datos sospechosos, o si
        aparece un título/lista claramente inventado.
    """
    if not web_context:
        return True
    context_lower = web_context.lower()

    # 1) Fechas con día concreto. NO cuentan años sueltos ni "octubre 2026".
    day_dates = re.findall(
        r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|"
        r"agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
        reply,
        flags=re.IGNORECASE,
    )
    suspicious = []
    for token in day_dates:
        if token.lower() not in context_lower:
            suspicious.append(("fecha", token))

    # 2) Títulos candidatos. Buscamos frases de 2+ palabras capitalizadas.
    title_pattern = re.compile(
        r"\b("
        r"[A-ZÁÉÍÓÚÑ][\w'’\-]+"
        r"(?:\s+(?:"
        r"[A-ZÁÉÍÓÚÑ][\w'’\-]+"
        r"|de|del|no|wa|to|ni|ga|wo"
        r"|\d+|1/2|II|III|IV"
        r"))+"
        r")\b"
    )

    STOP_TITLES = {
        "Hola", "Siii", "Oye", "Aquí", "También", "Pero", "Porque",
        "Airi", "Discord", "Un", "La", "El", "Los", "Las",
    }

    title_candidates = set()
    for match in title_pattern.finditer(reply):
        candidate = match.group(1).strip()
        if len(candidate.split()) < 2:
            continue
        if candidate in STOP_TITLES:
            continue
        title_candidates.add(candidate)

    for candidate in title_candidates:
        c_lower = candidate.lower()
        if c_lower in context_lower:
            continue
        # Coincidencia parcial: todas las palabras "significativas" aparecen.
        words = [
            w for w in re.split(r"[\s\-]+", candidate)
            if len(w) >= 4 and w.lower() not in {
                "temporada", "season", "anime", "serie",
            }
        ]
        if words and all(w.lower() in context_lower for w in words):
            continue
        suspicious.append(("título", candidate))

    # 3) Decisión con umbral. Un dato suelto NO invalida la respuesta;
    # hacen falta 3 o más sospechas para rechazarla.
    if len(suspicious) >= 3:
        log.warning(
            "Respuesta rechazada: %d datos sospechosos -> %s",
            len(suspicious),
            suspicious[:5],
        )
        return False

    if suspicious:
        log.info(
            "Datos sospechosos (no bloqueantes): %s",
            suspicious[:5],
        )
    return True
