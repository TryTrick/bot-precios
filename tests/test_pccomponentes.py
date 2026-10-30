"""PcComponentes con páginas reales recortadas (tests/fixtures/pccomponentes)."""
from pathlib import Path

import httpx
import pytest
import respx

from bot.http import Cliente
from bot.tiendas.pccomponentes import BASE, PcComponentes, parsear_ficha, parsear_listado

FIX = Path(__file__).parent / "fixtures" / "pccomponentes"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def html(nombre: str) -> str:
    return (FIX / f"{nombre}.html").read_text(encoding="utf-8")


def test_listado_distingue_vendedor():
    ofertas = parsear_listado(html("moviles_ventas"), "moviles")
    assert len(ofertas) == 40
    propias = [o for o in ofertas if o.vendido_por_tienda]
    assert len(propias) == 27 and len(ofertas) - len(propias) == 13
    assert all(o.url.startswith(BASE) and o.precio > 0 for o in ofertas)


def test_ficha():
    o = parsear_ficha(html("ficha"), "moviles")
    assert o.titulo.startswith("Apple iPhone 17 Pro Max 256 GB")
    assert o.precio == 1379.0 and o.ean == "0195950639018" and o.id_tienda == "10952781"
    assert o.vendido_por_tienda and o.en_stock and o.estado == "nuevo"


def test_web_cambiada():
    with pytest.raises(ValueError):
        parsear_listado("<html></html>", "moviles")
    assert parsear_ficha("<html></html>", "moviles") is None


@respx.mock
async def test_listar_pide_ventas_novedades_y_rotacion():
    pedidas = []

    def responder(request):
        pedidas.append(request.url.params["sort"])
        return httpx.Response(200, text=html("moviles_ventas"))

    respx.get(f"{BASE}/categorias/smartphone-moviles").mock(side_effect=responder)
    http = Cliente(RED)
    ofertas = await PcComponentes(http, {}).listar(["moviles"])
    await http.cerrar()
    assert sorted(pedidas) == ["activation_date", "price_desc", "sales"]
    assert len(ofertas) == 40  # sin duplicados entre las tres páginas
