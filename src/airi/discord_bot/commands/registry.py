"""Registro de comandos de texto (`!comando`).

Cada comando es un handler `async def handle(ctx, message) -> None`. El
registro distingue comandos exactos (`!afinidad`) de comandos con prefijo
(`!regalo <item>`, `!olvidar <n>`); los prefijos se comprueban primero y por
orden de longitud descendente para que `!olvidar` no capture `!olvidar-todo`.
"""

from __future__ import annotations


class CommandRegistry:
    def __init__(self):
        self._exact = {}
        self._prefix = []

    def exact(self, *names):
        def deco(fn):
            for name in names:
                self._exact[name] = fn
            return fn

        return deco

    def prefix(self, *names):
        def deco(fn):
            for name in names:
                self._prefix.append((name, fn))
            self._prefix.sort(key=lambda item: len(item[0]), reverse=True)
            return fn

        return deco

    def match(self, content):
        """Devuelve el handler para `content`, o None si no es un comando."""
        lowered = content.lower()
        for name, handler in self._prefix:
            if lowered.startswith(name):
                return handler
        return self._exact.get(lowered)
