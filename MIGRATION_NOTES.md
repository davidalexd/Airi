# Notas de Migración

## Estado actual: 100 % cerrado

La migración a arquitectura hexagonal está **completada**. Todos los checks pasan.

## Fases completadas

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Consolidar observability/ (borrar trace.py raíz, fijar pyproject.toml) | ✅ |
| 2 | Purificar domain/ (renombrar config.py → constants.py, actualizar imports) | ✅ |
| 3 | Crear src/airi/testing/ con fakes, desacoplar replay de tests/ | ✅ |
| 4 | Reorganizar tests por capa (unit/integration/regression/tools) | ✅ |
| 5 | Crear traces de fixture adicionales (≥ 3) | ✅ |
| 6 | Limpieza final, verify_migration.sh, docs | ✅ |

## Estructura actual

```
discord-local-llm/
├── data/                              (JSON de datos + traces/)
├── src/airi/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py                      (único config)
│   ├── logging_setup.py
│   ├── domain/                        (puro: sin config.py duplicado, sin web.py)
│   ├── ports/
│   ├── adapters/
│   ├── services/
│   ├── discord_bot/
│   ├── observability/                 (events, trace_store, instrumentation, replay, cli, trace)
│   └── testing/                       🆕 (fakes compartidos con replay)
├── tests/
│   ├── conftest.py
│   ├── __init__.py
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   ├── tools/
│   ├── fakes/                         (solo re-exports de airi.testing)
│   └── fixtures/
│       ├── traces/                    (≥ 3 traces)
│       └── transcripts/
├── tools/
│   ├── coverage.py
│   └── verify_migration.sh
├── pyproject.toml
├── README.md
├── MIGRATION_NOTES.md
├── .env / .env.example
└── .gitignore
```

## Comandos de debugging y trazas

- `!debug ultimo` desde Discord.
- `airi-trace last 5` desde CLI.
- `airi-trace show <correlation_id>` desde CLI.
- `airi-replay <trace.json>` para reproducir una traza.
- `airi-replay --emit-test <trace.json>` para generar test de regresión.

Las trazas se guardan en el directorio configurado con `AIRI_TRACE_DIR` (default: `./traces`).

## Reglas post-migración

- **No mezclar fases en un mismo commit.**
- **No añadir features nuevas hasta cerrar la migración.** (Ya cerrado ✅)
- **Todo bug nuevo se convierte en:** un TurnEvent real → un .json en `tests/fixtures/traces/` → un test automático.

## Criterio de cierre (12 checks)

Todos los checks pasan:

1. `ls src/airi/*.py` → 4 ficheros base ✅
2. `ls src/airi/observability/*.py` → 7 ficheros ✅
3. `ls src/airi/testing/*.py` → 4 ficheros ✅
4. `grep -rE "import (aiohttp|discord|requests)|open\(" src/airi/domain/` → vacío ✅
5. `grep -rn "from tests\.\|import tests\." src/airi/` → vacío ✅
6. `ls tests/*.py` → solo conftest.py y __init__.py ✅
7. `ls tests/fixtures/traces/*.json | wc -l` → 3 ✅
8. `pytest tests/ -q` → 137 tests verdes ✅
9. `ruff check src/ tests/ tools/` → limpio ✅
10. `bash tools/verify_migration.sh` → "OK: migración cerrada." ✅
11. `.gitignore` presente con `*.egg-info/`, `__pycache__/`, `.pytest_cache/` ✅
12. `git ls-files | grep '\.egg-info/'` → vacío ✅
