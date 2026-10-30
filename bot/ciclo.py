"""Un ciclo completo: listar tiendas en paralelo, detectar, confirmar, avisar, guardar."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from . import avisos, normalizar, referencia, reglas
from .confirmar import comprobar_oferta, confirmar
from .db import Historial
from .modelos import Candidato, Oferta
from .tiendas.base import Tienda

log = logging.getLogger(__name__)


@dataclass
class ResultadoTienda:
    tienda: str
    ok: bool
    productos: int = 0
    descartados: int = 0
    segundos: float = 0.0
    error: str = ""


@dataclass
class Resumen:
    tiendas: list[ResultadoTienda] = field(default_factory=list)
    candidatos: int = 0
    avisos_enviados: int = 0


async def _listar(t: Tienda, categorias: list[str]) -> tuple[list[Oferta] | Exception, float]:
    inicio = time.monotonic()
    try:
        ofertas = await t.listar(categorias)
    except Exception as e:
        return e, time.monotonic() - inicio
    return ofertas, time.monotonic() - inicio


async def ejecutar(cfg: dict, db: Historial, tiendas: list[Tienda],
                   prueba: bool = False) -> Resumen:
    resumen = Resumen()
    listados = await asyncio.gather(*(_listar(t, cfg["categorias"]) for t in tiendas))

    for t, (resultado, segundos) in zip(tiendas, listados):
        r = ResultadoTienda(t.nombre, ok=True, segundos=round(segundos, 1))
        resumen.tiendas.append(r)
        if isinstance(resultado, Exception) or not resultado:
            r.ok = False
            r.error = (f"{type(resultado).__name__}: {resultado}"
                       if isinstance(resultado, Exception) else "0 productos")
            log.error("[%s] CAÍDA en %.1fs: %s", t.nombre, segundos, r.error)
            _registrar_fallo(cfg, db, t.nombre, r.error)
            continue
        db.tienda_ok(t.nombre)
        for o in resultado:
            if comprobar_oferta(o):
                r.descartados += 1
                continue
            r.productos += 1
            await _procesar(cfg, db, t, o, resumen, prueba)
        db.con.commit()
        log.info("[%s] OK en %.1fs: %d productos válidos, %d descartados",
                 t.nombre, segundos, r.productos, r.descartados)

    db.con.commit()
    return resumen


async def _procesar(cfg: dict, db: Historial, t: Tienda, o: Oferta,
                    resumen: Resumen, prueba: bool) -> None:
    if o.estado == "nuevo":
        o.estado = normalizar.detectar_estado(o.titulo)
    clave = normalizar.clave_producto(o.titulo, o.categoria, o.marca)
    # La referencia se calcula ANTES de guardar el precio de hoy.
    ref, explicacion = referencia.calcular(db, o, clave, cfg["referencia"])
    if reglas.cumple(o.precio, ref, cfg["aviso"]):
        resumen.candidatos += 1
        c = Candidato(o, clave, ref, explicacion, reglas.descuento_pct(o.precio, ref))
        log.warning("[%s] CANDIDATO: %s a %.2f € (ref %.2f €)", t.nombre, o.titulo, o.precio, ref)
        await _avisar(db, t, c, resumen, prueba)
    if not t.solo_avisos:
        db.guardar(o, clave)


async def _avisar(db: Historial, t: Tienda, c: Candidato, resumen: Resumen, prueba: bool) -> None:
    if avisos.es_duplicado(db, c.oferta):
        log.info("[%s] ya avisado a ese precio o menor: %s", t.nombre, c.oferta.titulo)
        return
    ok, motivo, nueva = await confirmar(t, c)
    if not ok:
        log.warning("[%s] descartado al confirmar (%s): %s", t.nombre, motivo, c.oferta.titulo)
        return
    c.oferta = nueva
    c.descuento_pct = reglas.descuento_pct(nueva.precio, c.referencia)
    if avisos.enviar_alerta(db, c, t.nombre_visible, prueba):
        resumen.avisos_enviados += 1


def _registrar_fallo(cfg: dict, db: Historial, tienda: str, error: str) -> None:
    fallos = db.tienda_fallo(tienda, error)
    db.con.commit()
    umbral = cfg["tienda_rota"]["ciclos_fallidos"]
    if fallos >= umbral and db.puede_avisar_rota(tienda, cfg["tienda_rota"]["horas_entre_emails"]):
        avisos.enviar_tienda_rota(db, tienda, fallos, error)
