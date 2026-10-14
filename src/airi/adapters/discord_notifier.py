"""Notificador que envía mensajes a un canal de Discord."""

from __future__ import annotations


class DiscordNotifier:
    """Implementa `airi.ports.notifier.Notifier` sobre `discord.abc.Messageable`."""

    def __init__(self, channel):
        self.channel = channel

    async def send(self, content):
        await self.channel.send(content)
