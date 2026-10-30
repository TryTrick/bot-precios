"""MediaMarkt con páginas reales guardadas (tests/fixtures/mediamarkt)."""
from pathlib import Path

import httpx
import pytest
import respx

from bot.http import Cliente
from bot.tiendas.mediamarkt import BASE, MediaMarkt, SinDatos, parsear

FIX = Path(__file__).parent / "fixtures" / "mediamarkt"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def html(nombre: str) -> str:
    return (FIX / f"{nombre}.html").read_text(encoding="utf-8")


def test_listado_filtrado_solo_mediamarkt():
    ofertas, max_pagina = parsear(html("smartphones_mm_precio_asc"), "moviles")
    assert len(ofertas) == 12 and max_pagina == 30
    assert all(o.vendido_por_tienda for o in ofertas)
    primera = ofertas[0]
    assert primera.precio == 139.0 and primera.precio_tachado == 149.0
    assert primera.ean == "6932554444860" and primera.marca == "Xiaomi"
    assert primera.url.startswith("https://www.mediamarkt.es/es/product/")


def test_listado_sin_filtro_detecta_marketplace():
    ofertas, _ = parsear(html("smartphones"), "moviles")
    externos = [o for o in ofertas if not o.vendido_por_tienda]
    assert len(externos) == 3
    s26 = next(o for o in ofertas if o.id_tienda == "1620277")
    assert s26.vendido_por_tienda and s26.en_stock and s26.precio == 1199.0
    assert s26.ean == "8806097821250"


def test_sin_estado_lanza_error():
    with pytest.raises(SinDatos):
        parsear("<html><body>Página nueva</body></html>", "moviles")


@respx.mock
async def test_ficha_devuelve_el_producto_pedido():
    ofertas, _ = parsear(html("smartphones"), "moviles")
    s26 = next(o for o in ofertas if o.id_tienda == "1620277")
    respx.get(s26.url).mock(return_value=httpx.Response(200, text=html("ficha")))
    http = Cliente(RED)
    nueva = await MediaMarkt(http, {}).ficha(s26)
    await http.cerrar()
    assert nueva.id_tienda == "1620277" and nueva.precio == 1199.0


@respx.mock
async def test_barrido_para_al_superar_el_limite():
    url = f"{BASE}/es/category/smartphones-263.html"
    pedidas = []

    def responder(request):
        params = dict(request.url.params)
        pedidas.append((params["sort"], params.get("page", "1")))
        assert params["marketplace"] == "MediaMarkt"
        if params["sort"] == "currentprice asc" and params.get("page", "1") == "1":
            return httpx.Response(200, text=html("smartphones_mm_precio_asc"))  # 139–159 €
        return httpx.Response(200, text=html("smartphones"))  # hasta 1199 €: fin del barrido

    respx.get(url).mock(side_effect=responder)
    http = Cliente(RED)
    cfg = {"rastreo": {"barrido_hasta": 330, "max_paginas_barrido": 15, "paginas_rotacion": 1}}
    ofertas = await MediaMarkt(http, cfg).listar(["moviles", "graficas"])
    await http.cerrar()
    asc = [p for p in pedidas if p[0] == "currentprice asc"]
    desc = [p for p in pedidas if p[0] == "currentprice desc"]
    assert asc == [("currentprice asc", "1"), ("currentprice asc", "2")]
    assert len(desc) == 1  # una página de rotación
    assert len({o.id_tienda for o in ofertas}) == len(ofertas) >= 20  # sin duplicados


@respx.mock
async def test_categoria_caida_no_tumba_la_tienda():
    respx.get(f"{BASE}/es/category/smartphones-263.html").mock(
        return_value=httpx.Response(200, text=html("smartphones")))
    respx.get(f"{BASE}/es/category/tablets-169.html").mock(return_value=httpx.Response(403))
    http = Cliente(RED)
    ofertas = await MediaMarkt(http, {}).listar(["moviles", "tablets"])
    await http.cerrar()
    assert ofertas
