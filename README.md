# Airi — Discord bot con LLM local (arquitectura hexagonal)

## Estructura

```text
.
├── bot.py              # Capa Discord fina: eventos, comandos, traducción a servicios
├── game.py             # Shim de compatibilidad → airi.domain.*
├── date_view.py        # Vistas/botones de cita (Discord)
├── pyproject.toml      # Configuración (pytest pythonpath ".", "src", ruff)
├── src/airi/
│   ├── domain/         # LÓGICA PURA (sin I/O, sin Discord, sin HTTP)
│   │   ├── config.py       # env readers + constantes (afinidad, citas, diario)
│   │   ├── affinity.py     # niveles, deltas, decay, clamp, coronación, ranking
│   │   ├── dates.py        # máquina de estados de la cita
│   │   ├── gifts.py        # catálogo y efectos de regalos
│   │   ├── diary.py        # entradas, consultas, formato relativo
│   │   ├── memories.py     # alta/olvido de memorias sobre listas
│   │   ├── users.py        # registro de actividad (puro)
│   │   ├── gifs.py         # tipos, categorías y títulos de GIFs
│   │   ├── llm_output.py   # ModelOutput + parseo tolerante del LLM
│   │   ├── text_filters.py # clean_reply, repeticiones del modelo
│   │   ├── grounding.py    # filtro anti-alucinación
│   │   ├── prompts.py      # prompts + build_system_prompt(ctx)
│   │   ├── texts.py        # textos narrativos (cita, confesión, regalos)
│   │   └── web.py          # detección de mensajes que piden búsqueda web
│   ├── ports/          # Protocol (LLMClient, WebSearchClient, GifProvider,
│   │                   # Notifier, Repository)
│   ├── adapters/       # http_llm (llama.cpp), brave_search, nekosbest,
│   │                   # json_repo + JSONRepository, discord_notifier
│   └── services/       # Orquestación (solo usan ports)
│       ├── state.py        # AppState: datos + callbacks de persistencia
│       ├── conversation.py # ConversationService.run_turn(...) → TurnResult
│       └── date_service.py # DateService: turno/cierre de citas
│   ├── config.py       # Settings: ajustes de entorno (AIRI_TRACE_*), stdlib
│   ├── observability/  # Trazas por turno + logging con correlation_id
│   │   ├── trace.py        # TurnEvent (alias TurnTrace): campos + snapshots
│   │   ├── trace_store.py  # TraceStore: ring en memoria + disco atómico
│   │   ├── instrumentation.py # turn_event/traced: eventos fuera de run_turn
│   │   └── logging_setup.py# CorrelationIdFilter + formato [cid=...]
│   ├── trace.py        # CLI: `python -m airi.trace last/show`
│   ├── replay.py       # `python -m airi.replay <traza>.json`
│   └── discord_bot/    # Capa Discord fina (Fase 4)
│       ├── client.py       # on_message: enrutar, debounce, delegar
│       ├── context.py      # BotContext inyectado (+ trace_dir, last_traces)
│       ├── turn.py         # run_user_turn: servicio → embeds/GIFs/vistas
│       ├── embeds.py       # embeds y textos de ayuda
│       ├── commands/       # un módulo por comando + registry
│       └── views/          # botones de cita
└── tests/
    ├── unit/                   # unidades puras (sin red ni Discord)
    │   ├── test_events.py      # TurnEvent: serialización, aliases v1, recortes
    │   ├── test_trace_store.py # ring, disco atómico y fallos best-effort
    │   └── test_conversation_instrumented.py  # el evento sobrevive a errores
    ├── integration/            # ConversationService + citas + test_replay.py
    ├── test_game.py, test_bot_integration.py  # herencia (siguen verdes)
    ├── test_text_filters.py, test_grounding.py,
    │   test_llm_output_parse.py, test_memories_domain.py  # caracterización
    ├── test_observability.py  # instrumentación de run_turn + goldens de replay
    ├── test_logging_setup.py  # formato [cid=...] + filtro anti-KeyError
    ├── test_debug_command.py  # !debug ultimo/id/errores/clear + turno/trace
    ├── test_instrumentation.py  # turn_event/traced (gift/command/scene_select)
    ├── test_config.py         # Settings: AIRI_TRACE_* + fallback TRACE_*
    ├── fakes/          # FakeLLM, FakeSearch, FakeGif, FakeNotifier, FakeUser,
    │                   # InMemoryRepository + make_state()
    └── fixtures/       # traces/example_bug.json + transcripts/*.jsonl
```

## Reglas

- `domain/` no importa `discord`, `aiohttp` ni hace I/O de ficheros.
- Los servicios orquestan con `ports`; nunca con `adapters` directamente.
- `bot.py` construye `AppState` desde sus globales (`build_app_state()`) y
  los servicios vía `build_conversation_service()` + `DateService`.
- Los tests usan `asyncio.run()` (sin dependencias extra).

## Ejecutar tests

```bash
.venv/bin/python -m pytest tests/
```

## Ejecutar el bot

```bash
.venv/bin/python bot.py   # necesita .env con DISCORD_TOKEN y CHANNEL_ID
```

## Debugging y trazas

Cada turno genera un `TurnEvent` con un `correlation_id` (12 hex) que viaja en
los logs (`[cid=...]`) y en la traza. El evento guarda los **snapshots del
estado previos al turno** (afinidad, mundo, memorias, diario y cita), el prompt
enviado, la respuesta cruda del modelo, el parseo, la afinidad y las citas, de
modo que el turno se puede reproducir sin Discord ni red.

`TraceStore` mantiene siempre un ring en memoria (los últimos `N` turnos) y, si
hay directorio, persiste cada evento de forma atómica (`<dir>/<día>/<cid>.json`).
Ninguna operación lanza excepciones: un fallo de disco se registra y el turno
continúa.

Además de los turnos de conversación, se instrumentan los demás flujos que no
pasan por `run_turn`: los comandos (`kind="command"`), `!regalo`
(`kind="gift"`), la elección de escena al iniciar una cita
(`kind="scene_select"`) y las acciones de cita (`kind="date_action"`). Todos
comparten el mismo `TraceStore`.

Los ajustes se leen del entorno con `airi.config.Settings` (stdlib, sin
`pydantic-settings`): se prefiere el prefijo `AIRI_` y se acepta el nombre
histórico (`AIRI_TRACE_DIR` → `TRACE_DIR`).

```bash
# Guardar trazas en disco (vacío = solo ring en memoria)
TRACE_DIR=./traces          # o AIRI_TRACE_DIR
# Omitir la respuesta cruda del modelo (ahorra disco, pero el turno
# deja de ser reproducible)
TRACE_KEEP_RAW=1
# Tamaño del ring en memoria (turnos inspeccionables con `!debug`)
TRACE_KEEP_LAST=500         # o AIRI_TRACE_KEEP_LAST
```

- `!debug ultimo [n]` (solo dueño): resumen de los últimos `n` eventos del
  ring (def. 1, máx. 20) — incluye comandos, regalos y citas.
- `!debug id <cid>` (solo dueño): envía el JSON del evento con ese
  `correlation_id` como adjunto (lo busca en el ring y, si no, en `TRACE_DIR`).
- `!debug errores` (solo dueño): lista los eventos recientes con errores.
- `!debug clear` (solo dueño): vacía el ring en memoria (no toca el disco).
- `!debug turno` / `!debug trace` (solo dueño): resumen / JSON de tu último
  turno con Airi.
- Inspeccionar trazas desde la terminal (lee `--dir`, `AIRI_TRACE_DIR` o
  `TRACE_DIR`):

```bash
PYTHONPATH=src .venv/bin/python -m airi.trace last 10
PYTHONPATH=src .venv/bin/python -m airi.trace show <cid>
```

- Reproducir un turno sin Discord ni red:

```bash
PYTHONPATH=src .venv/bin/python -m airi.replay ./traces/2026-10-14/<cid>.json
# exit 0 = la reproducción coincide; exit 1 = diverge o no es reproducible
PYTHONPATH=src .venv/bin/python -m airi.replay --emit-test ./traces/.../<cid>.json
# genera tests/integration/test_regression_<cid>.py desde la traza
```

## Regresión y cobertura (Fase 6)

### Transcripts

`tests/fixtures/transcripts/*.jsonl` guardan conversaciones completas: por
turno, el texto del usuario y la respuesta CRUDA del modelo. El runner
(`tests/test_transcripts_regression.py`) las reinyecta con `FakeLLM` a través
de `ConversationService`/`DateService` y compara contra las expectativas
grabadas en el propio fichero (patrón auto-golden):

- Un transcript nuevo se ejecuta, graba sus expectativas y se marca `skipped`;
  la siguiente ejecución ya verifica.
- Si cambias comportamiento a propósito, regenera los goldens:

```bash
RECORD_TRANSCRIPTS=1 .venv/bin/python -m pytest tests/test_transcripts_regression.py
```

Transcripts incluidos: conversación normal, subida de nivel (Amiga) con
reflexión de diario, JSON inválido, delta sin motivo, grounding rechazado,
respuesta duplicada (skip), cita con crisis y recuperación, y cita fallida.

> Nota: con los snapshots, una traza de producción ya es en sí misma un
> transcript reproducible (inputs + prompt + respuesta cruda + estado previo),
> por lo que no se añadió un convertidor traza→transcript. Los
> `tests/fixtures/transcripts/*.jsonl` se mantienen como goldens sintéticos
> para caminos no observados en producción.

### Cobertura

`coverage.py`/`pytest-cov` no están instalados en este entorno sin red, así
que `tools/coverage.py` mide la cobertura de líneas con `sys.settrace`
(stdlib) durante la suite:

```bash
.venv/bin/python tools/coverage.py              # objetivos: domain >= 90%, services >= 70%
.venv/bin/python tools/coverage.py --missing    # + líneas sin cubrir
```

Estado actual: `domain/` ~97%, `services/` ~99%.
