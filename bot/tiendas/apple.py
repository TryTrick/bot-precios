"""Apple Store online (apple.com/es) — iPhone e iPad.

Verificado el 30/10/2026: cada página de compra `/es/shop/buy-iphone/<modelo>` (y
buy-ipad) incluye `window.PRODUCT_SELECTION_BOOTSTRAP = { productSelectionData: {...} }`
con `products` (una entrada por referencia `partNumber`, con sus `dimension*`:
capacidad, color, conectividad, tamaño) y `displayValues.prices[<fullPrice>]`
(`amountBeforeTradeIn`). Los modelos se descubren en las páginas índice buy-iphone y
buy-ipad. Apple vende directamente; la página no indica stock por referencia.
"""
from __future__ import annotations

import json
import logging
import re
from html import unescape

from ..modelos import Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

WEB = "https://www.apple.com"
INDICES = {"moviles": "/es/shop/buy-iphone", "tablets": "/es/shop/buy-ipad"}
_MARCA = "productSelectionData: "
_ETIQUETAS = re.compile(r"<as-footnote.*?</as-footnote>|<[^>]+>", re.S)


def modelos(html: str, indice: str) -> list[str]:
    rutas = sorted(set(re.findall(re.escape(indice) + r"/[a-z0-9-]+", html)))
    return [r for r in rutas if not r.endswith("carrier-offers")]


def _texto(valor) -> str:
    return " ".join(unescape(_ETIQUETAS.sub("", str(valor or ""))).split())


def _variante(dim: str, valor: str) -> str:
    """Texto corto de una opción a partir de su clave interna (los textos visibles
    son largos y meten especificaciones que confunden el emparejado)."""
    if dim == "dimensionCapacity":
        return valor.upper()                      # 256gb -> 256GB, 1tb -> 1TB
    if dim == "dimensionConnection":
        return "Wi-Fi + Cellular" if "cell" in valor else "Wi-Fi"
    if dim == "dimensionScreensize":
        return valor.replace("_", ".").replace("inch", "in")   # 13inch -> 13in
    if dim == "dimensionFinish":
        return "nanotexturizado" if valor == "matte" else ""
    return valor


def parsear(html: str, url: str, categoria: str) -> list[Oferta]:
    i = html.find(_MARCA)
    if i < 0:
        return []  # página sin selector de compra (p. ej. ofertas de operadoras)
    datos, _ = json.JSONDecoder().raw_decode(html, i + len(_MARCA))
    valores = datos.get("displayValues") or {}
    precios = valores.get("prices") or {}
    titulo_pag = re.search(r"<title>([^<]*)", html)
    familia = re.sub(r"^Compra(r)? (un |una |el |la )?|\s*-\s*Apple.*$", "",
                     unescape(titulo_pag.group(1)) if titulo_pag else "").strip()
    ofertas = []
    for p in datos.get("products") or []:
        precio = (precios.get(p.get("fullPrice")) or {}).get("amountBeforeTradeIn")
        if not precio:
            continue
        modelo, variantes = familia, []
        for dim, valor in sorted(p.items()):
            if (not dim.startswith("dimension") or dim == "dimensionColor"
                    or not isinstance(valor, str) or dim not in valores):
                continue  # dimensionSteporder y similares no son opciones
            texto = _texto(((valores.get(dim) or {}).get(valor) or {}).get("value"))
            if re.match(r"(iPhone|iPad)\b", texto):  # la opción nombra el modelo exacto
                modelo = re.split(r"\s+Pantalla|\s+Modelo", texto)[0]
            elif t := _variante(dim, valor):
                variantes.append(t)
        titulo = " ".join(["Apple", modelo, *variantes])
        ofertas.append(Oferta(
            tienda="apple", id_tienda=p["partNumber"], titulo=titulo, url=url,
            precio=float(precio), categoria=categoria, marca="Apple",
        ))
    return ofertas


@registrar
class Apple(Tienda):
    nombre = "apple"
    nombre_visible = "Apple Store"

    async def _categoria(self, categoria: str) -> list[Oferta]:
        indice = INDICES[categoria]
        r = await self.http.get(WEB + indice)
        rutas = modelos(r.text, indice)
        if not rutas:
            raise ValueError(f"sin modelos en {indice} (¿cambió la web?)")
        ofertas: list[Oferta] = []
        for ruta in rutas:
            pagina = await self.http.get(WEB + ruta)
            ofertas += parsear(pagina.text, WEB + ruta, categoria)
        log.info("[apple] %s: %d referencias en %d modelos", categoria, len(ofertas), len(rutas))
        return ofertas

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        ofertas: list[Oferta] = []
        for cat in [c for c in categorias if c in INDICES]:
            ofertas += await self._categoria(cat)
        return ofertas

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        r = await self.http.get(oferta.url)
        return next((o for o in parsear(r.text, oferta.url, oferta.categoria)
                     if o.id_tienda == oferta.id_tienda), None)
