"""Comando !diario."""

import time

from airi.discord_bot import embeds
from airi.domain.config import DIARY_VIEW_LIMIT
from airi.domain.diary import format_relative_time, recent_diary


async def handle(ctx, message):
    now = time.time()
    entries = recent_diary(ctx.state.diary, limit=DIARY_VIEW_LIMIT)
    if entries:
        listing = "\n".join(
            f"**{format_relative_time(e.get('ts'), now)}** · {e.get('text', '')}"
            for e in entries
        )[:4000]
    else:
        listing = "El diario de Airi todavía está en blanco~"
    await message.channel.send(embed=embeds.diary_embed(listing))
