"""Comprobaciones antes de mandar un aviso."""
from __future__ import annotations

from . import normalizar
from .modelos import Candidato, Oferta
from .tiendas.base import Tienda

TOLERANCIA_PRECIO = 0.02  # 2 % de diferencia entre listado y ficha


def comprobar_oferta(o: Oferta) -> str | None:
    """Filtros que no necesitan red. Devuelve el motivo de rechazo o None."""
    if not o.vendido_por_tienda:
        return "vendido por un vendedor externo"
    if not o.en_stock:
        return "sin stock"
    if normalizar.es_accesorio(o.titulo):
        return "es un accesorio"
    if normalizar.es_pack(o.titulo):
        return "es un pack"
    return None


async def confirmar(tienda: Tienda, c: Candidato) -> tuple[bool, str, Oferta | None]:
    try:
        nueva = await tienda.ficha(c.oferta)
    except Exception as e:  # la ficha falló: mejor no avisar que avisar mal
        return False, f"no se pudo reconsultar la ficha: {e}", None
    if nueva is None:
        return False, "la ficha no devolvió el producto", None
    motivo = comprobar_oferta(nueva)
    if motivo:
        return False, motivo, nueva
    if nueva.estado != c.oferta.estado:
        return False, f"el estado cambió ({c.oferta.estado} → {nueva.estado})", nueva
    if abs(nueva.precio - c.oferta.precio) > c.oferta.precio * TOLERANCIA_PRECIO:
        return False, f"el precio cambió en la ficha ({nueva.precio:.2f} €)", nueva
    clave_nueva = normalizar.clave_producto(nueva.titulo, nueva.categoria, nueva.marca)
    if c.clave and clave_nueva and clave_nueva != c.clave:
        return False, f"la variante no coincide ({clave_nueva} ≠ {c.clave})", nueva
    return True, "confirmado", nueva
