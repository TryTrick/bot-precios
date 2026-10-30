"""PcComponentes — SOLO EN LOCAL (desde las IPs de GitHub Actions responde 403 de Cloudflare).

Datos: JSON-LD (verificado el 30/10/2026).
- Listado `/categorias/<slug>`: `ItemList` con 40 productos/página: nombre, url, sku, marca,
  `offers.price`, `offers.availability` y `offers.seller.name` (filtra marketplace).
- Orden `?sort=price_asc|price_desc|sales|activation_date`, paginación `?page=N`.
- Ficha: objeto `product` con `gtin13`, `itemCondition` y `offers.offers` (oferta principal,
  con `offeredBy`).
No hay filtro por vendedor en la URL y por precio ascendente salen solo vendedores externos,
así que aquí no se hace barrido: más vendidos + novedades + rotación por precio descendente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from ..http import Bloqueado
from ..modelos import NUEVO, REACONDICIONADO, Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

BASE = "https://www.pccomponentes.com"
VENDEDOR = "PcComponentes"
# Slugs del sitemap oficial (sitemap/sitemap_categories.xml)
CATEGORIAS = {
    "moviles": ["smartphone-moviles"],
    "portatiles": ["portatiles"],
    "tablets": ["tablets"],
    "relojes": ["smartwatch"],
    "auriculares": ["auriculares"],
    # Solo consolas (los slugs sin "videoconsolas-" mezclan juegos y mandos).
    # "videoconsolas-xbox-series-x-s" no tiene listado (30/10/2026).
    "consolas": ["videoconsolas-ps5", "videoconsolas-nintendo-switch-2"],
    "graficas": ["tarjetas-graficas"],
    "monitores": ["monitores-pc"],
}
_LD = re.compile(r"<script[^>]*ld\+json[^>]*>(.*?)</script>", re.S)


def _bloques(html: str) -> list:
    salida = []
    for crudo in _LD.findall(html):
        try:
            salida.append(json.loads(crudo))
        except ValueError:
            continue
    return salida


def _precio(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def parsear_listado(html: str, categoria: str) -> list[Oferta]:
    for d in _bloques(html):
        if isinstance(d, dict) and d.get("@type") == "ItemList":
            break
    else:
        raise ValueError("no hay JSON-LD ItemList (¿cambió la web?)")
    ofertas = []
    for el in d.get("itemListElement", []):
        p = el.get("item") or {}
        of = p.get("offers") or {}
        precio = _precio(of.get("price"))
        if not precio or not p.get("url"):
            continue
        ofertas.append(Oferta(
            tienda="pccomponentes", id_tienda=str(p.get("sku") or p["url"].rsplit("/", 1)[-1]),
            titulo=p.get("name", ""), url=p["url"], precio=precio, categoria=categoria,
            vendido_por_tienda=(of.get("seller") or {}).get("name") == VENDEDOR,
            en_stock=str(of.get("availability", "")).endswith("InStock"),
            marca=(p.get("brand") or {}).get("name"),
        ))
    return ofertas


def parsear_ficha(html: str, categoria: str) -> Oferta | None:
    for d in _bloques(html):
        if not (isinstance(d, dict) and str(d.get("@type", "")).lower() == "product"):
            continue
        of = (d.get("offers") or {}).get("offers") or d.get("offers") or {}
        if isinstance(of, list):
            of = of[0] if of else {}
        precio = _precio(of.get("price"))
        if not precio:
            return None
        return Oferta(
            tienda="pccomponentes", id_tienda=str(d.get("sku")), titulo=d.get("name", ""),
            url=d.get("url", ""), precio=precio, categoria=categoria,
            estado=REACONDICIONADO if "Refurbished" in str(d.get("itemCondition")) else NUEVO,
            vendido_por_tienda=(of.get("offeredBy") or of.get("seller") or {}).get("name") == VENDEDOR,
            en_stock=str(of.get("availability", "")).endswith("InStock"),
            ean=d.get("gtin13") or None, marca=(d.get("brand") or {}).get("name"),
        )
    return None


@registrar
class PcComponentes(Tienda):
    nombre = "pccomponentes"
    nombre_visible = "PcComponentes"

    async def _pagina(self, slug: str, categoria: str, orden: str, pagina: int = 1) -> list[Oferta]:
        params = {"sort": orden}
        if pagina > 1:
            params["page"] = str(pagina)
        r = await self.http.get(f"{BASE}/categorias/{slug}", params=params)
        return parsear_listado(r.text, categoria)

    async def _categoria(self, categoria: str) -> list[Oferta]:
        giro = int(time.time() // 900)
        ofertas: list[Oferta] = []
        for slug in CATEGORIAS[categoria]:
            ofertas += await self._pagina(slug, categoria, "sales")
            ofertas += await self._pagina(slug, categoria, "activation_date")
            for n in range(self.cfg.get("rastreo", {}).get("paginas_rotacion", 1)):
                try:
                    ofertas += await self._pagina(slug, categoria, "price_desc", (giro + n) % 15 + 1)
                except ValueError:
                    pass  # página fuera de rango en categorías pequeñas: no es un fallo
        log.info("[pccomponentes] %s: %d productos", categoria, len(ofertas))
        return ofertas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        cats = [c for c in categorias if c in CATEGORIAS]
        resultados = await asyncio.gather(*(self._categoria(c) for c in cats),
                                          return_exceptions=True)
        vistas: dict[str, Oferta] = {}
        errores = []
        for res in resultados:
            if isinstance(res, Bloqueado):
                raise res  # no se aprovecha lo leído: la tienda cuenta como caída este ciclo
        for cat, res in zip(cats, resultados):
            if isinstance(res, Exception):
                errores.append(f"{cat}: {type(res).__name__}: {res}")
                continue
            for o in res:
                vistas.setdefault(o.id_tienda, o)
        if errores and not vistas:
            raise RuntimeError("; ".join(errores))
        for e in errores:
            log.warning("[pccomponentes] categoría fallida: %s", e)
        return list(vistas.values())

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        r = await self.http.get(oferta.url)
        return parsear_ficha(r.text, oferta.categoria)
