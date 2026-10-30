"""Xiaomi con páginas reales recortadas (tests/fixtures/xiaomi)."""
from pathlib import Path

import httpx
import pytest
import respx

from bot.http import Cliente
from bot.normalizar import clave_producto
from bot.tiendas.xiaomi import PAGINAS, Xiaomi, parsear

FIX = Path(__file__).parent / "fixtures" / "xiaomi"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def html(nombre: str) -> str:
    return (FIX / f"{nombre}.html").read_text(encoding="utf-8")


def test_moviles():
    ofertas = {o.titulo: o for o in parsear(html("mobile"), PAGINAS[0])}
    ultra = ofertas["Xiaomi 17 Ultra (precio desde)"]
    assert ultra.precio == 1199.99 and ultra.en_stock and ultra.categoria == "moviles"
    assert ultra.url == "https://www.mi.com/es/product/xiaomi-17-ultra/"
    # Sin capacidad no se empareja con nada
    assert clave_producto(ultra.titulo, "moviles", "Xiaomi") is None


def test_wearables_reparte_categorias_y_salta_sin_precio():
    ofertas = parsear(html("wearables"), PAGINAS[1])
    cats = {o.titulo: o.categoria for o in ofertas}
    assert cats["Xiaomi Watch 5 (precio desde)"] == "relojes"
    assert cats["REDMI Headphones Neo (precio desde)"] == "auriculares"
    assert "Xiaomi Smart Band 11 NFC (precio desde)" not in cats  # salePrice 0
    assert all(o.precio > 0 for o in ofertas)


def test_web_cambiada():
    with pytest.raises(ValueError):
        parsear("<html></html>", PAGINAS[0])


@respx.mock
async def test_listar_y_ficha():
    respx.get(PAGINAS[0]).mock(return_value=httpx.Response(200, text=html("mobile")))
    respx.get(PAGINAS[1]).mock(return_value=httpx.Response(200, text=html("wearables")))
    http = Cliente(RED)
    tienda = Xiaomi(http, {})
    ofertas = await tienda.listar(["moviles", "relojes"])
    assert {o.categoria for o in ofertas} == {"moviles", "relojes"}
    o = next(o for o in ofertas if o.titulo.startswith("Xiaomi 17 Ultra"))
    assert (await tienda.ficha(o)).precio == 1199.99
    await http.cerrar()
