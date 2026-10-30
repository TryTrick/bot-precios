"""Genera el JSON que usa la web de búsqueda: una línea por variante con la
oferta nueva más barata y la reacondicionada más barata."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import normalizar
from .db import Historial
from .modelos import REACONDICIONADO

VIGENCIA_HORAS = 48  # productos no vistos en este tiempo no se publican


def construir(db: Historial, nombres: dict[str, str]) -> dict:
    limite = (datetime.now(timezone.utc) - timedelta(hours=VIGENCIA_HORAS)).isoformat()
    grupos: dict[str, dict] = {}
    for p in db.todos_productos():
        if not p["en_stock"] or p["ultima_vez"] < limite or p["tienda"] == "simulada":
            continue
        clave = p["clave"] or (f"ean:{p['ean']}" if p["ean"] else f"{p['tienda']}:{p['id_tienda']}")
        g = grupos.setdefault(clave, {"tokens": set(), "c": p["categoria"], "n": None, "r": None})
        g["tokens"].update(normalizar.tokens_busqueda(p["titulo"]))
        lado = "r" if p["estado"] == REACONDICIONADO else "n"
        actual = g[lado]
        if actual is None or p["precio"] < actual["p"]:
            g[lado] = {"t": p["titulo"], "s": nombres.get(p["tienda"], p["tienda"]),
                       "p": round(p["precio"], 2), "u": p["url"], "v": p["ultima_vez"]}
    variantes = [
        {"k": " ".join(sorted(g["tokens"])), "c": g["c"], "n": g["n"], "r": g["r"]}
        for g in grupos.values()
    ]
    return {"generado": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "variantes": variantes}


def escribir(db: Historial, nombres: dict[str, str], ruta: Path, estado: list[dict]) -> int:
    datos = construir(db, nombres)
    datos["tiendas"] = estado
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(datos["variantes"])
