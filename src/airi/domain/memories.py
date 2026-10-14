"""Memorias duraderas de Airi: alta, olvido y acciones del modelo (puras)."""

from __future__ import annotations

import re

from airi.domain.constants import MAX_MEMORIES_PER_USER, MAX_MEMORY_CHARS
from airi.domain.text_filters import clean_reply


def user_memories(memories, user_id):
    """Lista (siempre existente) de memorias de un usuario."""
    key = str(user_id)
    entries = memories.get(key)
    if not isinstance(entries, list):
        entries = []
        memories[key] = entries
    return entries


def add_memory(memories, user_id, text, *, now, max_items=MAX_MEMORIES_PER_USER,
               max_chars=MAX_MEMORY_CHARS):
    """Guarda una memoria. Devuelve False si está vacía o es duplicada."""
    text = clean_reply(text).strip()[:max_chars].strip()
    if not text:
        return False
    entries = user_memories(memories, user_id)
    # Evitar duplicados exactos o casi exactos (solo frases suficientemente
    # largas, para no confundir "Dato 1" con "Dato 10").
    lower = text.lower()
    existing = [
        e.get("text", "").lower()
        for e in entries
        if isinstance(e, dict) and e.get("text")
    ]
    is_duplicate = lower in existing or any(
        min(len(lower), len(old)) >= 12 and (lower in old or old in lower)
        for old in existing
    )
    if is_duplicate:
        return False
    entries.append({"text": text, "created_at": float(now)})
    while len(entries) > max_items:
        entries.pop(0)
    return True


def forget_memory(memories, user_id, index=None):
    """Borra la memoria index (1-based) o todas si index es None."""
    entries = user_memories(memories, user_id)
    if index is None:
        if not entries:
            return False
        memories[str(user_id)] = []
        return True
    if 1 <= index <= len(entries):
        entries.pop(index - 1)
        return True
    return False


def process_memory_action(memories, user_id, action, *, now):
    """Aplica la acción de memoria del modelo (guardar u olvidar).

    Devuelve True solo si se guardó una memoria nueva.
    """
    if not isinstance(action, str):
        return False
    action = action.strip()
    if not action or action.lower() == "none":
        return False
    forget_match = re.match(r"(?i)^olvidar:\s*(\d+)$", action)
    if forget_match:
        forget_memory(memories, user_id, int(forget_match.group(1)))
        return False
    return add_memory(memories, user_id, action, now=now)
