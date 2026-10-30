"""Samsung con respuestas reales de su API (tests/fixtures/samsung)."""
import json
from pathlib import Path

import httpx
import pytest
import respx

from bot.http import Cliente
from bot.normalizar import clave_producto
from bot.tiendas.samsung import API, Samsung, parsear

FIX = Path(__file__).parent / "fixtures" / "samsung"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def datos(nombre: str) -> dict:
    return json.loads((FIX / f"{nombre}.json").read_text(encoding="utf-8"))


def test_moviles():
    ofertas = parsear(datos("moviles"), "moviles")
    assert len(ofertas) == 108  # los 102 modelos "learnMore" sin precio se ignoran
    s26 = next(o for o in ofertas if o.id_tienda == "SM-S948BZKGEUB")
    assert s26.titulo == "Samsung Galaxy S26 Ultra 512 GB"
    assert s26.precio == 1319.0 and s26.precio_tachado == 1748.99
    assert s26.en_stock and s26.vendido_por_tienda
    assert s26.url == "https://www.samsung.com/es/smartphones/galaxy-s26-ultra/"
    assert any(not o.en_stock for o in ofertas)


def test_misma_clave_que_mediamarkt():
    s26 = next(o for o in parsear(datos("moviles"), "moviles") if o.id_tienda == "SM-S948BZKDEUB")
    mm = "Samsung Galaxy S26 Ultra, Negro, 256 GB, 12 GB RAM, 6.9\" QHD+, Snapdragon 8 Elite Gen 5"
    assert clave_producto(s26.titulo, "moviles", "Samsung") == clave_producto(mm, "moviles", "Samsung")


def test_edicion_exclusiva_es_el_mismo_producto():
    t = {o.titulo for o in parsear(datos("moviles"), "moviles")}
    assert "Samsung Galaxy Z Fold8 Exclusivo Online 1 TB" in t
    assert (clave_producto("Samsung Galaxy Z Fold8 Exclusivo Online 1 TB", "moviles")
            == clave_producto("Samsung Galaxy Z Fold8 1 TB", "moviles"))


def test_auriculares():
    ofertas = parsear(datos("audio"), "auriculares")
    assert ofertas and all(o.titulo.startswith("Samsung Galaxy Buds") for o in ofertas)


def test_respuesta_rota():
    with pytest.raises(ValueError):
        parsear({"response": {"statusCode": 400, "resultData": None}}, "moviles")


@respx.mock
async def test_listar_y_ficha():
    def responder(request):
        tipo = request.url.params["type"]
        assert request.url.params["num"] == "100" and request.url.params["siteCode"] == "es"
        if tipo == "01010000":
            return httpx.Response(200, json=datos("moviles"))
        if tipo == "01040000":
            return httpx.Response(200, json=datos("audio"))
        return httpx.Response(500)

    respx.get(API).mock(side_effect=responder)
    http = Cliente(RED)
    tienda = Samsung(http, {})
    ofertas = await tienda.listar(["moviles", "auriculares", "tablets"])  # tablets falla
    s26 = next(o for o in ofertas if o.id_tienda == "SM-S948BZKGEUB")
    assert (await tienda.ficha(s26)).precio == 1319.0
    await http.cerrar()
