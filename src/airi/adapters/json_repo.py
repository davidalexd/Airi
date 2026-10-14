"""Repositorio JSON genérico (adaptador de persistencia)."""

from __future__ import annotations

import json
import os


def load_json(path, default):
    """Carga un JSON que debe ser un objeto; ante cualquier problema, `default`."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        pass
    return default


def save_json(path, data):
    """Guarda un JSON de forma atómica (tmp + rename)."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_json_list(path, default=None):
    """Como load_json pero para ficheros cuyo contenido es una lista."""
    if default is None:
        default = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return default


class JSONRepository:
    """Repo genérico: `load()` devuelve datos o el default, `save()` persiste."""

    def __init__(self, path, default_factory=dict, *, as_list=False):
        self.path = str(path)
        self.default_factory = default_factory
        self.as_list = as_list

    def load(self):
        default = self.default_factory()
        if self.as_list:
            return load_json_list(self.path, default)
        return load_json(self.path, default)

    def save(self, data):
        save_json(self.path, data)
