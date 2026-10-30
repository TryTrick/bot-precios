"""Registro de tiendas disponibles. Para añadir una: crear el módulo con una
subclase de Tienda y añadirla aquí y en config.yaml."""
from __future__ import annotations

from .base import Tienda

REGISTRO: dict[str, type[Tienda]] = {}


def registrar(cls: type[Tienda]) -> type[Tienda]:
    REGISTRO[cls.nombre] = cls
    return cls


def cargar_todas() -> dict[str, type[Tienda]]:
    # Importar los módulos ejecuta su @registrar
    from . import mediamarkt, simulada  # noqa: F401
    return REGISTRO
