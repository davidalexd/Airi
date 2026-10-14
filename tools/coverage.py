"""Cobertura de líneas y ramas (arcos) de `domain/` y `services/`.

Uso:

    .venv/bin/python tools/coverage.py            # informe + exit code
    .venv/bin/python tools/coverage.py --domain 90 --services 70
    .venv/bin/python tools/coverage.py --missing  # + detalle sin cubrir

Mide qué líneas se ejecutan con `sys.settrace` y, además, la cobertura de
ramas: para cada salto del bytecode (condicional, bucle, etc.) comprueba si
se han tomado todos sus arcos (línea origen → línea destino). Es un
equivalente aproximado a `coverage.py --branch` / `pytest-cov`, que no están
instalados en este entorno sin red.

Sale con código 1 si algún paquete no alcanza su objetivo de líneas o de
ramas.
"""

from __future__ import annotations

import argparse
import dis
import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TARGETS = {
    "domain": os.path.join(SRC, "airi", "domain"),
    "services": os.path.join(SRC, "airi", "services"),
}

# Saltos del bytecode: `hasjrel`/`hasjabs` son listas de opcodes (CPython usa
# `in` sobre la lista; indexarlas por opcode es el bug clásico).
_JUMPS = set(dis.hasjrel) | set(dis.hasjabs)
_UNCOND_JUMPS = {
    name for name in (
        "JUMP_FORWARD",
        "JUMP_ABSOLUTE",
        "JUMP_BACKWARD",
        "JUMP_BACKWARD_NO_INTERRUPT",
    )
    if hasattr(dis, name)
}
_TERMINAL = {
    name for name in (
        "RETURN_VALUE",
        "RETURN_CONST",
        "RETURN_GENERATOR",
        "RAISE_VARARGS",
        "RERAISE",
        "STOP_ITERATION",
    )
    if hasattr(dis, name)
}


def _walk_codes(code):
    """Itera el code object y todos los anidados (funciones, comprehensions)."""
    yield code
    for const in code.co_consts:
        if hasattr(const, "co_code"):
            yield from _walk_codes(const)


def executable_lines(path):
    """Líneas con código ejecutable de un fichero (aprox. vía bytecode)."""
    with open(path, "r", encoding="utf-8") as fh:
        code = compile(fh.read(), path, "exec")
    lines = set()
    for chunk in _walk_codes(code):
        for _, lineno in dis.findlinestarts(chunk):
            lines.add(lineno)
    return lines


def possible_arcs(path):
    """Arcos (línea_origen → línea_destino) alcanzables en el fichero.

    Solo se cuentan los arcos que cruzan de línea (los que un tracer de
    líneas puede observar). Cada salto condicional aporta dos arcos
    (fall-through y destino), los incondicionales uno y `return`/`raise`
    ninguno.
    """
    with open(path, "r", encoding="utf-8") as fh:
        code = compile(fh.read(), path, "exec")
    arcs = set()
    for chunk in _walk_codes(code):
        arcs |= _code_arcs(chunk)
    return arcs


def _code_arcs(code):
    """Arcos observables de un único code object."""
    instrs = list(dis.get_instructions(code))
    line_at = {}
    current = code.co_firstlineno
    for ins in instrs:
        if ins.starts_line is not None:
            current = ins.starts_line
        line_at[ins.offset] = current

    arcs = set()
    for idx, ins in enumerate(instrs):
        src = line_at[ins.offset]
        targets = []
        if ins.opname in _TERMINAL:
            pass
        elif ins.opcode in _JUMPS and ins.opname in _UNCOND_JUMPS:
            targets.append(ins.argval)
        else:
            if idx + 1 < len(instrs):
                targets.append(instrs[idx + 1].offset)
            if ins.opcode in _JUMPS:
                targets.append(ins.argval)
        for off in targets:
            if not isinstance(off, int) or off not in line_at:
                continue
            dst = line_at[off]
            if dst != src and src != 0 and dst != 0:
                arcs.add((src, dst))
    return arcs


def analyze(path):
    """(líneas ejecutables, arcos posibles) de un fichero."""
    return executable_lines(path), possible_arcs(path)


def collect_files(pkg_dir):
    out = {}
    for dirpath, _dirnames, filenames in os.walk(pkg_dir):
        if "__pycache__" in dirpath:
            continue
        for name in sorted(filenames):
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                out[path] = analyze(path)
    return out


def run_suite():
    """Ejecuta la suite bajo un tracer de líneas/arcos.

    Devuelve `(targets, covered_lines, covered_arcs)`.
    """
    targets = {name: collect_files(pkg_dir) for name, pkg_dir in TARGETS.items()}
    target_paths = set()
    for files in targets.values():
        target_paths.update(files)

    covered_lines = {}
    covered_arcs = {}
    prev_line = {}

    def tracer(frame, event, arg):
        filename = frame.f_code.co_filename
        if filename in target_paths:
            covered_lines.setdefault(filename, set()).add(frame.f_lineno)
            if event == "call":
                prev_line[frame] = None
            elif event == "line":
                cur = frame.f_lineno
                prev = prev_line.get(frame)
                if prev is not None and prev != cur:
                    covered_arcs.setdefault(filename, set()).add((prev, cur))
                prev_line[frame] = cur
            elif event in ("return", "exception"):
                prev_line.pop(frame, None)
        return tracer

    import pytest

    sys.settrace(tracer)
    threading_trace = getattr(__import__("threading"), "settrace", None)
    if threading_trace is not None:
        threading_trace(tracer)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "tests/"])
    finally:
        sys.settrace(None)
        if threading_trace is not None:
            threading_trace(None)
    return targets, covered_lines, covered_arcs


def _pct(hit, total):
    return 100.0 * hit / total if total else 100.0


def report(targets, covered_lines, covered_arcs, thresholds, branch_thresholds,
           show_missing=False):
    print()
    all_ok = True
    for pkg, threshold, branch_threshold in zip(TARGETS, thresholds, branch_thresholds):
        files = targets[pkg]
        tot_ln = cov_ln = tot_br = cov_br = 0
        print(f"=== {pkg}/ (objetivo: líneas >= {threshold}%, ramas >= {branch_threshold}%) ===")
        for path, (lines, arcs) in sorted(files.items()):
            hit_ln = len(lines & covered_lines.get(path, set()))
            hit_br = len(arcs & covered_arcs.get(path, set()))
            pct_ln, pct_br = _pct(hit_ln, len(lines)), _pct(hit_br, len(arcs))
            tot_ln += len(lines)
            cov_ln += hit_ln
            tot_br += len(arcs)
            cov_br += hit_br
            flag = "  <-- por debajo" if (pct_ln < threshold or pct_br < branch_threshold) else ""
            print(
                f"  {os.path.relpath(path, ROOT):50s} "
                f"líneas {pct_ln:6.1f}% ({hit_ln}/{len(lines)})  "
                f"ramas {pct_br:6.1f}% ({hit_br}/{len(arcs)}){flag}"
            )
            if show_missing:
                miss_ln = sorted(lines - covered_lines.get(path, set()))
                miss_br = sorted(arcs - covered_arcs.get(path, set()))
                if miss_ln:
                    print(f"      líneas sin cubrir: {miss_ln}")
                if miss_br:
                    print(f"      ramas sin cubrir: {miss_br}")
        ov_ln, ov_br = _pct(cov_ln, tot_ln), _pct(cov_br, tot_br)
        ok = ov_ln >= threshold and ov_br >= branch_threshold
        status = "OK" if ok else "FALLO"
        print(
            f"  {'TOTAL':50s} líneas {ov_ln:6.1f}% ({cov_ln}/{tot_ln})  "
            f"ramas {ov_br:6.1f}% ({cov_br}/{tot_br})  [{status}]"
        )
        print()
        all_ok = all_ok and ok
    return all_ok


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cobertura de domain/ y services/ (líneas + ramas)")
    parser.add_argument("--domain", type=float, default=90.0, help="objetivo de líneas en domain/")
    parser.add_argument("--services", type=float, default=70.0, help="objetivo de líneas en services/")
    parser.add_argument("--domain-branch", type=float, default=80.0,
                        help="objetivo de ramas en domain/")
    parser.add_argument("--services-branch", type=float, default=70.0,
                        help="objetivo de ramas en services/")
    parser.add_argument("--missing", action="store_true",
                        help="lista las líneas y ramas sin cubrir de cada fichero")
    args = parser.parse_args(argv)

    targets, covered_lines, covered_arcs = run_suite()
    ok = report(
        targets,
        covered_lines,
        covered_arcs,
        [args.domain, args.services],
        [args.domain_branch, args.services_branch],
        show_missing=args.missing,
    )
    if not ok:
        print("Objetivos de cobertura NO alcanzados.")
        return 1
    print("Objetivos de cobertura alcanzados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
