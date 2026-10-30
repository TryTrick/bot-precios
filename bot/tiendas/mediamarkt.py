"""MediaMarkt.es

Datos: `window.__PRELOADED_STATE__` (caché Apollo) presente tanto en listados como
en fichas. Por producto trae título, URL, EAN, precio, precio tachado, stock y si
es de marketplace. Verificado el 30/10/2026:
- Filtro `?marketplace=MediaMarkt` = solo vendidos por MediaMarkt.
- Orden `sort=currentprice+asc|currentprice+desc|release_date+desc|salescount+desc`.
- `page=N`, 12 productos por página, como mucho 30 páginas (`ProductList.maxPage`).
Estrategia: barrido por precio ascendente hasta `rastreo.barrido_hasta` (ve todo lo
que podría disparar el aviso) + páginas de rotación por precio descendente.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from ..modelos import Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

BASE = "https://www.mediamarkt.es"
# Slugs e IDs copiados del sitemap oficial (sitemap-productlistpages.xml)
CATEGORIAS = {
    "moviles": "smartphones-263",
    "portatiles": "port%C3%A1tiles-153",
    "tablets": "tablets-169",
    "relojes": "smartwatches-265",
    "auriculares": "auriculares-498",
    "consolas": "consolas-843",
    # "graficas": no hay ninguna vendida por MediaMarkt (470 de marketplace, 30/10/2026)
    "monitores": "monitores-179",
}
_MARCA_ESTADO = "__PRELOADED_STATE__ = "
_UNDEFINED = re.compile(r"(?<=[:\[,])undefined(?=[,}\]])")


class SinDatos(Exception):
    pass


def estado_apollo(html: str) -> dict:
    i = html.find(_MARCA_ESTADO)
    if i < 0:
        raise SinDatos("no hay __PRELOADED_STATE__ (¿cambió la web?)")
    i += len(_MARCA_ESTADO)
    j = html.find("</script>", i)
    crudo = _UNDEFINED.sub("null", html[i:j].rstrip().rstrip(";"))
    return json.loads(crudo).get("apolloState", {})


def _por_id(apollo: dict, tipo: str) -> dict[str, dict]:
    """Las 'features' Cofr se indexan por 'Media:es:<id>'; se agrupan por <id>."""
    salida: dict[str, dict] = {}
    for k, v in apollo.items():
        if k.startswith(tipo + ":") and isinstance(v, dict) and "id" in v:
            salida.setdefault(str(v["id"]).rsplit(":", 1)[-1], v)
    return salida


def parsear(html: str, categoria: str) -> tuple[list[Oferta], int]:
    """Ofertas de una página (listado o ficha) y número máximo de páginas."""
    apollo = estado_apollo(html)
    precios = _por_id(apollo, "CofrPriceFeature")
    stock = _por_id(apollo, "CofrOnlineStatusFeature")
    nucleo = _por_id(apollo, "CofrCoreFeature")
    ofertas: list[Oferta] = []
    for k, prod in apollo.items():
        if not k.startswith("GraphqlProduct:"):
            continue
        pid = str(prod.get("id"))
        pr, st, nu = precios.get(pid), stock.get(pid, {}), nucleo.get(pid, {})
        if not pr or not (pr.get("price") or {}).get("amount"):
            continue
        tachado = pr.get("strikePrice") or {}
        externo = bool(pr.get("isProductOfTypeMarketplace") or pr.get("marketplaceSeller")
                       or nu.get("isProductOfTypeMarketplace")
                       or st.get("onlineStatus") == "MP_OFFER")
        titulo = prod.get("title") or ""
        if pr.get("isProductOfTypeBundle"):
            titulo = "Pack " + titulo  # confirmar.es_pack lo descartará
        ofertas.append(Oferta(
            tienda="mediamarkt", id_tienda=pid, titulo=titulo,
            url=BASE + prod.get("url", ""), precio=float(pr["price"]["amount"]),
            categoria=categoria, vendido_por_tienda=not externo,
            en_stock=bool(st.get("isAvailableAndBuyable")) and st.get("onlineStatus") == "AVAILABLE",
            precio_tachado=(float(tachado["amount"])
                            if tachado.get("shouldBeStruck") and tachado.get("amount") else None),
            ean=nu.get("ean") or None, marca=(prod.get("manufacturer") or "").title() or None,
        ))
    max_pagina = 1
    for k, v in apollo.items():
        if k.startswith("ProductList:"):
            max_pagina = max(max_pagina, int(v.get("maxPage") or 1))
    return ofertas, max_pagina


@registrar
class MediaMarkt(Tienda):
    nombre = "mediamarkt"
    nombre_visible = "MediaMarkt"

    async def _pagina(self, categoria: str, orden: str, pagina: int) -> tuple[list[Oferta], int]:
        url = f"{BASE}/es/category/{CATEGORIAS[categoria]}.html"
        params = {"marketplace": "MediaMarkt", "sort": orden}
        if pagina > 1:
            params["page"] = str(pagina)
        r = await self.http.get(url, params=params)
        return parsear(r.text, categoria)

    async def _categoria(self, categoria: str) -> list[Oferta]:
        rastreo = self.cfg.get("rastreo", {})
        limite = rastreo.get("barrido_hasta", 330)
        max_barrido = rastreo.get("max_paginas_barrido", 15)
        ofertas, max_pagina = await self._pagina(categoria, "currentprice asc", 1)
        pagina = 1
        while (ofertas and pagina < min(max_barrido, max_pagina)
               and max(o.precio for o in ofertas[-12:]) <= limite):
            pagina += 1
            nuevas, _ = await self._pagina(categoria, "currentprice asc", pagina)
            if not nuevas:
                break
            ofertas += nuevas
        # Rotación: una página distinta del resto del catálogo en cada ciclo (cron ~15 min)
        giro = int(time.time() // 900)
        for n in range(rastreo.get("paginas_rotacion", 1)):
            p = (giro + n) % max_pagina + 1
            ofertas += (await self._pagina(categoria, "currentprice desc", p))[0]
        log.info("[mediamarkt] %s: %d productos (%d págs. de barrido)", categoria, len(ofertas), pagina)
        return ofertas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        cats = [c for c in categorias if c in CATEGORIAS]
        resultados = await asyncio.gather(*(self._categoria(c) for c in cats),
                                          return_exceptions=True)
        vistas: dict[str, Oferta] = {}
        errores = []
        for cat, res in zip(cats, resultados):
            if isinstance(res, Exception):
                errores.append(f"{cat}: {type(res).__name__}: {res}")
                continue
            for o in res:
                vistas.setdefault(o.id_tienda, o)
        if errores and not vistas:
            raise RuntimeError("; ".join(errores))
        for e in errores:
            log.warning("[mediamarkt] categoría fallida: %s", e)
        return list(vistas.values())

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        r = await self.http.get(oferta.url)
        for o in parsear(r.text, oferta.categoria)[0]:
            if o.id_tienda == oferta.id_tienda:
                return o
        return None
