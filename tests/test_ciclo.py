"""Ciclo completo con tiendas falsas (sin red) y el envío de email interceptado."""
import pytest

from bot import correo, exportar
from bot.ciclo import ejecutar
from bot.normalizar import clave_producto
from bot.tiendas.base import Tienda
from bot.tiendas.simulada import Simulada, oferta_falsa

from .conftest import oferta, sembrar


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(correo, "enviar", lambda asunto, cuerpo: lista.append((asunto, cuerpo)))
    return lista


def _sembrar_referencia(db):
    ref = oferta(tienda="pccomponentes", id_tienda="REF")
    sembrar(db, ref, clave_producto(ref.titulo, "moviles", "Samsung"), 1449, dias=5)


async def test_alerta_simulada(db, cfg, enviados):
    _sembrar_referencia(db)
    r = await ejecutar(cfg, db, [Simulada()])
    assert r.avisos_enviados == 1
    asunto, cuerpo = enviados[0]
    assert "299.00 €" in asunto and "Tienda simulada" in asunto and "-79%" in asunto
    assert "1449.00 €" in cuerpo and "https://example.com/prueba" in cuerpo


async def test_sin_duplicados_y_repite_si_baja(db, cfg, enviados):
    _sembrar_referencia(db)
    await ejecutar(cfg, db, [Simulada()])
    await ejecutar(cfg, db, [Simulada()])
    assert len(enviados) == 1
    mas_barata = oferta_falsa()
    mas_barata.precio = 199
    await ejecutar(cfg, db, [Simulada(ofertas=[mas_barata])])
    assert len(enviados) == 2


@pytest.mark.parametrize("cambio,motivo", [
    ({"precio": 1399.0}, "precio cambió"),
    ({"en_stock": False}, "sin stock"),
    ({"vendido_por_tienda": False}, "vendedor externo"),
    ({"titulo": "Samsung Galaxy S25 Ultra 12/256GB"}, "variante"),
    ({"estado": "reacondicionado"}, "estado"),
])
async def test_confirmacion_rechaza(db, cfg, enviados, caplog, cambio, motivo):
    _sembrar_referencia(db)
    o = oferta_falsa()
    ficha = oferta_falsa()
    for k, v in cambio.items():
        setattr(ficha, k, v)
    await ejecutar(cfg, db, [Simulada(ofertas=[o], fichas={o.id_tienda: ficha})])
    assert enviados == []
    assert motivo in caplog.text


async def test_ficha_no_disponible(db, cfg, enviados):
    _sembrar_referencia(db)
    o = oferta_falsa()
    await ejecutar(cfg, db, [Simulada(ofertas=[o], fichas={})])
    assert enviados == []


async def test_vendedor_externo_ni_se_guarda(db, cfg, enviados):
    o = oferta_falsa()
    o.vendido_por_tienda = False
    r = await ejecutar(cfg, db, [Simulada(ofertas=[o])])
    assert r.tiendas[0].descartados == 1 and db.todos_productos() == []


class Rota(Tienda):
    nombre = "rota"
    nombre_visible = "Rota"

    async def listar(self, categorias):
        raise RuntimeError("HTTP 403")

    async def ficha(self, oferta):
        return None


class Vacia(Simulada):
    nombre = "vacia"


async def test_tienda_rota_un_email_al_dia(db, cfg, enviados):
    vacia = Vacia(ofertas=[])
    for _ in range(5):
        r = await ejecutar(cfg, db, [Rota(None), vacia, Simulada()])
    # Simulada sigue funcionando aunque las otras fallen
    assert r.tiendas[2].ok and not r.tiendas[0].ok and r.tiendas[1].error == "0 productos"
    rotas = [a for a, _ in enviados if "Tienda rota" in a]
    assert len(rotas) == 2  # una por tienda, no una por ciclo
    assert db.estado_tienda("rota")["fallos_seguidos"] == 5


async def test_tienda_se_recupera(db, cfg, enviados):
    for _ in range(2):
        await ejecutar(cfg, db, [Rota(None)])
    await ejecutar(cfg, db, [Simulada()])
    assert db.estado_tienda("rota")["fallos_seguidos"] == 2
    assert db.estado_tienda("simulada")["fallos_seguidos"] == 0


def test_exportar_mas_barata_por_variante(db):
    k256 = clave_producto("Samsung Galaxy S25 Ultra 256GB", "moviles")
    k512 = clave_producto("Samsung Galaxy S25 Ultra 512GB", "moviles")
    db.guardar(oferta(tienda="pccomponentes", id_tienda="a", titulo="Samsung Galaxy S25 Ultra 256GB",
                      precio=1100), k256)
    db.guardar(oferta(tienda="mediamarkt", id_tienda="b", titulo="Samsung Galaxy S25 Ultra 256GB",
                      precio=1050), k256)
    db.guardar(oferta(tienda="amazon", id_tienda="c", titulo="Samsung Galaxy S25 Ultra 256GB "
                      "Reacondicionado", precio=800, estado="reacondicionado"), k256)
    db.guardar(oferta(tienda="amazon", id_tienda="d", titulo="Samsung Galaxy S25 Ultra 512GB",
                      precio=1300, en_stock=False), k512)
    datos = exportar.construir(db, {"mediamarkt": "MediaMarkt"})
    assert len(datos["variantes"]) == 1  # la de 512 GB está sin stock
    v = datos["variantes"][0]
    assert v["n"]["p"] == 1050 and v["n"]["s"] == "MediaMarkt"
    assert v["r"]["p"] == 800
