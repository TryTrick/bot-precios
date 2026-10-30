"""Chollometro con el RSS y un hilo reales (tests/fixtures/chollometro)."""
from pathlib import Path

import httpx
import pytest
import respx

from bot import correo
from bot.ciclo import ejecutar
from bot.http import Cliente
from bot.normalizar import clave_producto
from bot.tiendas.chollometro import (FEEDS, Chollometro, categoria_de, datos_hilo,
                                     parsear_feed, tienda_de)

from .conftest import oferta, sembrar

FIX = Path(__file__).parent / "fixtures" / "chollometro"
RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 0}


def leer(nombre: str) -> str:
    return (FIX / nombre).read_text(encoding="utf-8")


def item(titulo: str, tienda: str, precio: str, id_hilo: str, categoria="Electrónica") -> str:
    """Elemento con el mismo formato que el RSS real."""
    return (f'<item><category><![CDATA[{categoria}]]></category>'
            f'<pepper:merchant name="{tienda}" price="{precio}"/>'
            f'<title><![CDATA[{titulo}]]></title><description><![CDATA[x]]></description>'
            f'<link>https://www.chollometro.com/ofertas/slug-{id_hilo}</link></item>')


def feed(*items: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><rss xmlns:pepper="http://www.pepper.com/rss" '
            'version="2.0"><channel>' + "".join(items) + "</channel></rss>")


def test_feed_real():
    xml = leer("nuevos.xml")
    assert xml.count("<item>") == 30
    ofertas = parsear_feed(xml)
    # Del feed real solo pasa un juego de Switch de Amazon (que luego descarta es_accesorio)
    assert [o.vendedor for o in ofertas] == ["Amazon"]
    assert ofertas[0].precio == 19.49 and ofertas[0].id_tienda == "2049993"


def test_filtros_de_tienda_categoria_y_precio():
    xml = feed(
        item("Samsung Galaxy S25 Ultra 256GB", "Amazon", "299€", "1"),
        item("Samsung Galaxy S25 Ultra 256GB", "Tienda Random", "299€", "2"),  # no fiable
        item("Silla de oficina ergonómica", "Amazon", "99€", "3"),            # no es categoría
        item("iPhone 16 Pro 256GB", "El Corte Inglés", "1.099,90€", "4"),
        item("Portátil ASUS 16GB/512GB", "MediaMarkt", "399€", "5", "Hogar"),  # categoría del feed
    )
    ofertas = {o.id_tienda: o for o in parsear_feed(xml)}
    assert set(ofertas) == {"1", "4"}
    assert ofertas["4"].precio == 1099.90 and ofertas["4"].categoria == "moviles"
    assert set(o.id_tienda for o in parsear_feed(xml, ignorar={"amazon"})) == {"4"}


@pytest.mark.parametrize("titulo,cat", [
    ("PlayStation 5 Slim Digital", "consolas"),
    ("MSI GeForce RTX 5070 Ti 16GB", "graficas"),
    ("Apple MacBook Air M4 16GB 512GB", "portatiles"),
    ("Samsung Galaxy Tab S10 FE", "tablets"),
    ("Garmin Forerunner 265", "relojes"),
    ("Sony WH-1000XM6 auriculares", "auriculares"),
    ("LG UltraGear 27GR95QE monitor OLED", "monitores"),
    ("Xiaomi Redmi Note 15 Pro 256GB", "moviles"),
    ("Freidora de aire Cosori", None),
])
def test_categoria_por_titulo(titulo, cat):
    assert categoria_de(titulo) == cat


def test_nombres_de_tienda():
    assert tienda_de("El Corte Inglés") == "elcorteingles"
    assert tienda_de("Back Market") == "backmarket"
    assert tienda_de("AliExpress") is None


def test_datos_del_hilo_real():
    d = datos_hilo(leer("hilo.html"), "2050000")
    assert d["price"] == 14.87 and d["nextBestPrice"] == 20.99
    assert d["isExpired"] is False and d["merchant"]["merchantName"] == "Amazon"
    assert datos_hilo(leer("hilo.html"), "999") is None


@respx.mock
async def test_ciclo_aviso_via_chollometro(db, cfg, monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar", lambda a, c: enviados.append((a, c)))
    ref = oferta(tienda="mediamarkt", id_tienda="MM1", titulo="Samsung Galaxy S25 Ultra 256GB")
    sembrar(db, ref, clave_producto(ref.titulo, "moviles", "Samsung"), 1299, dias=5)

    respx.get(FEEDS[0]).mock(return_value=httpx.Response(200, text=feed(
        item("Samsung Galaxy S25 Ultra 256GB Titanio Negro", "Amazon", "299€", "2050000"))))
    respx.get(FEEDS[1]).mock(return_value=httpx.Response(200, text=feed()))
    # El hilo real tiene precio 14,87 €: se adapta al caso de prueba (299 €, activo)
    hilo = leer("hilo.html").replace('"price":14.87', '"price":299')
    respx.get("https://www.chollometro.com/ofertas/slug-2050000").mock(
        return_value=httpx.Response(200, text=hilo))

    http = Cliente(RED)
    r = await ejecutar(cfg, db, [Chollometro(http, cfg)])
    await http.cerrar()
    assert r.avisos_enviados == 1
    asunto, cuerpo = enviados[0]
    assert "Amazon (vía Chollometro)" in asunto and "Fuente: Chollometro" in cuerpo
    assert "chollometro" not in {p["tienda"] for p in db.todos_productos()}  # no va al buscador


@respx.mock
async def test_feeds_vacios_es_fallo():
    for u in FEEDS:
        respx.get(u).mock(return_value=httpx.Response(200, text=feed()))
    http = Cliente(RED)
    with pytest.raises(RuntimeError):
        await Chollometro(http, {}).listar(["moviles"])
    await http.cerrar()


@respx.mock
async def test_sin_nada_relevante_no_es_caida(db, cfg):
    respx.get(FEEDS[0]).mock(return_value=httpx.Response(200, text=feed(
        item("Silla de oficina", "Amazon", "99€", "7"))))
    respx.get(FEEDS[1]).mock(return_value=httpx.Response(200, text=feed()))
    http = Cliente(RED)
    r = await ejecutar(cfg, db, [Chollometro(http, cfg)])
    await http.cerrar()
    assert r.tiendas[0].ok and db.estado_tienda("chollometro")["fallos_seguidos"] == 0
