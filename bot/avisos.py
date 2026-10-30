"""Deduplicación y redacción de los emails."""
from __future__ import annotations

import logging

from . import correo
from .db import Historial
from .modelos import Candidato, Oferta

log = logging.getLogger(__name__)


def es_duplicado(db: Historial, o: Oferta) -> bool:
    """Un aviso por producto y precio; solo se repite si el precio baja más."""
    anterior = db.precio_ultimo_aviso(o.tienda, o.id_tienda)
    return anterior is not None and o.precio >= anterior


def redactar_alerta(c: Candidato, nombre_tienda: str, prueba: bool = False,
                    nota: str = "") -> tuple[str, str]:
    o = c.oferta
    prefijo = "[PRUEBA] " if prueba else ""
    asunto = (f"{prefijo}⚠️ {o.titulo[:80]} a {o.precio:.2f} € en {nombre_tienda} "
              f"(-{c.descuento_pct:.0f}%)")
    cuerpo = "\n".join([
        f"Posible error de precio en {nombre_tienda}" + (" (EMAIL DE PRUEBA)" if prueba else ""),
        "",
        f"Producto:    {o.titulo}",
        f"Estado:      {o.estado}",
        f"Precio:      {o.precio:.2f} €",
        f"Referencia:  {c.referencia:.2f} €  (descuento {c.descuento_pct:.1f} %)",
        f"Cálculo:     {c.explicacion}",
        f"Comprobado:  {o.visto}",
        "",
        f"Enlace directo: {o.url}",
        "",
        "Confirmado volviendo a consultar la ficha: vendido por la tienda, en stock,",
        "no es accesorio ni pack. Aun así, revísalo antes de comprar.",
    ] + (["", nota] if nota else []))
    return asunto, cuerpo


def enviar_alerta(db: Historial, c: Candidato, nombre_tienda: str, prueba: bool = False,
                  nota: str = "") -> bool:
    asunto, cuerpo = redactar_alerta(c, nombre_tienda, prueba, nota)
    try:
        correo.enviar(asunto, cuerpo)
    except Exception as e:
        log.error("No se pudo enviar el aviso (%s): %s", asunto, e)
        return False
    db.registrar_aviso(c.oferta.tienda, c.oferta.id_tienda, c.oferta.precio, c.referencia)
    return True


def enviar_tienda_rota(db: Historial, tienda: str, fallos: int, error: str) -> bool:
    asunto = f"🔧 Tienda rota: {tienda} ({fallos} ciclos fallando)"
    cuerpo = (f"La tienda {tienda} lleva {fallos} ciclos seguidos fallando o devolviendo "
              f"0 productos. Puede que haya cambiado su web o que esté bloqueando.\n\n"
              f"Último error: {error}\n\n"
              "No se enviará otro aviso de esta tienda en 24 horas.")
    try:
        correo.enviar(asunto, cuerpo)
    except Exception as e:
        log.error("No se pudo enviar el aviso de tienda rota: %s", e)
        return False
    db.marcar_email_rota(tienda)
    return True
