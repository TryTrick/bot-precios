"""Regla de aviso configurable (config.yaml → aviso)."""
from __future__ import annotations


def descuento_pct(precio: float, referencia: float) -> float:
    return round((1 - precio / referencia) * 100, 1) if referencia else 0.0


def cumple(precio: float, referencia: float | None, cfg: dict) -> bool:
    if not referencia or precio <= 0 or precio >= referencia:
        return False
    modo = cfg["modo"]
    if modo == "precio_final":
        p = cfg["precio_final"]
        return referencia >= p["referencia_min"] and precio <= p["precio_max"]
    if modo == "porcentaje":
        return descuento_pct(precio, referencia) >= cfg["porcentaje"]["caida_min"]
    raise ValueError(f"Modo de aviso desconocido: {modo!r}")
