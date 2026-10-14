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
