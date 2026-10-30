"""Línea de comandos.

    python -m bot ciclo                  # ciclo completo con las tiendas activas
    python -m bot ciclo --solo pccomponentes
    python -m bot ciclo --simular-alerta # inyecta un error de precio falso y manda el email
    python -m bot test-email             # email de prueba simple
    python -m bot sonda                  # qué tiendas responden desde esta IP
    python -m bot tarea-local            # tiendas solo_local (lo lanza el Programador de tareas)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from . import avisos, compartidos, correo, exportar, normalizar, sonda, tarea_local
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


async def _ciclo(args, cfg: dict, solo_local: bool = False) -> int:
    inicio = time.monotonic()
    registro = cargar_todas()
    en_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    activas = [n for n, t in cfg["tiendas"].items()
               if t.get("activa") and n in registro and not (en_actions and t.get("solo_local"))]
    if solo_local:
        activas = [n for n in activas if cfg["tiendas"][n].get("solo_local")]
    if args.solo:
        activas = [n for n in args.solo.split(",") if n in registro]
    http = Cliente(cfg["red"])
    comp = cfg["avisos_compartidos"]
    try:  # avisos que ya mandó la otra ejecución (Actions <-> local)
        externos = await compartidos.leer(http, comp["url_local" if en_actions else "url_actions"])
    except compartidos.SinConexion as e:
        if solo_local:
            log.warning("Sin conexión (%s): se salta este ciclo", e)
            await http.cerrar()
            return 0
        log.warning("No se pudieron leer los avisos compartidos: %s", e)
        externos = []
    tiendas = [registro[n](http, cfg) for n in activas]
    db = Historial(args.db)
    try:
        log.info("Ciclo con %d tiendas: %s (%d avisos externos recientes)", len(tiendas),
                 ", ".join(activas) or "(ninguna)", len(externos))
        resumen = await ejecutar(cfg, db, tiendas, externos=externos)
        estado = [{"tienda": r.tienda, "ok": r.ok, "productos": r.productos}
                  for r in resumen.tiendas]
        nombres = {t.nombre: t.nombre_visible for t in tiendas}
        n = exportar.escribir(db, nombres, Path(args.salida), estado)
        ruta_avisos = Path(args.db).parent / "avisos.json"
        compartidos.escribir(db, ruta_avisos, avisos.HORAS_HUELLA)
    finally:
        db.cerrar()
        await http.cerrar()
    if resumen.avisos_enviados and not en_actions:
        try:  # que Actions no repita este aviso por Chollometro
            compartidos.subir_rama_local(ruta_avisos)
        except Exception as e:
            log.error("No se pudieron subir los avisos locales (puede llegar un duplicado): %s", e)
    caidas = [r.tienda for r in resumen.tiendas if not r.ok]
    _resumen_actions(resumen, http.peticiones, time.monotonic() - inicio)
    log.info("Fin del ciclo en %.1fs: %d peticiones, %d variantes publicadas, "
             "%d candidatos, %d avisos, caídas: %s", time.monotonic() - inicio,
             http.peticiones, n, resumen.candidatos, resumen.avisos_enviados,
             ", ".join(caidas) or "ninguna")
    return 0


def _resumen_actions(resumen, peticiones: int, segundos: float) -> None:
    """Tabla por tienda en el resumen del run de GitHub Actions."""
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ruta:
        return
    filas = [f"| {r.tienda} | {'✅' if r.ok else '❌ ' + r.error[:80]} | {r.productos} | "
             f"{r.descartados} | {r.segundos} |" for r in resumen.tiendas]
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("\n".join([
            f"### Ciclo: {segundos:.0f} s, {peticiones} peticiones, "
            f"{resumen.candidatos} candidatos, {resumen.avisos_enviados} avisos", "",
            "| Tienda | Estado | Válidos | Descartados | Segundos |",
            "|---|---|---|---|---|", *filas, ""]))


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


def _tarea_local(args, cfg: dict) -> int:
    """Tiendas solo_local, sin ventana. Sale sin hacer nada si va con poca batería
    o si ya hay otra instancia; sin conexión, `_ciclo` también lo salta."""
    tarea_local.log_a_archivo(RAIZ / "datos" / "tarea_local.log")
    if not tarea_local.prioridad_baja():
        log.warning("No se pudo bajar la prioridad del proceso")
    enchufado, pct = tarea_local.energia()
    if not tarea_local.bateria_suficiente(enchufado, pct, cfg["tarea_local"]["bateria_min"]):
        log.info("Batería al %s %% sin cargador: se salta este ciclo", pct)
        return 0
    cerrojo = tarea_local.Cerrojo(RAIZ / "datos" / "tarea_local.lock")
    if not cerrojo.adquirir():
        log.info("Ya hay otra instancia en marcha: se salta este ciclo")
        return 0
    try:
        return asyncio.run(_ciclo(args, cfg, solo_local=True))
    except Exception:
        log.exception("La tarea local terminó con un error")
        return 1
    finally:
        cerrojo.liberar()


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
    tl = sub.add_parser("tarea-local", help="tiendas solo_local (Programador de tareas)")
    tl.add_argument("--db", default=str(RAIZ / "datos" / "historial.sqlite"))
    tl.add_argument("--salida", default=str(RAIZ / "datos" / "ofertas_local.json"))
    tl.set_defaults(solo=None, simular_alerta=False)
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
    if args.orden == "tarea-local":
        return _tarea_local(args, cfg)
    if args.simular_alerta:
        return asyncio.run(_simular(cfg))
    return asyncio.run(_ciclo(args, cfg))


if __name__ == "__main__":
    sys.exit(main())
