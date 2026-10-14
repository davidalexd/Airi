import asyncio
import json
import logging
import os
import random
import time
from io import BytesIO

import discord
from dotenv import load_dotenv

# Cargamos el .env ANTES de importar game: sus constantes se leen del entorno
# en el momento del import, así que necesitan los valores ya presentes.
load_dotenv()

import game  # noqa: E402

# Adaptadores concretos (el resto de la app depende de los puertos).
from airi.adapters.brave_search import BraveSearchClient  # noqa: E402
from airi.adapters.discord_notifier import DiscordNotifier  # noqa: E402
from airi.adapters.http_llm import HttpLlmClient  # noqa: E402
from airi.adapters.nekosbest import NekosBestProvider  # noqa: E402
from airi.config import Settings  # noqa: E402

# Capa Discord (UI + dispatch), desacoplada mediante BotContext.
from airi.discord_bot import embeds  # noqa: E402
from airi.discord_bot import turn as discord_turn  # noqa: E402
from airi.discord_bot.client import create_client  # noqa: E402
from airi.discord_bot.commands import build_registry  # noqa: E402
from airi.discord_bot.context import BotContext  # noqa: E402

# Lógica de dominio (pura): este módulo solo orquesta Discord/HTTP.
from airi.domain import memories as domain_memories  # noqa: E402
from airi.domain import prompts as domain_prompts  # noqa: E402
from airi.domain import users as domain_users  # noqa: E402
from airi.domain.config import (  # noqa: E402
    DATE_ACTION_LABEL_MAX,
    DATE_ACTION_MAX,
    DATE_SCENE_MAX,
    DIARY_REFLECTION_MIN_INTERVAL,
)
from airi.domain.gifs import ALLOWED_GIF_TYPES, GIF_EMOTION_TITLES  # noqa: E402
from airi.domain.grounding import reply_seems_grounded  # noqa: E402
from airi.domain.llm_output import (  # noqa: E402
    RESPONSE_SCHEMA,
    extract_json_object,
    extract_reply_field,
    parse_actions,
    parse_model_output,
    parse_scene_list,
)
from airi.domain.prompts import (  # noqa: E402
    GIFT_JUDGE_PROMPT,
    GIFT_JUDGE_SCHEMA,
    SCENE_PROPOSAL_PROMPT,
    SCENE_PROPOSAL_SCHEMA,
    SEARCH_QUERY_PROMPT,
    SYSTEM_PROMPT,
)
from airi.domain.text_filters import (  # noqa: E402
    clean_reply,
    remove_repeated_previous_reply,
    strip_repetition_loop,
)
from airi.domain.texts import confession_text, gift_reaction  # noqa: E402
from airi.observability.logging_setup import (  # noqa: E402
    CORRELATION_FORMAT,
    install_correlation_format,
)
from airi.observability.trace_store import TraceStore  # noqa: E402
from airi.services.conversation import ConversationService  # noqa: E402
from airi.services.date_service import DateService  # noqa: E402
from airi.services.state import AppState  # noqa: E402

# Re-exports de compatibilidad: los tests acceden a estos nombres vía ``bot.*``.
__all__ = [
    "DATE_ACTION_LABEL_MAX",
    "DATE_ACTION_MAX",
    "DATE_SCENE_MAX",
    "RESPONSE_SCHEMA",
    "extract_reply_field",
    "gift_reaction",
    "parse_actions",
    "parse_model_output",
    "remove_repeated_previous_reply",
    "reply_seems_grounded",
    "strip_repetition_loop",
]

# ============================================================
# CONFIGURACIÓN
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
LLAMA_URL = os.getenv("LLAMA_URL", "http://127.0.0.1:8081").rstrip("/")

# [CAMBIO] Brave Search API
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

MAX_OUTPUT_TOKENS = game.env_int("MAX_OUTPUT_TOKENS", 8000)
REQUEST_TIMEOUT = game.env_int("REQUEST_TIMEOUT", 300)
MAX_WEB_RESULTS = game.env_int("MAX_WEB_RESULTS", 5)

# Espera para unir mensajes rápidos del mismo canal (debounce).
DEBOUNCE_SECONDS = game.env_float("DEBOUNCE_SECONDS", 2.5)

# NekosBest API v2.
NEKOSBEST_CONTACT = os.getenv("NEKOSBEST_CONTACT", "")
GIF_TIMEOUT = game.env_int("GIF_TIMEOUT", 20)


# Color rosa pastel del embed que enmarca el GIF.
GIF_EMBED_COLOR = discord.Color(0xFFB6D9)

# ============================================================
# CONFIGURACIÓN DEL SIMULADOR DE CITAS (USUARIO → AIRI)
# ============================================================

AFFINITY_FILE = "affinity.json"
WORLD_FILE = "world.json"

# La lógica de juego (niveles, deltas, decay, ganador, regalos) vive en game.py.
AFFINITY_LEVELS = game.AFFINITY_LEVELS
CONFESS_THRESHOLD = game.CONFESS_THRESHOLD
AFFINITY_FLOOR = game.AFFINITY_FLOOR
AFFINITY_BAR_WIDTH = game.AFFINITY_BAR_WIDTH

# Citas: duración, enfriamiento y tope de cambio durante una cita.
# La máquina de estados (crisis, última oportunidad, resolución) vive en game.py.
DATE_MAX_TURNS = game.DATE_MAX_TURNS
DATE_CRISIS_MIN_TURNS = game.DATE_CRISIS_MIN_TURNS
DATE_END_MIN_TURNS = game.DATE_END_MIN_TURNS
DATE_CRISIS_DROP = game.DATE_CRISIS_DROP
DATE_LAST_CHANCE_MAX_RECOVERY = game.DATE_LAST_CHANCE_MAX_RECOVERY
DATE_MAX_SECONDS = game.DATE_MAX_SECONDS  # Duración real máxima de una cita.
DATE_BUSY_NOTICE_COOLDOWN = game.env_int("DATE_BUSY_NOTICE_COOLDOWN", 30)  # Avisos.
DATE_COOLDOWN = game.env_int("DATE_COOLDOWN", 6 * 3600)  # Enfriamiento entre citas.
DATE_DELTA_MAX = game.env_int("DATE_DELTA_MAX", 8)  # Citas: emociones ampliadas.
DATE_SCENES = (
    "un paseo por el parque al atardecer",
    "una tarde en una cafetería acogedora",
    "una sesión de cine con palomitas",
    "un día en la playa",
    "una cena a la luz de las velas",
    "una feria con luces de colores",
)

# [CAMBIO] UI de citas: la IA propone escenas iniciales y acciones por turno,
# que se convierten en botones. Estos topes acotan cuántas genera como máximo.

# Regalos: un regalo al día por usuario.
GIFT_COOLDOWN = game.env_int("GIFT_COOLDOWN", 24 * 3600)
MAX_RECENT_GIFTS = game.env_int("MAX_RECENT_GIFTS", 3)

# Temporada: si se define OWNER_ID, solo esa persona puede reiniciarla.
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)

# Observabilidad (Fase 5): si TRACE_DIR está definido, cada turno de
# conversación se guarda en TRACE_DIR/YYYY-MM-DD/<cid>.json. Vacío = apagado.
# Los ajustes se leen con `airi.config.Settings` (AIRI_TRACE_* con fallback a
# los nombres históricos TRACE_*).
_SETTINGS = Settings.from_env()
TRACE_DIR = _SETTINGS.trace_dir
# Si es falso, la traza no incluye la respuesta cruda del modelo
# (la traza deja de ser reproducible con `python -m airi.replay`).
TRACE_KEEP_RAW = os.getenv("TRACE_KEEP_RAW", "1") not in ("0", "false", "no")
# Tamaño del ring buffer en memoria (últimos N turnos inspeccionables con
# `!debug`). AIRI_TRACE_KEEP_LAST lo configura.
TRACE_KEEP_LAST = _SETTINGS.trace_keep_last

# Almacén de eventos: ring en memoria siempre; a disco si hay TRACE_DIR.
trace_store = TraceStore(TRACE_DIR or None, TRACE_KEEP_LAST)

# ============================================================
# LIMPIEZA DE EMOJIS
# ============================================================


# ============================================================
# LOGGING Y VALIDACIÓN
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=CORRELATION_FORMAT,
)
install_correlation_format()
log = logging.getLogger("discord-local-llm")

if not TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN en el archivo .env")
if CHANNEL_ID <= 0:
    raise RuntimeError("Falta un CHANNEL_ID válido en .env")
if not BRAVE_API_KEY:
    log.warning(
        "BRAVE_API_KEY no está configurada. La búsqueda web no funcionará."
    )

# ============================================================
# BÚSQUEDA WEB (BRAVE SEARCH API)
# ============================================================



# [CAMBIO] Búsqueda async contra Brave Search API (adaptador).
async def search_web(session, query):
    client = BraveSearchClient(
        BRAVE_API_KEY, session, max_results=MAX_WEB_RESULTS
    )
    return await client.search(query)



# ============================================================
# SISTEMA DE AFINIDAD (USUARIO → AIRI)
# ============================================================


def load_affinity():
    data = game.load_json(AFFINITY_FILE, {})
    # Normaliza entradas antiguas rellenando los campos nuevos de game.py.
    for uid, entry in list(data.items()):
        if str(uid).startswith("_"):
            continue
        if not isinstance(entry, dict):
            data[uid] = game.default_entry()
            continue
        for field, default in game.default_entry().items():
            entry.setdefault(field, default)
    if data:
        log.info("Afinidad cargada: %d usuarios", len(data))
    else:
        log.info("No existe affinity.json; la afinidad empezará desde cero")
    return data


def save_affinity():
    try:
        game.save_json(AFFINITY_FILE, affinity_data)
    except OSError:
        log.exception("No se pudo guardar %s", AFFINITY_FILE)


def load_world():
    data = game.load_json(WORLD_FILE, {})
    for field, default in game.default_world().items():
        data.setdefault(field, default)
    if not isinstance(data.get("preferences"), dict):
        data["preferences"] = game.default_preferences()
    log.info(
        "Mundo cargado: ganador=%s · temporada=%s",
        data.get("winner_id"), data.get("season"),
    )
    return data


def save_world():
    try:
        game.save_json(WORLD_FILE, world_data)
    except OSError:
        log.exception("No se pudo guardar %s", WORLD_FILE)


def affinity_entry(user_id):
    key = str(user_id)
    entry = affinity_data.get(key)
    if not isinstance(entry, dict):
        entry = game.default_entry()
        affinity_data[key] = entry
    else:
        for field, default in game.default_entry().items():
            entry.setdefault(field, default)
    return entry


def apply_affinity_change(user_id, delta, now=None, delta_max=None):
    """Aplica el cambio decidido por Airi (con decay por inactividad).

    Devuelve el cambio realmente aplicado.
    """
    entry = affinity_entry(user_id)
    now = time.time() if now is None else now
    if delta_max is None:
        delta_max = game.AFFINITY_DELTA_MAX
    applied = game.apply_affinity_delta(entry, delta, now, delta_max=delta_max)
    save_affinity()
    log.info(
        "Afinidad %+d (aplicado %+d) para %s (total: %d)",
        int(delta), applied, user_id, entry["points"],
    )
    return applied


def apply_affinity_penalty(user_id, penalty, now=None):
    """Compatibilidad: un castigo es un delta negativo."""
    return apply_affinity_change(user_id, min(0, int(penalty)), now=now)


def affinity_level(points):
    """Devuelve (nivel, mínimo_actual, mínimo_siguiente_o_None)."""
    return game.affinity_level(points)


def affinity_summary(user_id):
    """Devuelve (puntos, nombre_del_nivel, texto_de_progreso)."""
    entry = affinity_data.get(str(user_id)) or {}
    return game.affinity_summary(game.entry_points(entry))


def affinity_footer_text(user_id, display_name):
    points, level_name, progress = affinity_summary(user_id)
    return f"💛 Afinidad de {display_name}: {points} pts · {level_name} · {progress}"


# Instrucción de tono asociada a cada nivel de afinidad (arco romántico).


# ============================================================
# SECCIONES DEL SYSTEM PROMPT (fachada sobre airi.domain.prompts)
# ============================================================


def affinity_prompt_section(user):
    """Devuelve la sección del system prompt según la afinidad del usuario."""
    if user is None:
        return ""
    points, level_name, _ = affinity_summary(user.id)
    return domain_prompts.affinity_prompt_section(points, level_name, user.display_name)


def relationship_status_section(user):
    """Informa a Airi de su situación sentimental (ganador único)."""
    if user is None:
        return ""
    return domain_prompts.relationship_status_section(
        world_data,
        users_data,
        user_id=user.id,
        display_name=user.display_name,
        now=time.time(),
    )


def preferences_prompt_section():
    """Le recuerda a Airi sus propios gustos (que el jugador debe descubrir)."""
    return domain_prompts.preferences_prompt_section(world_data)


def date_context_section(user_id):
    """Si el usuario está en una cita, devuelve el contexto de la escena."""
    return domain_prompts.date_context_section(active_dates.get(str(user_id)))


# Carga inicial de los archivos de afinidad y del mundo.
affinity_data = load_affinity()
world_data = load_world()


# Citas activas por usuario (persisten en dates.json). Durante una cita cada
# usuario tiene su propio historial aislado, para no manchar la conversación
# pública del canal ni mezclarse con otras personas.
DATES_FILE = "dates.json"


def load_dates():
    data = game.load_json(DATES_FILE, {})
    clean = {}
    for uid, session in (data or {}).items():
        if str(uid).startswith("_"):
            continue
        norm = game.normalize_date_session(session)
        if norm is not None:
            clean[str(uid)] = norm
    log.info("Citas activas cargadas: %d", len(clean))
    return clean


def save_dates():
    try:
        game.save_json(DATES_FILE, active_dates)
    except OSError:
        log.exception("No se pudo guardar %s", DATES_FILE)


active_dates = load_dates()


# ============================================================
# MEMORIAS DE AIRI (POR USUARIO)
# ============================================================

MEMORIES_FILE = "memories.json"


def load_memories():
    try:
        with open(MEMORIES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            log.info("Memorias cargadas: %d usuarios", len(data))
            return data
        log.warning("memories.json no contiene un objeto; se ignora")
    except FileNotFoundError:
        log.info("No existe memories.json; Airi empezará sin memorias")
    except (OSError, json.JSONDecodeError):
        log.exception("No se pudo leer %s", MEMORIES_FILE)
    return {}


def save_memories():
    tmp_path = f"{MEMORIES_FILE}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(memories_data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, MEMORIES_FILE)
    except OSError:
        log.exception("No se pudo guardar %s", MEMORIES_FILE)


def user_memories(user_id):
    key = str(user_id)
    entries = memories_data.get(key)
    if not isinstance(entries, list):
        entries = []
        memories_data[key] = entries
    return entries


def add_memory(user_id, text):
    """Guarda una memoria para el usuario. Devuelve True si se guardó."""
    saved = domain_memories.add_memory(memories_data, user_id, text, now=time.time())
    if saved:
        save_memories()
        log.info("Memoria guardada para %s: %r", user_id, text)
    else:
        log.info("Memoria descartada (vacía o duplicada) para %s: %r", user_id, text)
    return saved


def forget_memory(user_id, index=None):
    """Borra la memoria index (1-based) o todas si index es None."""
    if domain_memories.forget_memory(memories_data, user_id, index):
        save_memories()
        return True
    return False


def process_memory_action(user_id, memory_action):
    """Aplica la acción de memoria elegida por el modelo (guardar u olvidar).

    Devuelve True si se guardó una memoria nueva.
    """
    return domain_memories.process_memory_action(
        memories_data, user_id, memory_action, now=time.time()
    )


def memories_prompt_section(user):
    """Devuelve la sección del system prompt con las memorias del usuario."""
    if user is None:
        return ""
    return domain_prompts.memories_prompt_section(user_memories(user.id))


# Carga inicial del archivo de memorias.
memories_data = load_memories()


# ============================================================
# DIARIO DE AIRI (recuerdos narrativos)
# ============================================================

DIARY_FILE = "diary.json"
DIARY_VIEW_LIMIT = game.env_int("DIARY_VIEW_LIMIT", 10)  # Entradas de !diario.


def load_diary():
    data = game.load_json_list(DIARY_FILE, [])
    log.info("Diario cargado: %d entradas", len(data))
    return data


def save_diary():
    try:
        game.save_json(DIARY_FILE, diary_data)
    except OSError:
        log.exception("No se pudo guardar %s", DIARY_FILE)


def log_diary_event(kind, user, text):
    """Registra un hito en el diario de Airi. Devuelve True si se guardó."""
    if not text:
        return False
    uid = getattr(user, "id", user)
    name = user_display_name(uid) if user is not None else str(user)
    entry = game.new_diary_entry(
        kind,
        uid,
        name,
        text,
        time.time(),
        season=int(world_data.get("season", 1) or 1),
    )
    if game.add_diary_entry(diary_data, entry):
        save_diary()
        return True
    return False




def add_diary_reflection(user_id, text, now=None, min_interval=DIARY_REFLECTION_MIN_INTERVAL):
    """Guarda una reflexión de Airi en 1ª persona. Devuelve True si se guardó."""
    text = clean_reply(text).strip()[:200].strip()
    if not text:
        return False
    key = str(user_id)
    recent = [
        e for e in diary_data[-20:]
        if isinstance(e, dict) and e.get("kind") == "reflection"
        and str(e.get("user_id")) == key
    ]
    lower = text.lower()
    if any(lower == str(e.get("text", "")).lower() for e in recent):
        log.info("Reflexión duplicada descartada para %s", user_id)
        return False
    now = time.time() if now is None else now
    if recent and now - float(recent[-1].get("ts", 0.0) or 0.0) < min_interval:
        return False
    entry = game.new_diary_entry(
        "reflection",
        user_id,
        user_display_name(user_id),
        text,
        now,
        season=int(world_data.get("season", 1) or 1),
    )
    if game.add_diary_entry(diary_data, entry):
        save_diary()
        log.info("Reflexión guardada para %s: %r", user_id, text)
        return True
    return False


# Carga inicial del diario.
diary_data = load_diary()


# ============================================================
# USUARIOS CONOCIDOS DEL CANAL
# ============================================================

USERS_FILE = "users.json"


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            log.info("Usuarios conocidos cargados: %d", len(data))
            return data
        log.warning("users.json no contiene un objeto; se ignora")
    except FileNotFoundError:
        log.info("No existe users.json; Airi empezará sin usuarios conocidos")
    except (OSError, json.JSONDecodeError):
        log.exception("No se pudo leer %s", USERS_FILE)
    return {}


def save_users():
    tmp_path = f"{USERS_FILE}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(users_data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, USERS_FILE)
    except OSError:
        log.exception("No se pudo guardar %s", USERS_FILE)


def register_user_activity(user):
    """Registra actividad del usuario: nombre, primera/última vez y contador."""
    if user is None:
        return
    is_new = domain_users.register_activity(
        users_data,
        user_id=user.id,
        display_name=user.display_name,
        now=time.time(),
    )
    if is_new:
        log.info("Nuevo usuario conocido: %s (%s)", user.display_name, user.id)
        log_diary_event(
            "meet",
            user,
            f"Hoy he conocido a {user.display_name} por primera vez.",
        )
    save_users()




def diary_prompt_section(user):
    """Sección del prompt con el diario de Airi sobre la persona actual."""
    if user is None:
        return ""
    return domain_prompts.diary_prompt_section(diary_data, user.id, time.time())


def known_users_prompt_section(user):
    """Devuelve la sección del prompt con las personas del canal conocidas."""
    if user is None:
        return ""
    return domain_prompts.known_users_prompt_section(
        users_data,
        diary_data,
        world_data,
        user_id=user.id,
        display_name=user.display_name,
    )


# Carga inicial del archivo de usuarios conocidos.
users_data = load_users()


# ============================================================
# GIFS DE AIRI — NEKOSBEST API V2
# ============================================================


def nekosbest_headers():
    return NekosBestProvider(session=None, contact=NEKOSBEST_CONTACT).headers()


async def fetch_nekosbest_gif(session, gif_type):
    provider = NekosBestProvider(
        session, contact=NEKOSBEST_CONTACT, timeout=GIF_TIMEOUT
    )
    return await provider.fetch(gif_type)


async def send_selected_gif(session, channel, user, gif_type):
    if gif_type == "none" or gif_type not in ALLOWED_GIF_TYPES:
        return
    log.info("El modelo ha seleccionado el GIF: %s", gif_type)
    gif_bytes = await fetch_nekosbest_gif(session, gif_type)
    if not gif_bytes:
        log.warning("No se encontró un GIF válido en NekosBest para %s", gif_type)
        return
    try:
        filename = f"airi_{gif_type}.gif"
        embed = discord.Embed(
            title=GIF_EMOTION_TITLES.get(gif_type, "Airi"),
            color=GIF_EMBED_COLOR,
        )
        if user is not None:
            embed.set_footer(
                text=affinity_footer_text(user.id, user.display_name),
                icon_url=user.display_avatar.url,
            )
        embed.set_image(url=f"attachment://{filename}")
        file = discord.File(BytesIO(gif_bytes), filename=filename)
        await channel.send(embed=embed, file=file)
        log.info("GIF enviado correctamente: %s", gif_type)
    except discord.HTTPException:
        log.exception("Discord no pudo enviar el GIF")


# ============================================================
# RELACIONES: GANADOR ÚNICO, CONFESIÓN, CITAS Y REGALOS
# ============================================================



def user_display_name(user_id):
    entry = users_data.get(str(user_id))
    if isinstance(entry, dict) and entry.get("name"):
        return str(entry["name"])
    return "alguien"






# [CAMBIO] Airi juzga los regalos: decide su reacción y cuánto le llegan.




# Cierre de la cita según cómo haya terminado.


def win_status_line():
    winner = world_data.get("winner_id")
    if not winner:
        return "💌 Airi sigue soltera: el corazón está libre."
    return f"💍 Airi ya es novia de **{user_display_name(winner)}**."


def build_help_embed():
    return embeds.build_help_embed()


async def settle_relationship(channel, now, session=None, user=None):
    """Corona al ganador (confesión automática) y bloquea al resto."""
    winner = game.maybe_crown_winner(world_data, affinity_data, now)
    if winner:
        game.apply_winner_lock(world_data, affinity_data)
        save_world()
        save_affinity()
        await channel.send(confession_text(user_display_name(winner)))
        log_diary_event(
            "confession",
            winner,
            f"Me he dado cuenta de que quiero estar con "
            f"{user_display_name(winner)}. ¡Hoy nos hemos hecho novios!",
        )
        log.info("¡Ganador coronado! %s es ahora pareja de Airi", winner)
        if session is not None and user is not None and str(user.id) == str(winner):
            try:
                await send_selected_gif(session, channel, user, "kiss")
            except Exception:
                log.exception("No se pudo enviar el GIF de la confesión")
        return winner
    if world_data.get("winner_id"):
        game.apply_winner_lock(world_data, affinity_data)
        save_affinity()
    return None


async def process_date_turn(
    channel,
    user,
    session,
    *,
    text,
    delta,
    points,
    date_decision,
    date_reason,
    last_chance_result,
    now,
):
    """Avanza un turno de la cita, comunica el resultado y cierra si toca.

    Devuelve el evento del turno (ver game.step_date). La lógica vive en
    `airi.services.date_service.DateService`; aquí se inyecta el estado y
    el notificador de Discord.
    """
    service = DateService(
        state=build_app_state(), notifier=DiscordNotifier(channel)
    )
    return await service.process_turn(
        session,
        user=user,
        text=text,
        delta=delta,
        points=points,
        date_decision=date_decision,
        date_reason=date_reason,
        last_chance_result=last_chance_result,
        now=now,
    )


def _finish_date(user_id, session, event, *, now):
    """Cierra la cita: registra el resultado en el diario y la elimina."""
    DateService(state=build_app_state()).finish_date(user_id, session, event, now=now)


# ============================================================
# CITAS EXCLUSIVAS: AVISOS Y EXPIRACIÓN
# ============================================================
# Mientras Airi está en una cita, los demás no pueden hablarle: reciben un
# aviso de sistema con el nombre de su acompañante y el tiempo restante.
# Una cita dura como máximo DATE_MAX_SECONDS para no bloquear el canal.

_busy_notice_at = {}  # uid -> timestamp del último aviso enviado (anti-spam).


def expire_stale_dates(now=None):
    """Cierra las citas que superaron su duración máxima.

    Devuelve la lista de uids cerrados. Pensado para llamarse al principio de
    `on_message`, de modo que una cita abandonada nunca bloquee el canal.
    """
    if now is None:
        now = time.time()
    expired = []
    for uid, session in list(active_dates.items()):
        if game.date_expired(session, now):
            expired.append(uid)
            _finish_date(uid, session, "ending", now=now)
    if expired:
        log.info("Citas caducadas por tiempo: %s", ", ".join(expired))
    return expired


def busy_date_owner(exclude_id=None):
    """Devuelve (uid, session) de la cita activa de OTRO usuario, o (None, None).

    Antes de buscar, expira las citas caducadas para no bloquear el canal.
    """
    expire_stale_dates()
    exclude = None if exclude_id is None else str(exclude_id)
    for uid, session in active_dates.items():
        if session.get("state") == "closed":
            continue
        if exclude is not None and str(uid) == exclude:
            continue
        return str(uid), session
    return None, None


def date_busy_text(uid, session, now=None):
    """Mensaje de sistema que anuncia que Airi está en una cita con alguien."""
    if now is None:
        now = time.time()
    name = user_display_name(uid)
    seconds = game.date_seconds_left(session, now)
    if seconds < 60:
        when = "en menos de 1 min"
    else:
        when = f"en ~{int((seconds + 59) // 60)} min"
    return (
        f"🌸 **Airi está en una cita ahora mismo.** Está con **{name}**. "
        f"Su cita termina {when}. Vuelve un poco más tarde para hablar con ella~"
    )


async def notify_busy(channel, user, now=None):
    """Avisa de que Airi está ocupada, respetando un cooldown por usuario."""
    if now is None:
        now = time.time()
    uid = user.id
    last = _busy_notice_at.get(uid, 0.0)
    if now - last < DATE_BUSY_NOTICE_COOLDOWN:
        return
    _busy_notice_at[uid] = now
    owner_id, session = busy_date_owner(exclude_id=uid)
    if owner_id is None:
        return
    await channel.send(date_busy_text(owner_id, session, now))


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
histories = {}
pending_messages = {}
message_seq = {}
generation_lock = asyncio.Lock()

# ============================================================
# GENERACIÓN CON LLAMA.CPP
# ============================================================






def fallback_scenes():
    """Escenas de reserva si el modelo no responde bien."""
    count = min(3, len(DATE_SCENES))
    return random.sample(list(DATE_SCENES), k=count)


async def propose_scenes(session, user=None):
    """Pide a la IA 3-4 planes de cita; si falla, usa escenas de reserva."""
    who = user_display_name(user.id) if user is not None else "esa persona"
    payload = {
        "messages": [
            {"role": "system", "content": SCENE_PROPOSAL_PROMPT},
            {"role": "user", "content": f"Propón planes de cita con {who}."},
        ],
        "max_tokens": 300,
        "temperature": 0.9,
        "stream": False,
        "json_schema": SCENE_PROPOSAL_SCHEMA,
    }
    try:
        data = await request_llama(session, payload)
        choices = data.get("choices") or []
        raw = (choices[0].get("message") or {}).get("content") if choices else None
        parsed = extract_json_object(raw) if isinstance(raw, str) else None
        scenes = parse_scene_list(parsed.get("scenes")) if isinstance(parsed, dict) else []
        if scenes:
            return scenes
        log.warning("El modelo no devolvió escenas válidas; uso escenas de reserva")
    except Exception:
        log.exception("Error proponiendo escenas; uso escenas de reserva")
    return fallback_scenes()


async def request_llama(session, payload):
    # [CAMBIO] Diagnóstico temporal: revisar si llama-server acepta json_schema.
    log.info("JSON Schema enviado: %r", payload.get("json_schema"))
    log.info(
        "Mensajes enviados al modelo:\n%s",
        json.dumps(payload.get("messages", []), ensure_ascii=False, indent=2),
    )
    client = HttpLlmClient(
        LLAMA_URL,
        session,
        timeout=REQUEST_TIMEOUT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    return await client.post(payload)


async def build_search_query(session, user_message):
    payload = {
        "messages": [
            {"role": "system", "content": SEARCH_QUERY_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 64,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        data = await request_llama(session, payload)
        choices = data.get("choices") or []
        if not choices:
            return user_message
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        query = content.strip().strip('"').strip("'").strip()
        query = query.splitlines()[0].strip()
        query = query[:300]
        return query or user_message
    except Exception:
        log.exception(
            "No se pudo reformular la consulta; se usará el mensaje original"
        )
        return user_message


async def judge_gift(session, item, user, recent_gifts=None):
    """Airi juzga un regalo: su reacción y cuánta afinidad le llega.

    Devuelve (reply, delta, event) o None si el modelo falla. `delta` ya viene
    con el candado aplicado (0 si Airi no declara motivo).
    """
    affinity_desc = affinity_prompt_section(user)
    relationship_desc = relationship_status_section(user)
    prefs_desc = preferences_prompt_section()
    recent = [str(g) for g in (recent_gifts or [])]
    recent_desc = ", ".join(recent) if recent else "(ninguno)"
    system_prompt = (
        SYSTEM_PROMPT
        + affinity_desc
        + relationship_desc
        + prefs_desc
        + GIFT_JUDGE_PROMPT
    )
    if user is not None:
        sender = user_display_name(user.id)
    else:
        sender = "Alguien"
    user_message = (
        f"{sender} te acaba de regalar «{item}». "
        f"Regalos recientes que ya te ha hecho: {recent_desc}. "
        "Reacciona como Airi y decide, con tu criterio, si el regalo mueve tu "
        "afinidad y cuánto."
    )
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.7,
        "stream": False,
        "json_schema": GIFT_JUDGE_SCHEMA,
    }
    try:
        data = await request_llama(session, payload)
    except Exception:
        log.exception("No se pudo consultar a Airi sobre el regalo")
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    parsed = extract_json_object(content) if isinstance(content, str) else None
    if not isinstance(parsed, dict):
        return None

    reply_raw = parsed.get("reply")
    reply = clean_reply(reply_raw) if isinstance(reply_raw, str) else ""
    delta_raw = parsed.get("affinity_delta", 0)
    if isinstance(delta_raw, bool) or not isinstance(delta_raw, (int, float)):
        delta = 0
    else:
        delta = int(delta_raw)
    delta = game.clamp_delta(delta)
    event_raw = parsed.get("affinity_event", "none")
    if isinstance(event_raw, str):
        event = event_raw.strip()[:300]
    else:
        event = "none"
    if event.lower() in ("", "none", "ninguno", "null"):
        delta = 0
    log.info("Airi juzga el regalo «%s»: delta %+d (motivo: %s)", item, delta, event)
    return reply, delta, event


# ============================================================
# TURNO DE CONVERSACIÓN (VIVE EN airi.discord_bot.turn)
# ============================================================


def build_app_state():
    """Construye el estado inyectable apuntando a los globales actuales.

    Los callbacks resuelven los globales en tiempo de llamada, de modo que
    (p. ej. en tests) se pueden monkeypatchar `save_*` y `log_diary_event`.
    """
    return AppState(
        affinity=affinity_data,
        world=world_data,
        dates=active_dates,
        memories=memories_data,
        diary=diary_data,
        users=users_data,
        histories=histories,
        save_affinity=lambda: save_affinity(),
        save_world=lambda: save_world(),
        save_dates=lambda: save_dates(),
        save_memories=lambda: save_memories(),
        save_diary=lambda: save_diary(),
        save_users=lambda: save_users(),
        log_diary_event=lambda kind, user, text: log_diary_event(kind, user, text),
        apply_affinity_fn=lambda uid, delta, now=None, delta_max=None: apply_affinity_change(
            uid, delta, now=now, delta_max=delta_max
        ),
        traces=trace_store,
    )


def build_conversation_service(session, state, channel):
    """Servicio con los adaptadores reales (llama.cpp, Brave, NekosBest)."""
    return ConversationService(
        llm=HttpLlmClient(
            LLAMA_URL,
            session,
            timeout=REQUEST_TIMEOUT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
        state=state,
        search=BraveSearchClient(BRAVE_API_KEY, session, max_results=MAX_WEB_RESULTS),
        gifs=NekosBestProvider(session, contact=NEKOSBEST_CONTACT, timeout=GIF_TIMEOUT),
        notifier=DiscordNotifier(channel),
        clock=time.time,
        date_delta_max=DATE_DELTA_MAX,
    )


# ============================================================
# COMPOSICIÓN: contexto, comandos y cliente de Discord
# ============================================================


def build_ctx(channel):
    """Contexto de la capa Discord para un mensaje de este canal."""
    ctx = BotContext(
        channel_id=channel.id,
        state=build_app_state(),
        lock=generation_lock,
        owner_id=OWNER_ID,
        debounce_seconds=DEBOUNCE_SECONDS,
        request_timeout=REQUEST_TIMEOUT,
        llama_url=LLAMA_URL,
        trace_dir=TRACE_DIR,
        trace_keep_raw=TRACE_KEEP_RAW,
        build_service=build_conversation_service,
        settle_relationship=settle_relationship,
        process_date_turn=process_date_turn,
        add_diary_reflection=add_diary_reflection,
        judge_gift=judge_gift,
        propose_scenes=propose_scenes,
        busy_date_owner=busy_date_owner,
        notify_busy=notify_busy,
        date_busy_text=date_busy_text,
        expire_stale_dates=expire_stale_dates,
        affinity_footer=lambda user: affinity_footer_text(
            user.id, user.display_name
        ),
        log_diary_event=log_diary_event,
    )
    ctx.handle_scene_choice = (
        lambda interaction, payload: discord_turn.handle_scene_choice(
            ctx, interaction, payload
        )
    )
    ctx.handle_date_action = (
        lambda interaction, payload: discord_turn.handle_date_action(
            ctx, interaction, payload
        )
    )
    return ctx


registry = build_registry()
client = create_client(build_ctx=build_ctx, registry=registry, channel_id=CHANNEL_ID)


def log_startup():
    log.info("API local: %s", LLAMA_URL)
    log.info("Búsqueda web: Brave Search API")
    log.info("Proveedor de GIFs: NekosBest API v2")
    log.info(
        "Simulador de citas activo: confesión al llegar a %d (temporada %s)",
        game.CONFESS_THRESHOLD,
        world_data.get("season"),
    )
    if world_data.get("winner_id"):
        log.info("Airi ya tiene pareja: %s", world_data.get("winner_id"))
    if OWNER_ID:
        log.info("Dueño autorizado para reiniciar temporada: %s", OWNER_ID)
    if not NEKOSBEST_CONTACT:
        log.warning(
            "Define NEKOSBEST_CONTACT en .env con un correo o URL de contacto."
        )
    if not BRAVE_API_KEY:
        log.warning("Define BRAVE_API_KEY en .env para habilitar la búsqueda web.")


if __name__ == "__main__":
    log_startup()
    client.run(TOKEN)
