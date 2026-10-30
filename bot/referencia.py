"""Precio de referencia de un producto.

1. Mediana del historial propio (días anteriores a hoy, mín. N días).
2. Mediana de cada otra tienda que vende el mismo producto (EAN o clave).
Referencia = mediana de esas medianas. Si no hay nada, el precio tachado de
la propia tienda (último recurso). Si tampoco, no hay referencia.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from .db import Historial
from .modelos import Oferta


def calcular(db: Historial, o: Oferta, clave: str | None, cfg: dict,
             dia: date | None = None) -> tuple[float | None, str]:
    dia = dia or date.today()
    ventana = cfg.get("dias", 30)
    min_propios = cfg.get("min_dias_propios", 3)
    desde = (dia - timedelta(days=ventana)).isoformat()

    medianas: list[float] = []
    partes: list[str] = []

    propios = db.precios_tienda(o.tienda, o.id_tienda, desde, hasta_excluido=dia.isoformat())
    if len(propios) >= min_propios:
        m = median(propios)
        medianas.append(m)
        partes.append(f"{o.tienda}: mediana {m:.2f} € ({len(propios)} días)")

    for fila in db.equivalentes(o, clave):
        precios = db.precios_tienda(fila["tienda"], fila["id_tienda"], desde)
        if precios:
            m = median(precios)
            medianas.append(m)
            partes.append(f"{fila['tienda']}: mediana {m:.2f} € ({len(precios)} días)")

    if medianas:
        ref = median(medianas)
        return ref, "Mediana de: " + "; ".join(partes)
    if o.precio_tachado and o.precio_tachado > o.precio:
        return o.precio_tachado, f"Precio tachado de {o.tienda} (sin historial)"
    return None, "Sin referencia"
