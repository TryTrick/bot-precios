"""Xiaomi tienda oficial (mi.com/es) — cobertura parcial.

Verificado el 30/10/2026: las fichas y las páginas `product-list` cargan precios por
variante con JavaScript desde una API que no aparece en el HTML. Lo único que viene
en el HTML son los bloques de las páginas `/es/mobile/` y `/es/wearables/`, dentro de
`window.__PRELOADED_STATE__`: por familia, `name`, `salePrice`, `originPrice`,
`isOutOfStock` y el enlace del botón «Comprar ahora».
Ese precio es el «desde» (variante más barata) y no indica capacidad: estos productos
no se emparejan con otras tiendas (la clave sale None) y solo se comparan con su
propio historial.
"""
from __future__ import annotations

import json
import logging

from ..modelos import Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

PAGINAS = ["https://www.mi.com/es/mobile/", "https://www.mi.com/es/wearables/"]
SUFIJO = " (precio desde)"
_MARCA_ESTADO = "window.__PRELOADED_STATE__ = "


def _categoria(nombre: str, pagina: str) -> str | None:
    n = nombre.lower()
    if any(p in n for p in ("buds", "headphones", "earphones", "auriculares")):
        return "auriculares"
    if "watch" in n or "band" in n:
        return "relojes"
    if "pad" in n:
        return "tablets"
    return "moviles" if "/mobile/" in pagina else None


def _bloques(obj, salida: list) -> None:
    """Bloques con 'goods' (los datos de página vienen también como JSON en texto)."""
    if isinstance(obj, dict):
        bienes = obj.get("goods")
        if isinstance(bienes, list) and bienes and isinstance(bienes[0], dict) \
                and "salePrice" in bienes[0]:
            salida.append(obj)
        for v in obj.values():
            _bloques(v, salida)
    elif isinstance(obj, list):
        for v in obj:
            _bloques(v, salida)
    elif isinstance(obj, str) and obj[:1] in "{[" and "salePrice" in obj:
        try:
            _bloques(json.loads(obj), salida)
        except ValueError:
            pass


def parsear(html: str, pagina: str) -> list[Oferta]:
    i = html.find(_MARCA_ESTADO)
    if i < 0:
        raise ValueError("no hay __PRELOADED_STATE__ (¿cambió la web?)")
    i += len(_MARCA_ESTADO)
    estado = json.loads(html[i:html.find("</script>", i)].strip().rstrip(";"))
    bloques: list[dict] = []
    _bloques(estado, bloques)
    vistas: dict[str, Oferta] = {}
    for b in bloques:
        enlace = next((x.get("gotoUrl") for x in b.get("buttons") or []
                       if x.get("gotoUrl") and "skupanel" not in x["gotoUrl"]), "")
        for g in b["goods"]:
            precio = float(g.get("salePrice") or 0)
            url = g.get("gotoUrl") or enlace
            cat = _categoria(g.get("name", ""), pagina)
            if not precio or not url or not cat or g.get("isCombo"):
                continue
            original = float(g.get("originPrice") or 0)
            vistas.setdefault(g["spuId"], Oferta(
                tienda="xiaomi", id_tienda=g["spuId"], titulo=g["name"] + SUFIJO,
                url=("https:" + url) if url.startswith("//") else url, precio=precio,
                categoria=cat, en_stock=not g.get("isOutOfStock"),
                precio_tachado=original if original > precio else None, marca="Xiaomi",
            ))
    return list(vistas.values())


@registrar
class Xiaomi(Tienda):
    nombre = "xiaomi"
    nombre_visible = "Xiaomi"

    async def _todas(self) -> list[Oferta]:
        ofertas: list[Oferta] = []
        for pagina in PAGINAS:
            r = await self.http.get(pagina)
            ofertas += parsear(r.text, pagina)
        return ofertas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        ofertas = [o for o in await self._todas() if o.categoria in categorias]
        log.info("[xiaomi] %d familias (precio desde)", len(ofertas))
        return ofertas

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        # No hay datos por producto en el HTML de la ficha: se reconsulta la página de listado
        for o in await self._todas():
            if o.id_tienda == oferta.id_tienda:
                return o
        return None
