"""Modelo de datos común a todas las tiendas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

NUEVO = "nuevo"
REACONDICIONADO = "reacondicionado"


def ahora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Oferta:
    """Un producto tal y como lo publica una tienda en un momento dado."""
    tienda: str
    id_tienda: str            # SKU / ASIN / id propio de la tienda
    titulo: str
    url: str
    precio: float
    categoria: str
    estado: str = NUEVO
    vendido_por_tienda: bool = True
    en_stock: bool = True
    precio_tachado: float | None = None
    ean: str | None = None
    marca: str | None = None
    visto: str = field(default_factory=ahora_iso)


@dataclass
class Candidato:
    """Oferta que cumple la regla de aviso y está pendiente de confirmar."""
    oferta: Oferta
    clave: str | None
    referencia: float
    explicacion: str
    descuento_pct: float
