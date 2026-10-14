"""Registro de usuarios conocidos del canal (lógica pura)."""

from __future__ import annotations


def register_activity(users, *, user_id, display_name, now):
    """Actualiza nombre/visitas del usuario. Devuelve True si es nuevo."""
    key = str(user_id)
    entry = users.get(key)
    is_new = not isinstance(entry, dict)
    if is_new:
        entry = {
            "name": display_name,
            "first_seen": float(now),
            "last_seen": float(now),
            "interactions": 0,
        }
        users[key] = entry
    entry["name"] = display_name
    entry["last_seen"] = float(now)
    entry["interactions"] = int(entry.get("interactions", 0) or 0) + 1
    return is_new
