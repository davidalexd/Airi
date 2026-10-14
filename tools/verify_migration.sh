#!/usr/bin/env bash
set -e

echo "== 1. No hay legacy =="
! find . -maxdepth 1 \( -name "bot.py" -o -name "game.py" -o -name "date_view.py" \)

echo "== 2. No hay doble paquete =="
[ ! -d "airi" ] || { echo "ERROR: airi/ en raíz"; exit 1; }

echo "== 3. src/airi/ raíz limpio (4 ficheros base) =="
count=$(ls src/airi/*.py 2>/dev/null | wc -l)
[ "$count" -eq 4 ] || { echo "ERROR: src/airi/ tiene $count ficheros (esperado 4)"; exit 1; }

echo "== 4. observability/ (7 ficheros) =="
count=$(ls src/airi/observability/*.py 2>/dev/null | wc -l)
[ "$count" -eq 7 ] || { echo "ERROR: observability/ tiene $count ficheros (esperado 7)"; exit 1; }

echo "== 5. testing/ (4 ficheros) =="
count=$(ls src/airi/testing/*.py 2>/dev/null | wc -l)
[ "$count" -eq 4 ] || { echo "ERROR: testing/ tiene $count ficheros (esperado 4)"; exit 1; }

echo "== 6. domain/ puro =="
! grep -rE "import (aiohttp|discord|requests)|open\(" src/airi/domain/

echo "== 7. replay desacoplado de tests/ =="
! grep -rn "from tests\.\|import tests\." src/airi/

echo "== 8. Tests ubicados (solo conftest.py + __init__.py en tests/) =="
count=$(ls tests/*.py 2>/dev/null | wc -l)
[ "$count" -eq 2 ] || { echo "ERROR: tests/ tiene $count ficheros (esperado 2)"; exit 1; }

echo "== 9. Traces suficientes (>= 3) =="
count=$(ls tests/fixtures/traces/*.json 2>/dev/null | wc -l)
[ "$count" -ge 3 ] || { echo "ERROR: solo $count traces (esperado >= 3)"; exit 1; }

echo "== 10. .gitignore presente =="
[ -f ".gitignore" ] || { echo "ERROR: .gitignore ausente"; exit 1; }

echo "== 11. *.egg-info/ no versionado =="
eggs=$(git ls-files | grep -E '\.egg-info/' || true)
[ -z "$eggs" ] || { echo "ERROR: *.egg-info/ versionado: $eggs"; exit 1; }

echo "== 12. Suite verde =="
pytest tests/ -q

echo "== 13. Ruff limpio =="
ruff check src/ tests/ tools/

echo "OK: migración cerrada."
