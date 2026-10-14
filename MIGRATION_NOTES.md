# Notas de Migración

## Comandos de arranque

**Bot modular (bueno):**
```bash
python -m airi  # después de mover airi/src/ a src/airi/
# o actualmente: cd airi && PYTHONPATH=src python -m airi.src
```

**Bot legacy (viejo):**
```bash
python bot.py
```

## Estado actual
- Paquete `airi/` en raíz con `airi/src/` dentro
- `src/` vacío en la raíz
- Legacy: bot.py, game.py, date_view.py en la raíz
- Datos JSON en la raíz

## Objetivo
- Mover `airi/src/` a `src/airi/`
- Borrar `airi/` de la raíz
- Eliminar legacy
- Reubicar datos a `data/`
