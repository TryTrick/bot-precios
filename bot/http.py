"""Cliente HTTP educado: límite de concurrencia, pausas por tienda y reintentos.

No intenta saltarse protecciones: si una tienda responde 403/429 o con una
página de reto/CAPTCHA, se lanza Bloqueado y la tienda se marca caída.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
CABECERAS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
_SEÑALES_RETO = ("<title>Just a moment", "captcha", "Access Denied", "cf-chl")


class Bloqueado(Exception):
    pass


class Cliente:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._global = asyncio.Semaphore(cfg.get("concurrencia_global", 4))
        self._por_host: dict[str, asyncio.Semaphore] = {}
        self._ultimo: dict[str, float] = {}
        self._bloqueados: dict[str, str] = {}  # host -> motivo; no se le vuelve a pedir nada
        self._http = httpx.AsyncClient(headers=CABECERAS, follow_redirects=True,
                                       timeout=cfg.get("timeout", 20), http2=False)
        self.peticiones = 0

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def get(self, url: str, *, params: dict | None = None,
                  cabeceras: dict | None = None, detectar_reto: bool = True) -> httpx.Response:
        host = urlsplit(url).netloc
        if host in self._bloqueados:  # tras un 403/429 o reto, nada más a esa tienda en el ciclo
            raise Bloqueado(f"{self._bloqueados[host]} (sin más peticiones en este ciclo)")
        sem = self._por_host.setdefault(
            host, asyncio.Semaphore(self.cfg.get("concurrencia_por_tienda", 1)))
        intentos = self.cfg.get("reintentos", 2) + 1
        async with sem, self._global:
            for intento in range(1, intentos + 1):
                await self._pausa(host)
                try:
                    self.peticiones += 1
                    r = await self._http.get(url, params=params, headers=cabeceras)
                except httpx.TransportError as e:
                    log.warning("%s intento %d: %s", url, intento, e)
                    if intento == intentos:
                        raise
                    continue
                if r.status_code in (403, 429):
                    raise self._bloquear(host, f"HTTP {r.status_code} en {url}")
                if r.status_code >= 500 and intento < intentos:
                    log.warning("%s intento %d: HTTP %d", url, intento, r.status_code)
                    continue
                r.raise_for_status()
                if detectar_reto and _parece_reto(r.text):
                    raise self._bloquear(host, f"Página de reto/CAPTCHA en {url}")
                return r
        raise RuntimeError("inalcanzable")

    def _bloquear(self, host: str, motivo: str) -> Bloqueado:
        self._bloqueados[host] = motivo
        log.error("Bloqueo en %s: %s. No se reintenta en este ciclo.", host, motivo)
        return Bloqueado(motivo)

    async def _pausa(self, host: str) -> None:
        minimo, maximo = self.cfg.get("pausas_por_host", {}).get(
            host, (self.cfg.get("pausa_min", 1.0), self.cfg.get("pausa_max", 3.0)))
        espera = random.uniform(minimo, maximo)
        transcurrido = time.monotonic() - self._ultimo.get(host, 0)
        if transcurrido < espera:
            await asyncio.sleep(espera - transcurrido)
        self._ultimo[host] = time.monotonic()


def _parece_reto(texto: str) -> bool:
    # Las páginas de reto son pequeñas; una página real puede mencionar "captcha"
    # en algún script, por eso solo se mira si el documento es corto.
    if len(texto) > 50_000:
        return False
    cabeza = texto[:20_000]
    return any(s.lower() in cabeza.lower() for s in _SEÑALES_RETO)
