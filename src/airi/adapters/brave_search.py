"""Búsqueda web con Brave Search API."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchClient:
    """Implementa `airi.ports.web_search.WebSearchClient`."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        max_results: int = 5,
        url: str = BRAVE_SEARCH_URL,
        timeout: int = 15,
    ):
        self.api_key = api_key or ""
        self.session = session
        self.max_results = max_results
        self.url = url
        self.timeout = timeout

    async def search(self, query):
        if not self.api_key:
            log.error("BRAVE_API_KEY no configurada; no se puede buscar")
            return None

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": self.max_results,
            "safesearch": "moderate",
            "text_decorations": "false",
            "extra_snippets": "true",
        }

        try:
            async with self.session.get(
                self.url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                log.info("Brave HTTP %s para query %r", response.status, query)
                if response.status == 401:
                    log.error("Brave: API key inválida o no autorizada (401)")
                    return None
                if response.status == 429:
                    log.warning("Brave: rate limit alcanzado (429)")
                    return None
                if response.status != 200:
                    body = (await response.text())[:300]
                    log.warning("Brave HTTP %s: %s", response.status, body)
                    return None
                data = await response.json()
        except asyncio.TimeoutError:
            log.warning("Timeout consultando Brave Search")
            return None
        except aiohttp.ClientError:
            log.exception("Error HTTP consultando Brave Search")
            return None
        except Exception:
            log.exception("Error inesperado con Brave Search")
            return None

        web_results = (data.get("web") or {}).get("results") or []
        log.info("Brave devolvió %d resultados", len(web_results))
        if not web_results:
            return None

        formatted = []
        for index, result in enumerate(web_results, start=1):
            title = (result.get("title") or "").strip()
            url = (result.get("url") or "").strip()
            description = (result.get("description") or "").strip()
            extra = result.get("extra_snippets") or []
            if extra:
                description += " " + " ".join(
                    s.strip() for s in extra if isinstance(s, str)
                )

            if not url or not (title or description):
                continue

            formatted.append(
                f"Fuente {index}: {title or 'Sin título'}\n"
                f"URL: {url}\n"
                f"Resumen: {description or 'Sin resumen disponible'}"
            )

        if not formatted:
            log.warning("Brave devolvió resultados pero todos fueron descartados")
            return None

        log.info(
            "Contexto web listo (%d fuentes, %d caracteres). Primeras 300:\\n%s",
            len(formatted),
            len("\n\n".join(formatted)),
            "\n\n".join(formatted)[:300],
        )
        return "\n\n".join(formatted)
