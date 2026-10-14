"""Cliente de Discord: solo enruta eventos hacia comandos y turnos.

`create_client` recibe un `build_ctx(channel) -> BotContext`, un
`CommandRegistry` y el id del canal autorizado. `on_message` se limita a:
autorizar → expirar citas → despachar comando → comprobar cita activa →
debounce → delegar el turno a `airi.discord_bot.turn`.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from airi.discord_bot import turn

log = logging.getLogger(__name__)


class _Debouncer:
    """Une mensajes rápidos del MISMO (canal, autor)."""

    def __init__(self):
        self.pending = {}
        self.seq = {}

    def next_seq(self, key):
        value = self.seq.get(key, 0) + 1
        self.seq[key] = value
        return value

    def current_seq(self, key):
        return self.seq.get(key)

    def add(self, key, item):
        self.pending.setdefault(key, []).append(item)

    def pop(self, key):
        self.seq.pop(key, None)
        return self.pending.pop(key, [])

    def reset(self, channel_id, author_id):
        key = (channel_id, author_id)
        self.pending.pop(key, None)
        self.seq.pop(key, None)


def create_client(*, build_ctx, registry, channel_id):
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    debounce = _Debouncer()

    def _reset_conversation(ctx, ch_id, author_id):
        debounce.reset(ch_id, author_id)
        ctx.state.histories.pop(ch_id, None)

    @client.event
    async def on_ready():
        log.info("Bot conectado como %s", client.user)
        log.info("Canal autorizado: %s", channel_id)

    @client.event
    async def on_message(message):
        if message.author.bot or message.channel.id != channel_id:
            return
        content = message.content.strip()
        if not content:
            return

        ctx = build_ctx(message.channel)
        ctx.reset_conversation = (
            lambda ch_id, author_id: _reset_conversation(ctx, ch_id, author_id)
        )

        if ctx.expire_stale_dates():
            await message.channel.send(
                "🌙 «Vaya, se me ha ido el tiempo... la cita termina aquí. "
                "*se despide con la mano*»"
            )

        handler = registry.match(content)
        if handler is not None:
            await handler(ctx, message)
            return

        owner_id, _owner_session = ctx.busy_date_owner(exclude_id=message.author.id)
        if owner_id is not None:
            await ctx.notify_busy(message.channel, message.author)
            return

        key = (message.channel.id, message.author.id)
        seq = debounce.next_seq(key)
        debounce.add(key, (message.author, content))
        await asyncio.sleep(ctx.debounce_seconds)
        if debounce.current_seq(key) != seq:
            return
        merged = debounce.pop(key)
        if not merged:
            return
        await turn.run_user_turn(
            ctx, message.channel, message.author, merged, reply_target=message
        )

    return client


def run_bot(argv=None):
    """Inicia el bot de Discord.

    Construye la aplicación modular hexagonal y ejecuta el cliente de Discord.
    """
    import asyncio
    import json
    import logging
    import os
    import time
    from io import BytesIO

    from dotenv import load_dotenv

    from airi.adapters.brave_search import BraveSearchClient
    from airi.adapters.discord_notifier import DiscordNotifier
    from airi.adapters.http_llm import HttpLlmClient
    from airi.adapters.nekosbest import NekosBestProvider
    from airi.config import Settings
    from airi.discord_bot import embeds
    from airi.discord_bot import turn as discord_turn
    from airi.discord_bot.commands import build_registry
    from airi.discord_bot.context import BotContext
    from airi.domain.affinity import (
        apply_affinity_delta,
        apply_winner_lock,
        maybe_crown_winner,
    )
    from airi.domain.gifs import ALLOWED_GIF_TYPES, GIF_EMOTION_TITLES
    from airi.domain.texts import confession_text
    from airi.logging_setup import install_correlation_format
    from airi.observability.trace_store import TraceStore
    from airi.services.conversation import ConversationService
    from airi.services.state import AppState

    load_dotenv()

    # Configuración
    TOKEN = os.getenv("DISCORD_TOKEN")
    CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
    LLAMA_URL = os.getenv("LLAMA_URL", "http://127.0.0.1:8081").rstrip("/")
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
    NEKOSBEST_CONTACT = os.getenv("NEKOSBEST_CONTACT", "")
    GIF_TIMEOUT = int(os.getenv("GIF_TIMEOUT", "20"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))
    MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))
    MAX_WEB_RESULTS = int(os.getenv("MAX_WEB_RESULTS", "5"))
    DATE_DELTA_MAX = int(os.getenv("DATE_DELTA_MAX", "7"))
    DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "3"))
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
    CONFESS_THRESHOLD = int(os.getenv("CONFESS_THRESHOLD", "100"))

    log = logging.getLogger(__name__)

    # Datos globales
    generation_lock = asyncio.Lock()
    world_data_dir = os.getenv("DATA_DIR", "data")
    world_file = os.path.join(world_data_dir, "world.json")
    affinity_file = os.path.join(world_data_dir, "affinity.json")
    dates_file = os.path.join(world_data_dir, "dates.json")
    diary_file = os.path.join(world_data_dir, "diary.json")
    memories_file = os.path.join(world_data_dir, "memories.json")
    users_file = os.path.join(world_data_dir, "users.json")

    # Cargar datos
    with open(world_file, "r", encoding="utf-8") as f:
        world_data = json.load(f)
    with open(affinity_file, "r", encoding="utf-8") as f:
        affinity_data = json.load(f)
    with open(dates_file, "r", encoding="utf-8") as f:
        dates_data = json.load(f)
    with open(diary_file, "r", encoding="utf-8") as f:
        diary_data = json.load(f)
    with open(memories_file, "r", encoding="utf-8") as f:
        memories_data = json.load(f)
    with open(users_file, "r", encoding="utf-8") as f:
        users_data = json.load(f)

    # Persistencia
    def save_world():
        with open(world_file, "w", encoding="utf-8") as f:
            json.dump(world_data, f, indent=2)

    def save_affinity():
        with open(affinity_file, "w", encoding="utf-8") as f:
            json.dump(affinity_data, f, indent=2)

    def save_dates():
        with open(dates_file, "w", encoding="utf-8") as f:
            json.dump(dates_data, f, indent=2)

    def save_diary():
        with open(diary_file, "w", encoding="utf-8") as f:
            json.dump(diary_data, f, indent=2)

    def save_memories():
        with open(memories_file, "w", encoding="utf-8") as f:
            json.dump(memories_data, f, indent=2)

    def save_users():
        with open(users_file, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=2)

    # Settings
    settings = Settings.from_env()
    trace_store = TraceStore(settings.trace_dir, settings.trace_keep_last)
    install_correlation_format()

    # Estado
    state = AppState(
        world=world_data,
        affinity=affinity_data,
        dates=dates_data,
        diary=diary_data,
        memories=memories_data,
        users=users_data,
        save_world=save_world,
        save_affinity=save_affinity,
        save_dates=save_dates,
        save_diary=save_diary,
        save_memories=save_memories,
        save_users=save_users,
        log_diary_event=lambda kind, user, text: log.info("%s %s: %s", kind, user, text),
        apply_affinity_fn=lambda uid, delta, now=None, delta_max=None: (
            lambda entry: apply_affinity_delta(entry, delta, now or time.time(), delta_max)
        )(state.affinity_entry(uid)),
        traces=trace_store,
    )

    def build_app_state():
        return state

    def build_conversation_service(session, state, channel):
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

    def build_ctx(channel):
        ctx = BotContext(
            channel_id=channel.id,
            state=build_app_state(),
            lock=generation_lock,
            owner_id=OWNER_ID,
            debounce_seconds=DEBOUNCE_SECONDS,
            request_timeout=REQUEST_TIMEOUT,
            llama_url=LLAMA_URL,
            trace_dir=settings.trace_dir,
            trace_keep_raw=True,
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
            log_diary_event=lambda kind, user, text: log.info("%s %s: %s", kind, user, text),
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

    def apply_affinity_change(uid, delta, *, now=None, delta_max=None):
        return state.apply_affinity(uid, delta, now=now, delta_max=delta_max)

    def log_diary_event(kind, user, text):
        log.info("%s %s: %s", kind, user, text)

    async def send_selected_gif(session, channel, user, gif_type):
        """Envía un GIF de NekosBest (usado para la confesión)."""
        if gif_type == "none" or gif_type not in ALLOWED_GIF_TYPES:
            return
        log.info("El modelo ha seleccionado el GIF: %s", gif_type)
        provider = NekosBestProvider(
            session, contact=NEKOSBEST_CONTACT, timeout=GIF_TIMEOUT
        )
        gif_bytes = await provider.fetch(gif_type)
        if not gif_bytes:
            log.warning("No se encontró un GIF válido en NekosBest para %s", gif_type)
            return
        try:
            filename = f"airi_{gif_type}.gif"
            embed = discord.Embed(
                title=GIF_EMOTION_TITLES.get(gif_type, "Airi"),
                color=embeds.GIF_EMBED_COLOR,
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

    def user_display_name(user_id):
        entry = users_data.get(str(user_id))
        if isinstance(entry, dict) and entry.get("name"):
            return str(entry["name"])
        return "alguien"

    async def settle_relationship(channel, now, session=None, user=None):
        """Corona al ganador (confesión automática) y bloquea al resto."""
        winner = maybe_crown_winner(world_data, affinity_data, now)
        if winner:
            apply_winner_lock(world_data, affinity_data)
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
            apply_winner_lock(world_data, affinity_data)
            save_affinity()
        return None

    def process_date_turn(date_session, user, decision, reason):
        if decision == "crisis":
            pass
        elif decision == "end":
            pass
        save_dates()

    def add_diary_reflection(user_id, text, now):
        save_diary()

    def judge_gift(user_id, gift_type, now):
        pass

    def propose_scenes(user_id, scene_list, now):
        pass

    def busy_date_owner(exclude_id=None):
        return None, None

    def notify_busy(channel, user):
        pass

    def date_busy_text():
        return ""

    def expire_stale_dates():
        return False

    def affinity_footer_text(user_id, display_name):
        return ""

    client = create_client(build_ctx=build_ctx, registry=registry, channel_id=CHANNEL_ID)

    def log_startup():
        log.info("API local: %s", LLAMA_URL)
        log.info("Búsqueda web: Brave Search API")
        log.info("Proveedor de GIFs: NekosBest API v2")
        log.info(
            "Simulador de citas activo: confesión al llegar a %d (temporada %s)",
            CONFESS_THRESHOLD,
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

    log_startup()
    client.run(TOKEN)
