"""Comando !usuarios."""

import time

from airi.discord_bot import embeds


async def handle(ctx, message):
    rows = []
    for _uid, entry in ctx.state.users.items():
        if not isinstance(entry, dict):
            continue
        try:
            last = time.strftime(
                "%d/%m/%Y %H:%M",
                time.localtime(float(entry.get("last_seen", 0.0))),
            )
        except (TypeError, ValueError, OSError):
            last = "desconocida"
        rows.append(
            f"**{entry.get('name', '??')}** — "
            f"{int(entry.get('interactions', 0) or 0)} interacciones · "
            f"última vez: {last}"
        )
    description = "\n".join(rows) if rows else (
        "Todavía no conozco a nadie por aquí..."
    )
    await message.channel.send(embed=embeds.users_embed(description))
