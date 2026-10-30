"""Línea de comandos.

    python -m bot ciclo                  # ciclo completo con las tiendas activas
    python -m bot ciclo --solo pccomponentes
    python -m bot ciclo --simular-alerta # inyecta un error de precio falso y manda el email
    python -m bot test-email             # email de prueba simple
    python -m bot sonda                  # qué tiendas responden desde esta IP
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from . import correo, exportar, normalizar, sonda
from .ciclo import ejecutar
from .config import RAIZ, cargar_config, cargar_env
from .db import Historial
from .http import Cliente
from .modelos import Oferta
from .tiendas import cargar_todas
from .tiendas.simulada import Simulada, oferta_falsa

log = logging.getLogger("bot")


def _logging() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # la consola de Windows no es UTF-8 por defecto
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _ciclo(args, cfg: dict) -> int:
    inicio = time.monotonic()
    registro = cargar_todas()
    activas = [n for n, t in cfg["tiendas"].items() if t.get("activa") and n in registro]
    if args.solo:
        activas = [n for n in args.solo.split(",") if n in registro]
    http = Cliente(cfg["red"])
    tiendas = [registro[n](http) for n in activas]
    db = Historial(args.db)
    try:
        log.info("Ciclo con %d tiendas: %s", len(tiendas), ", ".join(activas) or "(ninguna)")
        resumen = await ejecutar(cfg, db, tiendas)
        estado = [{"tienda": r.tienda, "ok": r.ok, "productos": r.productos}
                  for r in resumen.tiendas]
        nombres = {t.nombre: t.nombre_visible for t in tiendas}
        n = exportar.escribir(db, nombres, Path(args.salida), estado)
    finally:
        db.cerrar()
        await http.cerrar()
    caidas = [r.tienda for r in resumen.tiendas if not r.ok]
    log.info("Fin del ciclo en %.1fs: %d peticiones, %d variantes publicadas, "
             "%d candidatos, %d avisos, caídas: %s", time.monotonic() - inicio,
             http.peticiones, n, resumen.candidatos, resumen.avisos_enviados,
             ", ".join(caidas) or "ninguna")
    return 0


async def _simular(cfg: dict) -> int:
    """BD en memoria con historial inventado + tienda simulada con precio de error."""
    db = Historial(":memory:")
    falsa = oferta_falsa()
    clave = normalizar.clave_producto(falsa.titulo, falsa.categoria, falsa.marca)
    for i in range(1, 8):
        dia = (date.today() - timedelta(days=i)).isoformat()
        db.guardar(Oferta(tienda="pccomponentes", id_tienda="REF-1",
                          titulo="Samsung Galaxy S25 Ultra 12/512GB Titanio Negro",
                          url="https://example.com/ref", precio=1449.0,
                          categoria="moviles", marca="Samsung"), clave, dia=dia)
    resumen = await ejecutar(cfg, db, [Simulada()], prueba=True)
    db.cerrar()
    if resumen.avisos_enviados:
        log.info("Alerta simulada enviada. Revisa tu correo.")
        return 0
    log.error("La alerta simulada NO se envió (mira los mensajes anteriores).")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("ciclo", help="ejecuta un ciclo completo")
    c.add_argument("--db", default=str(RAIZ / "datos" / "historial.sqlite"))
    c.add_argument("--salida", default=str(RAIZ / "site" / "ofertas.json"))
    c.add_argument("--solo", help="lista de tiendas separadas por comas")
    c.add_argument("--simular-alerta", action="store_true",
                   help="inyecta un precio falso en una BD de prueba y manda el email")
    sub.add_parser("test-email", help="manda un email de prueba")
    sub.add_parser("sonda", help="comprueba qué tiendas responden desde esta IP")
    args = p.parse_args(argv)

    _logging()
    cargar_env()
    cfg = cargar_config()
    if args.orden == "test-email":
        correo.enviar("[bot-precios] Email de prueba",
                      "Si lees esto, el envío por Gmail funciona correctamente.")
        return 0
    if args.orden == "sonda":
        for linea in asyncio.run(sonda.ejecutar()):
            print(linea)
        return 0
    if args.simular_alerta:
        return asyncio.run(_simular(cfg))
    return asyncio.run(_ciclo(args, cfg))


if __name__ == "__main__":
    sys.exit(main())
