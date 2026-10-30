"""Interfaz común de las tiendas."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..http import Cliente
from ..modelos import Oferta


class Tienda(ABC):
    nombre: str = ""            # id interno (config.yaml)
    nombre_visible: str = ""    # lo que se muestra en la web y en los emails
    solo_avisos: bool = False   # True = fuente de avisos (Chollometro), no va al buscador

    nota_aviso: str = ""        # texto extra para el email de aviso

    def nombre_para(self, oferta: Oferta) -> str:
        """Nombre de la tienda que se muestra en el aviso de esta oferta."""
        return self.nombre_visible

    def __init__(self, http: Cliente, cfg: dict | None = None):
        self.http = http
        self.cfg = cfg or {}

    @abstractmethod
    async def listar(self, categorias: list[str]) -> list[Oferta]:
        """Ofertas de los listados de categoría de este ciclo."""

    @abstractmethod
    async def ficha(self, oferta: Oferta) -> Oferta | None:
        """Vuelve a consultar el producto (para confirmar antes de avisar)."""
