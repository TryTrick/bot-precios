"""Tienda falsa para pruebas: publica un error de precio inventado.

Se usa con `python -m bot ciclo --simular-alerta` y en los tests. Nunca
hace peticiones de red.
"""
from __future__ import annotations

from ..modelos import Oferta
from . import registrar
from .base import Tienda

PRECIO_FALSO = 299.0


@registrar
class Simulada(Tienda):
    nombre = "simulada"
    nombre_visible = "Tienda simulada (PRUEBA)"

    def __init__(self, http=None, ofertas: list[Oferta] | None = None,
                 fichas: dict[str, Oferta | None] | None = None):
        super().__init__(http)
        self._ofertas = ofertas if ofertas is not None else [oferta_falsa()]
        self._fichas = fichas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        return list(self._ofertas)

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        if self._fichas is not None:
            return self._fichas.get(oferta.id_tienda)
        return oferta


def oferta_falsa() -> Oferta:
    return Oferta(
        tienda="simulada", id_tienda="SIM-S25U-512",
        titulo="Samsung Galaxy S25 Ultra 12/512GB Titanio Negro Libre",
        url="https://example.com/prueba/samsung-galaxy-s25-ultra-512gb",
        precio=PRECIO_FALSO, categoria="moviles", marca="Samsung",
        precio_tachado=1579.0,
    )
