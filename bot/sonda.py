"""Diagnóstico: una petición a cada tienda para ver si responde desde esta IP.

`python -m bot sonda` en local o en el workflow manual sonda.yml (IPs de GitHub).
"""
from __future__ import annotations

import asyncio

import httpx

from .http import CABECERAS, _parece_reto

URLS = {
    "pccomponentes": "https://www.pccomponentes.com/categorias/portatiles",
    "mediamarkt": "https://www.mediamarkt.es/es/category/smartphones-263.html",
    "amazon": "https://www.amazon.es/s?k=samsung+galaxy+s25+ultra&rh=p_6%3AA1AT7YVPFBWXBL",
    "samsung": "https://www.samsung.com/es/smartphones/galaxy-s25-ultra/buy/",
    "chollometro": "https://www.chollometro.com/rss/nuevos",
    "apple": "https://www.apple.com/es/shop/buy-iphone",
    "xiaomi": "https://www.mi.com/es/",
    "elcorteingles": "https://www.elcorteingles.es/electronica/moviles-y-smartphones/",
    "fnac": "https://www.fnac.es/",
    "worten": "https://www.worten.es/productos/telefonos-y-smartphones/smartphones",
    "carrefour": "https://www.carrefour.es/moviles/cat20004/c",
    "backmarket": "https://www.backmarket.es/es-es/l/smartphones/6c290010-c0c2-47a4-b68a-ac2ec2b64dca",
}


async def _una(cliente: httpx.AsyncClient, tienda: str, url: str) -> str:
    try:
        r = await cliente.get(url)
    except httpx.HTTPError as e:
        return f"{tienda:14} ERROR {type(e).__name__}"
    t = r.text
    reto = "RETO" if _parece_reto(t) or "validateCaptcha" in t else "-"
    return (f"{tienda:14} HTTP {r.status_code}  {len(t):>8} bytes  "
            f"ld+json={t.count('application/ld+json'):<3} reto={reto}")


async def ejecutar() -> list[str]:
    async with httpx.AsyncClient(headers=CABECERAS, follow_redirects=True, timeout=20) as c:
        return await asyncio.gather(*(_una(c, t, u) for t, u in URLS.items()))
