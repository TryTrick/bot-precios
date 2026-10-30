"""Carga de config.yaml y de secretos (.env o variables de entorno)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def cargar_config(ruta: Path | None = None) -> dict:
    ruta = ruta or RAIZ / "config.yaml"
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_env(ruta: Path | None = None) -> None:
    """Lee un .env sencillo (CLAVE=valor). No pisa variables ya definidas,
    así en GitHub Actions mandan los Secrets."""
    ruta = ruta or RAIZ / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
