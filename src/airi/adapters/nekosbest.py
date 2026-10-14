"""Proveedor de GIFs de NekosBest API v2."""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse

import aiohttp

from airi.domain.gifs import GIF_CATEGORIES

log = logging.getLogger(__name__)

NEKOSBEST_URL = "https://nekos.best/api/v2"


class NekosBestProvider:
    """Implementa `airi.ports.gif_provider.GifProvider`."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        base_url: str = NEKOSBEST_URL,
        contact: str = "",
        timeout: int = 20,
        categories: dict | None = None,
    ):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.contact = (contact or "").strip()
        self.timeout = timeout
        self.categories = categories if categories is not None else GIF_CATEGORIES

    def headers(self):
        if self.contact:
            user_agent = f"AiriDiscordBot ({self.contact})"
        else:
            user_agent = "AiriDiscordBot (local development; set NEKOSBEST_CONTACT in .env)"
        return {"User-Agent": user_agent}

    async def fetch(self, kind):
        categories = self.categories.get(kind, [])
        headers = self.headers()

        for category in categories:
            try:
                async with self.session.get(
                    f"{self.base_url}/{category}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        body = (await response.text())[:200]
                        log.warning(
                            "NekosBest HTTP %s para %s: %s",
                            response.status, category, body,
                        )
                        continue
                    try:
                        data = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, json.JSONDecodeError):
                        log.warning("NekosBest devolvió JSON inválido para %s", category)
                        continue

                results = data.get("results", []) if isinstance(data, dict) else []
                if not results or not isinstance(results, list):
                    log.warning("NekosBest no devolvió resultados para %s", category)
                    continue

                gif_url = results[0].get("url") if isinstance(results[0], dict) else None
                if not isinstance(gif_url, str):
                    continue
                parsed_url = urlparse(gif_url)
                if (
                    parsed_url.scheme != "https"
                    or parsed_url.hostname != "nekos.best"
                    or not parsed_url.path.lower().endswith(".gif")
                ):
                    log.warning("URL de GIF no válida recibida: %r", gif_url)
                    continue

                async with self.session.get(
                    gif_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as file_response:
                    if file_response.status != 200:
                        log.warning(
                            "Descarga del GIF falló con HTTP %s", file_response.status
                        )
                        continue
                    gif_bytes = await file_response.read()
                    if gif_bytes.startswith((b"GIF87a", b"GIF89a")):
                        log.info("GIF obtenido de NekosBest: %s", category)
                        return gif_bytes
                    log.warning("El archivo de %s no es un GIF válido", category)

            except asyncio.TimeoutError:
                log.warning("Tiempo agotado consultando NekosBest: %s", category)
            except aiohttp.ClientError:
                log.exception("Error HTTP consultando NekosBest: %s", category)
            except Exception:
                log.exception("Error inesperado con NekosBest: %s", category)

        return None
