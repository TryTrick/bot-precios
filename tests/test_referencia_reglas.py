from bot import referencia, reglas
from bot.normalizar import clave_producto

from .conftest import oferta, sembrar


def _clave(o):
    return clave_producto(o.titulo, o.categoria, o.marca)


def test_sin_historial_ni_tachado(db, cfg):
    o = oferta(precio=299)
    assert referencia.calcular(db, o, _clave(o), cfg["referencia"])[0] is None


def test_tachado_como_ultimo_recurso(db, cfg):
    o = oferta(precio=299, precio_tachado=1500)
    ref, expl = referencia.calcular(db, o, _clave(o), cfg["referencia"])
    assert ref == 1500 and "tachado" in expl


def test_historial_propio_minimo_dias(db, cfg):
    o = oferta()
    sembrar(db, o, _clave(o), 1400, dias=2)  # menos que min_dias_propios (3)
    assert referencia.calcular(db, oferta(precio=299), _clave(o), cfg["referencia"])[0] is None
    sembrar(db, o, _clave(o), 1400, dias=5)
    assert referencia.calcular(db, oferta(precio=299), _clave(o), cfg["referencia"])[0] == 1400


def test_hoy_no_cuenta_en_historial_propio(db, cfg):
    o = oferta()
    sembrar(db, o, _clave(o), 1400, dias=3)
    db.guardar(oferta(precio=100), _clave(o))  # error de hoy ya guardado en otro ciclo
    assert referencia.calcular(db, oferta(precio=100), _clave(o), cfg["referencia"])[0] == 1400


def test_combina_con_otras_tiendas(db, cfg):
    propia = oferta(tienda="mediamarkt", id_tienda="MM1")
    otra = oferta(tienda="pccomponentes", id_tienda="PC1")
    tercera = oferta(tienda="amazon", id_tienda="B0X")
    k = _clave(propia)
    sembrar(db, propia, k, 1300, dias=5)
    sembrar(db, otra, k, 1400, dias=5)
    sembrar(db, tercera, k, 1500, dias=5)
    ref, expl = referencia.calcular(db, oferta(tienda="mediamarkt", id_tienda="MM1", precio=299),
                                    k, cfg["referencia"])
    assert ref == 1400
    assert "pccomponentes" in expl and "amazon" in expl


def test_otras_tiendas_sin_historial_propio(db, cfg):
    otra = oferta(tienda="pccomponentes", id_tienda="PC1")
    k = _clave(otra)
    sembrar(db, otra, k, 1449, dias=2)
    nueva = oferta(tienda="mediamarkt", id_tienda="MM9", precio=299)
    assert referencia.calcular(db, nueva, k, cfg["referencia"])[0] == 1449


def test_reacondicionado_no_compara_con_nuevo(db, cfg):
    nuevo = oferta(tienda="pccomponentes", id_tienda="PC1")
    k = _clave(nuevo)
    sembrar(db, nuevo, k, 1449, dias=5)
    reac = oferta(tienda="amazon", id_tienda="R1", precio=299, estado="reacondicionado")
    assert referencia.calcular(db, reac, k, cfg["referencia"])[0] is None


def test_regla_precio_final(cfg):
    a = cfg["aviso"]
    assert reglas.cumple(330, 700, a)
    assert not reglas.cumple(331, 2000, a)
    assert not reglas.cumple(300, 699, a)
    assert not reglas.cumple(300, None, a)


def test_regla_porcentaje(cfg):
    a = cfg["aviso"]
    a["modo"] = "porcentaje"
    assert reglas.cumple(500, 1000, a)
    assert not reglas.cumple(501, 1000, a)
    assert reglas.cumple(100, 200, a)  # no exige referencia mínima
    assert reglas.descuento_pct(299, 1449) == 79.4
