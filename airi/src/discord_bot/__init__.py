"""Capa Discord fina de Airi: eventos, comandos, vistas y traducción.

No contiene lógica de juego; recibe estado y servicios a través de un
`BotContext` construido por el composition root (`bot.py`).
"""

from airi.discord_bot.client import create_client
from airi.discord_bot.context import BotContext

__all__ = ["BotContext", "create_client"]
