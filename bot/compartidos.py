"""Datos compartidos entre GitHub Actions y la tarea local.

1. Avisos: cada ejecución publica las huellas de sus avisos recientes (tienda vendedora,
   clave, categoría, precio, hora) y lee las de la otra antes de avisar, para no mandar
   dos veces el mismo chollo.
2. Tiendas locales (PcComponentes, que bloquea las IPs de GitHub): la tarea local publica
   en cada ejecución sus productos de las últimas 48 h con su historial de precios, y
   Actions los importa para la web y como referencia de las demás tiendas.

Actions guarda `avisos.json` en la rama `datos`; la tarea local sube `avisos.json` y
`tiendas_locales.json` a la rama `datos-local`. Se leen por raw.githubusercontent.com
(público, caché de unos 5 minutos).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import normalizar
from .config import RAIZ
from .db import Historial
from .exportar import VIGENCIA_HORAS
from .http import Cliente

log = logging.getLogger(__name__)

RAMA_LOCAL = "datos-local"
FRESCURA_HORAS = 2  # tienda local "al día" en la web si su última lectura es más reciente


class SinConexion(Exception):
    pass


async def leer_json(http: Cliente, url: str) -> dict | None:
    """JSON publicado por la otra ejecución. None si aún no existe o no se puede leer."""
    try:
        r = await http.get(url, detectar_reto=False)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            log.warning("No se pudo leer %s: %s", url, e)
        return None
    except httpx.TransportError as e:
        raise SinConexion(str(e)) from e
    try:
        datos = r.json()
    except ValueError:
        log.warning("JSON ilegible en %s", url)
        return None
    return datos if isinstance(datos, dict) else None


async def leer(http: Cliente, url: str) -> list[dict]:
    """Huellas de avisos publicadas por la otra ejecución."""
    datos = await leer_json(http, url) or {}
    return [h for h in datos.get("avisos", []) if isinstance(h, dict)]


def _hace(horas: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()


def escribir(db: Historial, ruta: Path, horas: int) -> str:
    """Escribe las huellas propias de las últimas `horas` y devuelve el JSON."""
    texto = json.dumps({"avisos": db.avisos_desde(_hace(horas))}, ensure_ascii=False, indent=1)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto + "\n", encoding="utf-8")
    return texto


# --- tiendas locales ----------------------------------------------------------

def escribir_locales(db: Historial, ruta: Path, estado: dict[str, dict],
                     dias_historial: int) -> int:
    """Productos de las tiendas locales vistos en las últimas 48 h, con su historial.
    `estado`: {tienda: {"ok": bool, "productos": int}} del ciclo que acaba de terminar."""
    productos = []
    dias_desde = (datetime.now(timezone.utc) - timedelta(days=dias_historial)).date().isoformat()
    for tienda in estado:
        productos += db.exportar_tienda(tienda, _hace(VIGENCIA_HORAS), dias_desde)
    datos = {"generado": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
             "tiendas": estado, "productos": productos}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return len(productos)


def importar_locales(db: Historial, datos: dict | None) -> list[dict]:
    """Importa los productos de las tiendas locales y devuelve su estado para la web.
    Cada producto conserva su hora real de lectura: la web lo deja de mostrar a las 48 h
    si la tarea local deja de publicar."""
    if not datos:
        return []
    for fila in datos.get("productos", []):
        if isinstance(fila, dict) and fila.get("tienda") and fila.get("id_tienda"):
            # La clave se recalcula con el código de aquí: la guardada puede ser de una
            # versión anterior del emparejado
            fila["clave"] = normalizar.clave_producto(fila.get("titulo", ""),
                                                      fila.get("categoria", ""), fila.get("marca"))
            db.importar(fila)
    db.con.commit()
    al_dia = datos.get("generado", "") >= _hace(FRESCURA_HORAS)
    estado = [{"tienda": t, "ok": bool(e.get("ok")) and al_dia, "productos": e.get("productos", 0)}
              for t, e in (datos.get("tiendas") or {}).items()]
    log.info("Importados %d productos de tiendas locales (%s), generados %s",
             len(datos.get("productos", [])), ", ".join(e["tienda"] for e in estado),
             datos.get("generado"))
    return estado


# --- subida a la rama datos-local --------------------------------------------

def _git(*args: str, entrada: str | None = None, timeout: int = 30) -> str:
    # Sin preguntas: si las credenciales no valen, falla en vez de quedarse esperando
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    r = subprocess.run(["git", *args], cwd=RAIZ, input=entrada, capture_output=True,
                       text=True, timeout=timeout, env=env)
    if r.returncode:
        raise RuntimeError(f"git {args[0]}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def subir_rama_local(archivos: list[Path]) -> None:
    """Sube los archivos como único commit de la rama datos-local (sin tocar main)."""
    arbol = arbol_de(archivos)
    hora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    commit = _git("commit-tree", arbol, "-m", f"Datos de la tarea local {hora}")
    _git("push", "-q", "-f", "origin", f"{commit}:refs/heads/{RAMA_LOCAL}", timeout=90)
    log.info("Datos locales subidos a la rama %s", RAMA_LOCAL)


def arbol_de(archivos: list[Path]) -> str:
    """Árbol de git con esos archivos en la raíz (sin checkout ni índice)."""
    entradas = "".join(
        # -z: terminado en NUL; con "\n" Windows lo convierte en "\r\n" y el nombre acaba en "\r"
        f"100644 blob {_git('hash-object', '-w', str(a))}\t{a.name}\0"
        for a in sorted(archivos, key=lambda a: a.name))
    return _git("mktree", "-z", entrada=entradas)
