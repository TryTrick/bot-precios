"""Samsung tienda oficial (samsung.com/es).

Datos: la API que usa su propio buscador de productos (verificada el 30/10/2026):
  https://searchapi.samsung.com/v6/front/b2c/product/finder/hybris
    ?type=<pfCategoryTypeCode>&siteCode=es&start=1&num=100&sort=newest&onlyFilterInfoYN=N
`type` sale del campo oculto `pfCategoryTypeCode` de cada página /es/<categoría>/all-…/.
Cada familia trae `modelList` con `price` (normal), `promotionPrice` (actual),
`stockStatusText` (inStock/outOfStock) y la capacidad en `fmyChipList`.
Con num=100 cada categoría cabe en una petición. Los modelos sin precio
(`ctaType` = learnMore) no se venden online y se ignoran.
"""
from __future__ import annotations

import asyncio
import logging

from ..modelos import Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

API = "https://searchapi.samsung.com/v6/front/b2c/product/finder/hybris"
WEB = "https://www.samsung.com"
TIPOS = {
    "moviles": "01010000",
    "tablets": "01020000",
    "relojes": "01030000",
    "auriculares": "01040000",   # "audio-sound": en ES solo Galaxy Buds
    "portatiles": "03010000",
    "monitores": "07010000",
}


def _num(valor) -> float | None:
    try:
        return float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parsear(datos: dict, categoria: str) -> list[Oferta]:
    resultado = (datos.get("response") or {}).get("resultData")
    if not resultado or "productList" not in resultado:
        raise ValueError("respuesta sin productList (¿cambió la API?)")
    ofertas = []
    for familia in resultado["productList"]:
        for m in familia.get("modelList") or []:
            normal, promo = _num(m.get("price")), _num(m.get("promotionPrice"))
            precio = promo or normal
            if not precio:
                continue
            chips = {c.get("fmyChipType"): c.get("fmyChipLocalName") or c.get("fmyChipName")
                     for c in m.get("fmyChipList") or []}
            # El nombre no lleva capacidad ni tamaño: se añaden desde las opciones
            extras = [v for k, v in chips.items() if k and k != "COLOR" and v]
            titulo = " ".join(["Samsung", m.get("displayName") or familia.get("fmyMarketingName", ""),
                               *extras]).strip()
            ofertas.append(Oferta(
                tienda="samsung", id_tienda=m["modelCode"], titulo=titulo,
                url=WEB + (m.get("pdpUrl") or ""), precio=precio, categoria=categoria,
                vendido_por_tienda=m.get("thirdPartyPrdYN") != "Y"
                and familia.get("thirdPartyPrdYN") != "Y",
                en_stock=m.get("stockStatusText") == "inStock",
                precio_tachado=normal if normal and normal > precio else None,
                marca="Samsung",
            ))
    return ofertas


@registrar
class Samsung(Tienda):
    nombre = "samsung"
    nombre_visible = "Samsung"

    async def _categoria(self, categoria: str) -> list[Oferta]:
        r = await self.http.get(API, params={
            "type": TIPOS[categoria], "siteCode": "es", "start": "1", "num": "100",
            "sort": "newest", "onlyFilterInfoYN": "N"}, detectar_reto=False)
        ofertas = parsear(r.json(), categoria)
        log.info("[samsung] %s: %d modelos con precio", categoria, len(ofertas))
        return ofertas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        cats = [c for c in categorias if c in TIPOS]
        resultados = await asyncio.gather(*(self._categoria(c) for c in cats),
                                          return_exceptions=True)
        ofertas, errores = [], []
        for cat, res in zip(cats, resultados):
            if isinstance(res, Exception):
                errores.append(f"{cat}: {type(res).__name__}: {res}")
            else:
                ofertas += res
        if errores and not ofertas:
            raise RuntimeError("; ".join(errores))
        for e in errores:
            log.warning("[samsung] categoría fallida: %s", e)
        return ofertas

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        # La API no tiene consulta por modelo: se vuelve a pedir su categoría (1 petición)
        for o in await self._categoria(oferta.categoria):
            if o.id_tienda == oferta.id_tienda:
                return o
        return None
