from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from bot.config import cargar_config
from bot.db import Historial
from bot.modelos import Oferta

_CFG = cargar_config()


@pytest.fixture
def cfg() -> dict:
    return copy.deepcopy(_CFG)


@pytest.fixture
def db():
    h = Historial(":memory:")
    yield h
    h.cerrar()


def oferta(**kw) -> Oferta:
    base = dict(tienda="pccomponentes", id_tienda="1",
                titulo="Samsung Galaxy S25 Ultra 12/512GB Titanio Negro",
                url="https://example.com/p", precio=1449.0, categoria="moviles",
                marca="Samsung")
    base.update(kw)
    return Oferta(**base)


def sembrar(db: Historial, o: Oferta, clave: str | None, precio: float, dias: int) -> None:
    """Historial de `dias` días anteriores a hoy a precio fijo."""
    for i in range(1, dias + 1):
        o2 = Oferta(**{**o.__dict__, "precio": precio})
        db.guardar(o2, clave, dia=(date.today() - timedelta(days=i)).isoformat())
