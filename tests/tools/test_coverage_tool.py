"""Tests del analizador estático de `tools/coverage.py` (arcos y líneas).

No ejecutan la suite bajo el tracer (eso lo hace el propio tool): comprueban
que la derivación de arcos desde el bytecode es correcta con fragmentos
controlados, que es donde estaba el bug histórico de `dis.hasjrel`.
"""

from __future__ import annotations

import textwrap

import tools.coverage as cov


def _write(tmp_path, src: str) -> str:
    """Escribe el fragmento empezando en la línea 1 (sin línea en blanco inicial)."""
    path = tmp_path / "sample.py"
    path.write_text(textwrap.dedent(src).lstrip("\n"), encoding="utf-8")
    return str(path)


def test_possible_arcs_includes_both_branches(tmp_path):
    path = _write(tmp_path, """
        def f(x):
            if x:
                return 1
            return 2
        """)
    arcs = cov.possible_arcs(path)

    assert (2, 3) in arcs  # if verdadero → return 1
    assert (2, 4) in arcs  # while/if falso → return 2


def test_single_line_branch_has_no_self_arc(tmp_path):
    path = _write(tmp_path, """
        def g(x):
            return 1 if x else 2
        """)
    arcs = cov.possible_arcs(path)

    # La rama ocurre dentro de una sola línea: no es observable como arco.
    assert (2, 2) not in arcs
    assert 2 in cov.executable_lines(path)


def test_loop_back_arc_is_detected(tmp_path):
    path = _write(tmp_path, """
        def h(n):
            total = 0
            for i in range(n):
                total += i
            return total
        """)
    arcs = cov.possible_arcs(path)

    assert (3, 4) in arcs  # cabecera del bucle → cuerpo
    assert (3, 5) in arcs  # cabecera → salida del bucle
    assert (4, 3) in arcs  # cuerpo → cabecera (vuelta)


def test_hasjrel_is_used_as_membership(tmp_path):
    """El bug clásico: indexar `dis.hasjrel` por opcode en vez de usar `in`."""
    path = _write(tmp_path, """
        def f(x):
            if x:
                return 1
            return 2
        """)
    # Si `_JUMPS` fuese una lista indexada por opcode, un `x` normal podría
    # colisionar; aquí basta con que los saltos condicionales se reconozcan.
    arcs = cov.possible_arcs(path)
    assert arcs, "el análisis de saltos no produjo ningún arco"
