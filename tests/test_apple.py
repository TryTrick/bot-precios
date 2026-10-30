"""Apple Store con páginas reales recortadas (tests/fixtures/apple)."""
from pathlib import Path

import httpx
import respx

from bot.http import Cliente
from bot.normalizar import clave_producto
from bot.tiendas.apple import WEB, Apple, modelos, parsear

FIX = Path(__file__).parent / "fixtures" / "apple"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def html(nombre: str) -> str:
    return (FIX / f"{nombre}.html").read_text(encoding="utf-8")


def test_indice_descubre_modelos():
    rutas = modelos(html("buy-iphone"), "/es/shop/buy-iphone")
    assert "/es/shop/buy-iphone/iphone-18-pro" in rutas
    assert not any(r.endswith("carrier-offers") for r in rutas)


def test_iphone_pro_y_pro_max_no_se_confunden():
    ofertas = parsear(html("iphone-18-pro"), "u", "moviles")
    titulos = {o.titulo: o.precio for o in ofertas}
    assert titulos["Apple iPhone 18 Pro 256GB"] == 1469.0
    assert titulos["Apple iPhone 18 Pro Max 256GB"] == 1619.0
    assert (clave_producto("Apple iPhone 18 Pro 256GB", "moviles")
            != clave_producto("Apple iPhone 18 Pro Max 256GB", "moviles"))


def test_ipad_variantes():
    claves = {clave_producto(o.titulo, "tablets", "Apple"): o.precio
              for o in parsear(html("ipad-pro"), "u", "tablets")}
    assert len(claves) == 24  # capacidad × tamaño × conexión × acabado
    assert any("cellular" in k for k in claves) and any("11in" in k for k in claves)


def test_pagina_sin_selector():
    assert parsear("<html><title>x</title></html>", "u", "moviles") == []


@respx.mock
async def test_listar_y_ficha():
    respx.get(WEB + "/es/shop/buy-iphone").mock(return_value=httpx.Response(200, text=html("buy-iphone")))
    pro = WEB + "/es/shop/buy-iphone/iphone-18-pro"
    respx.get(pro).mock(return_value=httpx.Response(200, text=html("iphone-18-pro")))
    respx.get(url__startswith=WEB + "/es/shop/buy-iphone/").mock(
        return_value=httpx.Response(200, text="<html></html>"))
    http = Cliente(RED)
    tienda = Apple(http, {})
    ofertas = await tienda.listar(["moviles"])
    o = next(o for o in ofertas if o.titulo == "Apple iPhone 18 Pro Max 512GB")
    assert o.url == pro and (await tienda.ficha(o)).precio == o.precio
    await http.cerrar()
