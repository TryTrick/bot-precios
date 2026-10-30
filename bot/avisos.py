"""Deduplicación y redacción de los emails."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import correo
from .db import Historial
from .modelos import Candidato, Oferta
from .tiendas.chollometro import tienda_de

log = logging.getLogger(__name__)

HORAS_HUELLA = 72      # durante cuánto tiempo un aviso tapa al mismo chollo de otra fuente
MARGEN_PRECIO = 0.02   # diferencias de redondeo entre fuentes (Chollometro: "299€")


def tienda_real(o: Oferta) -> str:
    """Quién vende: en Chollometro es la tienda del chollo, no el propio Chollometro."""
    if o.tienda == "chollometro" and o.vendedor:
        return tienda_de(o.vendedor) or o.tienda
    return o.tienda


def huella(c: Candidato) -> dict:
    o = c.oferta
    return {"tienda": tienda_real(o), "clave": c.clave, "categoria": o.categoria,
            "precio": o.precio}


def mismo_chollo(nueva: dict, previa: dict) -> bool:
    """¿Es `nueva` el mismo error de precio que un aviso ya enviado (por otra fuente)?

    Misma tienda vendedora y, o bien misma clave de producto sin bajar más de un 2 %,
    o bien (los títulos de Chollometro no siempre dan clave) misma categoría y el
    mismo precio con un margen del 2 %.
    """
    if nueva["tienda"] != previa.get("tienda"):
        return False
    p, q = nueva["precio"], previa.get("precio") or 0
    if nueva["clave"] and nueva["clave"] == previa.get("clave"):
        return p >= q * (1 - MARGEN_PRECIO)
    return nueva["categoria"] == previa.get("categoria") and abs(p - q) <= q * MARGEN_PRECIO


def es_duplicado(db: Historial, c: Candidato, externos: list[dict] = ()) -> bool:
    """Un aviso por producto y precio; solo se repite si el precio baja más.

    `externos` son las huellas de avisos enviados desde la otra ejecución (Actions o
    la tarea local), para que el mismo chollo no llegue dos veces.
    """
    o = c.oferta
    anterior = db.precio_ultimo_aviso(o.tienda, o.id_tienda)
    if anterior is not None and o.precio >= anterior:
        return True
    desde = (datetime.now(timezone.utc) - timedelta(hours=HORAS_HUELLA)).isoformat()
    previas = db.avisos_desde(desde) + [h for h in externos if h.get("enviado", "") >= desde]
    h = huella(c)
    return any(mismo_chollo(h, p) for p in previas)


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
    db.registrar_aviso(c.oferta.tienda, c.oferta.id_tienda, c.oferta.precio, c.referencia,
                       tienda_real(c.oferta), c.clave, c.oferta.categoria)
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
