"""Chollometro (fuente complementaria, solo avisos; no alimenta el buscador).

Verificado el 30/10/2026:
- RSS `/rss/nuevos` (y `/rss/hot`): 30 elementos (~50 min de publicaciones), sin
  paginación ni feeds por categoría. Cada <item> trae título, <link> al hilo,
  <category> general y `<pepper:merchant name="Amazon" price="14,87€"/>`.
- La página del hilo incluye el objeto JSON del chollo: `threadId`, `price`,
  `nextBestPrice` (precio anterior declarado), `isExpired`, `status`, `merchant`.
  El enlace a la tienda no se publica (`link: null`): el aviso enlaza al hilo.
Solo se consideran tiendas de la lista fiable, y se ignoran las que ya se vigilan
directamente para no duplicar avisos.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from html import unescape

from .. import normalizar
from ..modelos import Oferta
from . import registrar
from .base import Tienda

log = logging.getLogger(__name__)

FEEDS = ["https://www.chollometro.com/rss/nuevos", "https://www.chollometro.com/rss/hot"]

# Nombre de tienda en Chollometro (normalizado) -> id interno de tienda
TIENDAS_FIABLES = {
    "amazon": "amazon", "amazones": "amazon", "mediamarkt": "mediamarkt",
    "pccomponentes": "pccomponentes", "elcorteingles": "elcorteingles", "fnac": "fnac",
    "worten": "worten", "carrefour": "carrefour", "backmarket": "backmarket",
    "apple": "apple", "applestore": "apple", "samsung": "samsung", "xiaomi": "xiaomi",
    "mistore": "xiaomi",
}
CATEGORIAS_FEED = {"electronica", "gaming", "informatica", "telefonia"}

# Categoría deducida del título (el feed solo trae categorías generales)
_CATEGORIA_TITULO = [
    ("consolas", r"\bconsola\b|\bps5\b|playstation 5|xbox series|nintendo switch|steam deck"),
    ("graficas", r"tarjeta grafica|\brtx ?\d{4}|\bradeon rx|\brx ?\d{4}\b"),
    ("portatiles", r"\bportatil\b|\blaptop\b|\bmacbook\b|\bnotebook\b|chromebook"),
    ("tablets", r"\btablet\b|\bipad\b|galaxy tab|\bxiaomi pad\b|\bredmi pad\b"),
    ("relojes", r"smartwatch|\breloj\b|apple watch|galaxy watch|\bgarmin\b|\bamazfit\b"),
    ("auriculares", r"auricular|\bairpods\b|\bbuds\b|\bcascos\b|headphones"),
    ("monitores", r"\bmonitor\b"),
    ("moviles", r"\bmovil\b|smartphone|\biphone\b|galaxy [asz]\d|\bpixel \d|redmi note|"
                r"\bpoco [xfm]\d|\boneplus \d"),
]
_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_CDATA = r"(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?"


def _campo(item: str, etiqueta: str) -> str:
    m = re.search(rf"<{etiqueta}>{_CDATA}</{etiqueta}>", item, re.S)
    return unescape(m.group(1)).strip() if m else ""


def _precio(texto: str) -> float | None:
    m = re.search(r"(\d[\d.]*)(?:,(\d{1,2}))?", texto or "")
    if not m:
        return None
    return float(m.group(1).replace(".", "") + "." + (m.group(2) or "0"))


def categoria_de(titulo: str) -> str | None:
    t = normalizar.sin_acentos(titulo)
    for cat, patron in _CATEGORIA_TITULO:
        if re.search(patron, t):
            return cat
    return None


def tienda_de(nombre: str) -> str | None:
    return TIENDAS_FIABLES.get(re.sub(r"[^a-z]", "", normalizar.sin_acentos(nombre)))


def parsear_feed(xml: str, ignorar: set[str] = frozenset()) -> list[Oferta]:
    ofertas = []
    for item in _ITEM.findall(xml):
        merchant = re.search(r'<pepper:merchant name="([^"]*)"(?: price="([^"]*)")?', item)
        if not merchant:
            continue
        tienda = tienda_de(unescape(merchant.group(1)))
        precio = _precio(unescape(merchant.group(2) or ""))
        titulo = _campo(item, "title")
        cat_feed = normalizar.sin_acentos(_campo(item, "category"))
        categoria = categoria_de(titulo)
        if (not tienda or tienda in ignorar or not precio or not categoria
                or cat_feed not in CATEGORIAS_FEED):
            continue
        enlace = _campo(item, "link")
        hilo = re.search(r"-(\d+)$", enlace)
        if not hilo:
            continue
        ofertas.append(Oferta(
            tienda="chollometro", id_tienda=hilo.group(1), titulo=titulo, url=enlace,
            precio=precio, categoria=categoria, vendedor=unescape(merchant.group(1)),
        ))
    return ofertas


def datos_hilo(html: str, id_hilo: str) -> dict | None:
    """Objeto JSON del chollo: se busca hacia atrás desde su threadId."""
    marca = f'"threadId":"{id_hilo}"'
    pos = html.find(marca)
    if pos < 0:
        return None
    dec = json.JSONDecoder()
    for _ in range(200):
        pos = html.rfind("{", 0, pos)
        if pos < 0:
            return None
        try:
            obj, _ = dec.raw_decode(html, pos)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("threadId") == id_hilo:
            return obj
    return None


@registrar
class Chollometro(Tienda):
    nombre = "chollometro"
    nombre_visible = "Chollometro"
    solo_avisos = True
    nota_aviso = ("Fuente: Chollometro. El enlace lleva al hilo (botón «Ir al chollo»). "
                  "No se puede comprobar si lo vende la propia tienda o un vendedor externo.")

    def nombre_para(self, oferta: Oferta) -> str:
        return f"{oferta.vendedor} (vía Chollometro)" if oferta.vendedor else self.nombre_visible

    def _vigiladas(self) -> set[str]:
        en_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        return {n for n, t in self.cfg.get("tiendas", {}).items()
                if n != self.nombre and t.get("activa")
                and not (en_actions and t.get("solo_local"))}

    async def listar(self, categorias: list[str]) -> list[Oferta]:
        respuestas = await asyncio.gather(*(self.http.get(u) for u in FEEDS),
                                          return_exceptions=True)
        if all(isinstance(r, Exception) for r in respuestas):
            raise respuestas[0]
        ignorar = self._vigiladas()
        vistas: dict[str, Oferta] = {}
        elementos = 0
        for r in respuestas:
            if isinstance(r, Exception):
                log.warning("[chollometro] feed fallido: %s", r)
                continue
            elementos += r.text.count("<item>")
            for o in parsear_feed(r.text, ignorar):
                if o.categoria in categorias:
                    vistas.setdefault(o.id_tienda, o)
        if not elementos:
            raise RuntimeError("los feeds no tienen elementos (¿cambió el RSS?)")
        # El precio anterior solo está en el hilo: se consulta únicamente para lo que
        # podría disparar un aviso (precio por debajo del límite de barrido).
        limite = self.cfg.get("rastreo", {}).get("barrido_hasta", 330)
        baratas = [o for o in vistas.values() if o.precio <= limite]
        for o, d in zip(baratas, await asyncio.gather(*(self.ficha(o) for o in baratas),
                                                         return_exceptions=True)):
            if isinstance(d, Oferta):
                o.precio_tachado, o.en_stock = d.precio_tachado, d.en_stock
        log.info("[chollometro] %d elementos, %d de mis categorías y tiendas fiables "
                 "(%d hilos consultados)", elementos, len(vistas), len(baratas))
        return list(vistas.values())

    async def ficha(self, oferta: Oferta) -> Oferta | None:
        r = await self.http.get(oferta.url)
        d = datos_hilo(r.text, oferta.id_tienda)
        if not d or d.get("price") is None:
            return None
        nueva = Oferta(**{**oferta.__dict__})
        nueva.precio = float(d["price"])
        nueva.en_stock = not d.get("isExpired") and d.get("status") == "Activated"
        if d.get("nextBestPrice"):
            nueva.precio_tachado = float(d["nextBestPrice"])
        return nueva
