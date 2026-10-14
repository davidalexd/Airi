"""Comando !ayuda / !help."""

from airi.discord_bot import embeds


async def handle(ctx, message):
    await message.channel.send(embed=embeds.build_help_embed())
