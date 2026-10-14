"""Máquina de estados de las citas (lógica pura)."""

from __future__ import annotations

from airi.domain.config import (
    DATE_CRISIS_DROP,
    DATE_CRISIS_MIN_TURNS,
    DATE_END_MIN_TURNS,
    DATE_LAST_CHANCE_MAX_RECOVERY,
    DATE_MAX_SECONDS,
    DATE_MAX_TURNS,
    DATE_STATES,
    LAST_CHANCE_RESULTS,
)

# ============================================================
# CITAS: MÁQUINA DE ESTADOS (active → last_chance → final_scene → closed)
# ============================================================


def new_date_session(scene, affinity_start, now):
    """Crea una sesión de cita nueva en estado `active`.

    `affinity_start` es la afinidad al empezar la cita: sirve de techo para la
    recuperación de la última oportunidad.
    """
    try:
        start = int(affinity_start)
    except (TypeError, ValueError):
        start = 0
    return {
        "scene": str(scene or ""),
        "state": "active",
        "turns": 0,
        "affinity_start": start,
        "affinity_crisis": None,
        "crisis_reason": "none",
        "last_chance_used": False,
        "last_chance_result": "none",
        "history": [],
        "started_at": float(now),
    }


def normalize_date_session(session):
    """Completa los campos que falten (p. ej. sesiones cargadas de disco)."""
    if not isinstance(session, dict):
        return None
    session.setdefault("scene", "")
    session.setdefault("state", "active")
    session.setdefault("turns", 0)
    session.setdefault("affinity_start", 0)
    session.setdefault("affinity_crisis", None)
    session.setdefault("crisis_reason", "none")
    session.setdefault("last_chance_used", False)
    session.setdefault("last_chance_result", "none")
    session.setdefault("history", [])
    session.setdefault("started_at", 0.0)
    if session.get("state") not in DATE_STATES:
        session["state"] = "active"
    if not isinstance(session.get("history"), list):
        session["history"] = []
    try:
        session["turns"] = int(session.get("turns", 0) or 0)
    except (TypeError, ValueError):
        session["turns"] = 0
    try:
        session["affinity_start"] = int(session.get("affinity_start", 0) or 0)
    except (TypeError, ValueError):
        session["affinity_start"] = 0
    return session


def date_turns_left(session):
    """Turnos que le quedan a la cita antes de agotar el límite."""
    if not isinstance(session, dict):
        return 0
    try:
        turns = int(session.get("turns", 0) or 0)
    except (TypeError, ValueError):
        turns = 0
    return max(0, DATE_MAX_TURNS - turns)


def date_seconds_left(session, now, max_seconds=DATE_MAX_SECONDS):
    """Segundos reales que le quedan a la cita (0 si ya expiró)."""
    if not isinstance(session, dict):
        return 0
    if session.get("state") == "closed":
        return 0
    try:
        started = float(session.get("started_at", 0.0) or 0.0)
        elapsed = float(now) - started
    except (TypeError, ValueError):
        return 0
    return max(0.0, float(max_seconds) - elapsed)


def date_expired(session, now, max_seconds=DATE_MAX_SECONDS):
    """True si la cita sigue abierta pero ha superado su duración máxima."""
    if not isinstance(session, dict):
        return False
    if session.get("state") == "closed":
        return False
    try:
        started = float(session.get("started_at", 0.0) or 0.0)
        elapsed = float(now) - started
    except (TypeError, ValueError):
        return False
    return elapsed >= float(max_seconds)


def crisis_allowed(session):
    """La crisis solo puede dispararse una vez y tras unos turnos mínimos."""
    if not isinstance(session, dict):
        return False
    if session.get("state") != "active":
        return False
    if session.get("last_chance_used"):
        return False
    try:
        turns = int(session.get("turns", 0) or 0)
    except (TypeError, ValueError):
        turns = 0
    return turns >= DATE_CRISIS_MIN_TURNS


def end_allowed(session):
    """El modelo puede cerrar la cita solo pasados unos turnos mínimos."""
    if not isinstance(session, dict):
        return False
    if session.get("state") not in ("active", "last_chance"):
        return False
    try:
        turns = int(session.get("turns", 0) or 0)
    except (TypeError, ValueError):
        turns = 0
    return turns >= DATE_END_MIN_TURNS


def resolve_date_at_limit(session, points=0):
    """Agota los turnos: fuerza el cierre y devuelve el evento final.

    Deja siempre la sesión en estado `final_scene`.
    """
    if not isinstance(session, dict):
        return "closed"
    if session.get("state") == "last_chance":
        result = session.get("last_chance_result", "none")
        if result not in ("success", "partial"):
            session["last_chance_result"] = "fail"
            session["state"] = "final_scene"
            return "failed_last_chance"
        session["state"] = "final_scene"
        return "recovered" if result == "success" else "partial_recovery"
    session["state"] = "final_scene"
    return "ending"


def last_chance_recovery(session, result, current_points):
    """Puntos que se recuperan al salvarla en la última oportunidad.

    Nunca supera `DATE_LAST_CHANCE_MAX_RECOVERY` ni devuelve la afinidad por
    encima del valor con el que empezó la cita.
    """
    if result == "success":
        earned = DATE_LAST_CHANCE_MAX_RECOVERY
    elif result == "partial":
        earned = DATE_LAST_CHANCE_MAX_RECOVERY // 2
    else:
        earned = 0
    try:
        start = int(session.get("affinity_start", 0) or 0)
    except (TypeError, ValueError):
        start = 0
    try:
        ceiling = max(0, start - int(current_points))
    except (TypeError, ValueError):
        ceiling = 0
    return max(0, min(earned, ceiling))


def step_date(
    session,
    delta=0,
    points=0,
    decision="continue",
    reason="none",
    last_chance_result="none",
    end_keyword=False,
    now=None,
):
    """Avanza un turno la máquina de estados de la cita. Muta `session`.

    `points` es la afinidad tras aplicar el delta de este turno. Devuelve
    `(state, event)`, donde `event` describe lo ocurrido en el turno.
    """
    if not isinstance(session, dict):
        return "closed", "closed"
    normalize_date_session(session)
    state = session["state"]
    session["turns"] = int(session.get("turns", 0) or 0) + 1

    if state == "closed":
        return "closed", "closed"

    if state == "active":
        if decision == "crisis" and crisis_allowed(session):
            session["state"] = "last_chance"
            session["affinity_crisis"] = int(points)
            session["crisis_reason"] = str(reason or "none")[:300]
            session["last_chance_used"] = True
            return "last_chance", "crisis"
        drop = int(session.get("affinity_start", 0) or 0) - int(points)
        if drop >= DATE_CRISIS_DROP and crisis_allowed(session):
            session["state"] = "last_chance"
            session["affinity_crisis"] = int(points)
            session["crisis_reason"] = str(reason or "la afinidad cayó")[:300]
            session["last_chance_used"] = True
            return "last_chance", "crisis"
        if session["turns"] >= DATE_MAX_TURNS:
            return "final_scene", resolve_date_at_limit(session, points)
        if end_keyword or (decision == "end" and end_allowed(session)):
            session["state"] = "final_scene"
            return "final_scene", "ending"
        return "active", "continue"

    if state == "last_chance":
        result = last_chance_result if last_chance_result in LAST_CHANCE_RESULTS else "none"
        if result == "success":
            session["last_chance_result"] = "success"
            session["state"] = "final_scene"
            return "final_scene", "recovered"
        if result == "partial":
            session["last_chance_result"] = "partial"
            session["state"] = "final_scene"
            return "final_scene", "partial_recovery"
        if result == "fail":
            session["last_chance_result"] = "fail"
            session["state"] = "final_scene"
            return "final_scene", "failed_last_chance"
        if session["turns"] >= DATE_MAX_TURNS:
            return "final_scene", resolve_date_at_limit(session, points)
        return "last_chance", "continue"

    if state == "final_scene":
        session["state"] = "closed"
        return "closed", "closed"

    return "closed", "closed"
