"""Avisos compartidos entre GitHub Actions y la tarea local, para no avisar dos veces.

Cada ejecución publica las huellas de sus avisos recientes (tienda vendedora, clave,
categoría, precio, hora) y lee las de la otra antes de avisar:
- Actions las guarda en `avisos.json` de la rama `datos`.
- La tarea local las sube a la rama `avisos-local` (solo cuando envía un aviso).
Se leen por raw.githubusercontent.com (público, caché de unos 5 minutos).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import RAIZ
from .db import Historial
from .http import Cliente

log = logging.getLogger(__name__)

RAMA_LOCAL = "avisos-local"


class SinConexion(Exception):
    pass


async def leer(http: Cliente, url: str) -> list[dict]:
    """Huellas publicadas por la otra ejecución. 404 = todavía no hay ninguna."""
    try:
        r = await http.get(url, detectar_reto=False)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return []
        log.warning("No se pudieron leer los avisos compartidos (%s): %s", url, e)
        return []
    except httpx.TransportError as e:
        raise SinConexion(str(e)) from e
    try:
        datos = r.json()
    except ValueError:
        log.warning("Avisos compartidos ilegibles en %s", url)
        return []
    return [h for h in datos.get("avisos", []) if isinstance(h, dict)]


def escribir(db: Historial, ruta: Path, horas: int) -> str:
    """Escribe las huellas propias de las últimas `horas` y devuelve el JSON."""
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    texto = json.dumps({"avisos": db.avisos_desde(desde)}, ensure_ascii=False, indent=1)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto + "\n", encoding="utf-8")
    return texto


def _git(*args: str, entrada: str | None = None, timeout: int = 30) -> str:
    # Sin preguntas: si las credenciales no valen, falla en vez de quedarse esperando
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    r = subprocess.run(["git", *args], cwd=RAIZ, input=entrada, capture_output=True,
                       text=True, timeout=timeout, env=env)
    if r.returncode:
        raise RuntimeError(f"git {args[0]}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def subir_rama_local(ruta: Path) -> None:
    """Sube `avisos.json` como único commit de la rama avisos-local (sin tocar main)."""
    blob = _git("hash-object", "-w", str(ruta))
    arbol = _git("mktree", entrada=f"100644 blob {blob}\tavisos.json\n")
    hora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    commit = _git("commit-tree", arbol, "-m", f"Avisos de la tarea local {hora}")
    _git("push", "-q", "-f", "origin", f"{commit}:refs/heads/{RAMA_LOCAL}", timeout=90)
    log.info("Avisos locales subidos a la rama %s", RAMA_LOCAL)
