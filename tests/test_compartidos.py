"""Tarea local: bloqueos sin reintento, avisos compartidos sin duplicados, batería y cerrojo."""
import asyncio
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from bot import avisos, compartidos, correo, exportar
from bot.ciclo import ejecutar
from bot.db import Historial
from bot.http import Bloqueado, Cliente
from bot.modelos import Candidato
from bot.normalizar import clave_producto
from bot.tarea_local import Cerrojo, bateria_suficiente
from bot.tiendas.pccomponentes import PcComponentes
from bot.tiendas.simulada import Simulada

from .conftest import oferta, sembrar

RED = {"pausa_min": 0, "pausa_max": 0, "reintentos": 2}
CLAVE = clave_producto("Samsung Galaxy S25 Ultra 12/512GB", "moviles", "Samsung")


def _ahora(horas_atras: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=horas_atras)).isoformat()


def _huella(**kw) -> dict:
    base = {"tienda": "pccomponentes", "clave": CLAVE, "categoria": "moviles",
            "precio": 299.0, "enviado": _ahora(1)}
    return {**base, **kw}


def _chollo(titulo="Samsung Galaxy S25 Ultra 12/512GB Titanio", precio=299.0,
            vendedor="PcComponentes", id_hilo="123") -> Candidato:
    o = oferta(tienda="chollometro", id_tienda=id_hilo, titulo=titulo, precio=precio,
               vendedor=vendedor, marca=None)
    return Candidato(o, clave_producto(o.titulo, o.categoria), 1449.0, "", 79.0)


# --- bloqueos -----------------------------------------------------------------

@respx.mock
async def test_bloqueo_no_reintenta_ni_vuelve_a_pedir():
    ruta = respx.get(url__startswith="https://www.pccomponentes.com/").mock(
        return_value=httpx.Response(429))
    http = Cliente(RED)
    with pytest.raises(Bloqueado):
        await http.get("https://www.pccomponentes.com/categorias/tablets")
    with pytest.raises(Bloqueado, match="sin más peticiones"):
        await http.get("https://www.pccomponentes.com/categorias/portatiles")
    assert ruta.call_count == 1  # ni reintento ni segunda petición
    await http.cerrar()


@respx.mock
async def test_bloqueo_corta_tambien_las_que_esperaban_turno():
    # Como en PcComponentes: todas las categorías se lanzan a la vez y esperan turno
    async def respuesta_lenta(request):  # como la red real: mientras, las demás hacen cola
        await asyncio.sleep(0.01)
        return httpx.Response(403)

    ruta = respx.get(url__startswith="https://www.pccomponentes.com/").mock(
        side_effect=respuesta_lenta)
    http = Cliente(RED)
    urls = [f"https://www.pccomponentes.com/categorias/{n}" for n in range(8)]
    res = await asyncio.gather(*(http.get(u) for u in urls), return_exceptions=True)
    assert all(isinstance(r, Bloqueado) for r in res)
    assert ruta.call_count == 1
    await http.cerrar()


class _HttpBloqueaTablets:
    async def get(self, url, **kw):
        if "tablets" in url:
            raise Bloqueado("HTTP 403")
        raise ValueError("fuera de rango")  # el resto, vacías


async def test_pccomponentes_un_bloqueo_tumba_el_ciclo(cfg):
    with pytest.raises(Bloqueado):
        await PcComponentes(_HttpBloqueaTablets(), cfg).listar(["moviles", "tablets"])


def test_pausas_por_host_de_config(cfg):
    assert cfg["red"]["pausas_por_host"]["www.pccomponentes.com"][0] >= 5


# --- deduplicación entre fuentes -----------------------------------------------------

def test_mismo_chollo_por_clave_aunque_venga_de_chollometro(db):
    assert avisos.es_duplicado(db, _chollo(), [_huella()])
    assert avisos.es_duplicado(db, _chollo(precio=295), [_huella()])  # redondeo (<2 %)


def test_avisa_si_baja_mas_otra_tienda_o_caducado(db):
    assert not avisos.es_duplicado(db, _chollo(precio=279), [_huella()])
    assert not avisos.es_duplicado(db, _chollo(vendedor="MediaMarkt"), [_huella()])
    assert not avisos.es_duplicado(db, _chollo(), [_huella(enviado=_ahora(80))])


def test_sin_clave_empareja_por_precio_y_categoria(db):
    sin_clave = _chollo(titulo="Chollazo Samsung tope de gama en PcComponentes")
    assert sin_clave.clave is None
    assert avisos.es_duplicado(db, sin_clave, [_huella(precio=299.5)])
    assert not avisos.es_duplicado(db, sin_clave, [_huella(precio=349)])
    assert not avisos.es_duplicado(db, sin_clave, [_huella(categoria="tablets")])


def test_dos_hilos_del_mismo_chollo_un_solo_aviso(db):
    c = _chollo(id_hilo="1")
    db.registrar_aviso("chollometro", "1", 299.0, 1449.0, "pccomponentes", c.clave, "moviles")
    assert avisos.es_duplicado(db, _chollo(id_hilo="2"))


async def test_ciclo_no_repite_lo_que_avisó_la_tarea_local(db, cfg, monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar", lambda a, c: enviados.append(a))
    ref = oferta(tienda="mediamarkt", id_tienda="REF")
    sembrar(db, ref, CLAVE, 1449, dias=5)
    hilo = _chollo().oferta
    await ejecutar(cfg, db, [Simulada(ofertas=[hilo])], externos=[_huella()])
    assert enviados == []
    await ejecutar(cfg, db, [Simulada(ofertas=[hilo])])  # sin el aviso local, sí avisa
    assert len(enviados) == 1


# --- archivo compartido -------------------------------------------------------------

def test_escribir_huellas(tmp_path):
    db = Historial(":memory:")
    db.registrar_aviso("chollometro", "9", 299.0, 1449.0, "pccomponentes", CLAVE, "moviles")
    datos = json.loads(compartidos.escribir(db, tmp_path / "avisos.json", 72))
    assert datos["avisos"][0]["tienda"] == "pccomponentes"
    assert datos["avisos"][0]["clave"] == CLAVE
    db.cerrar()


def test_arbol_nombres_exactos(tmp_path):
    for nombre in ("avisos.json", "tiendas_locales.json"):
        (tmp_path / nombre).write_text("{}", encoding="utf-8")
    arbol = compartidos.arbol_de([tmp_path / "tiendas_locales.json", tmp_path / "avisos.json"])
    # sin retorno de carro al final del nombre
    assert compartidos._git("ls-tree", "--name-only", arbol).split("\n") == [
        "avisos.json", "tiendas_locales.json"]


# --- tiendas locales (PcComponentes) en la web -----------------------------------------

def test_locales_viajan_a_la_web_con_su_hora_y_su_historial(tmp_path, cfg):
    local = Historial(":memory:")
    pcc = oferta(id_tienda="S25U", precio=1724.51, url="https://www.pccomponentes.com/s25u")
    sembrar(local, pcc, CLAVE, 1799, dias=4)
    local.guardar(pcc, CLAVE)
    local.guardar(oferta(id_tienda="VIEJO", visto="2026-01-01T00:00:00+00:00"), CLAVE)
    ruta = tmp_path / "tiendas_locales.json"
    n = compartidos.escribir_locales(local, ruta, {"pccomponentes": {"ok": True, "productos": 1}},
                                     30)
    assert n == 1  # el no visto en 48 h no viaja

    actions = Historial(":memory:")
    estado = compartidos.importar_locales(actions, json.loads(ruta.read_text(encoding="utf-8")))
    assert estado == [{"tienda": "pccomponentes", "ok": True, "productos": 1}]
    web = exportar.construir(actions, {"pccomponentes": "PcComponentes"})
    fila = next(v["n"] for v in web["variantes"] if "s25" in v["k"].split())
    assert (fila["s"], fila["p"], fila["u"]) == ("PcComponentes", 1724.51,
                                                 "https://www.pccomponentes.com/s25u")
    assert fila["v"] == pcc.visto  # hora real de la lectura local, no la de Actions
    assert len(actions.precios_tienda("pccomponentes", "S25U", "2000-01-01")) == 5


def test_importar_recalcula_la_clave(db):
    fila = {"tienda": "pccomponentes", "id_tienda": "1", "url": "u", "categoria": "moviles",
            "estado": "nuevo", "precio": 1724.51, "en_stock": 1, "clave": "moviles|samsung|vieja|1gb",
            "titulo": 'Samsung Galaxy S25 Ultra 5G 12GB 1TB 6,9" Negro Titanio S Pen integrado',
            "primera_vez": "2026-10-30T00:00:00+00:00", "ultima_vez": "2026-10-30T00:00:00+00:00"}
    compartidos.importar_locales(db, {"generado": "", "tiendas": {}, "productos": [fila]})
    assert db.todos_productos()[0]["clave"] == "moviles|samsung|s25-ultra|1024gb"


def test_locales_antiguos_salen_como_caidos(db):
    datos = {"generado": "2026-01-01T00:00:00+00:00", "productos": [],
             "tiendas": {"pccomponentes": {"ok": True, "productos": 300}}}
    assert compartidos.importar_locales(db, datos)[0]["ok"] is False
    assert compartidos.importar_locales(db, None) == []


URL = "https://raw.githubusercontent.com/x/y/datos-local/avisos.json"


@respx.mock
async def test_leer_compartidos():
    http = Cliente(RED)
    respx.get(URL).mock(return_value=httpx.Response(200, json={"avisos": [_huella()]}))
    assert (await compartidos.leer(http, URL))[0]["tienda"] == "pccomponentes"
    respx.get(URL).mock(return_value=httpx.Response(404))
    assert await compartidos.leer(http, URL) == []
    respx.get(URL).mock(side_effect=httpx.ConnectError("sin red"))
    with pytest.raises(compartidos.SinConexion):
        await compartidos.leer(http, URL)
    await http.cerrar()


def test_bd_antigua_gana_columnas(tmp_path):
    ruta = tmp_path / "vieja.sqlite"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE avisos (tienda TEXT NOT NULL, id_tienda TEXT NOT NULL, "
                "precio REAL NOT NULL, referencia REAL NOT NULL, enviado TEXT NOT NULL)")
    con.execute("INSERT INTO avisos VALUES ('mediamarkt','1',300,900,'2026-10-29T10:00:00+00:00')")
    con.commit()
    con.close()
    db = Historial(ruta)
    assert db.avisos_desde("2026-10-01")[0]["tienda"] == "mediamarkt"
    db.cerrar()


# --- condiciones de la tarea --------------------------------------------------

@pytest.mark.parametrize("enchufado, pct, sigue", [
    (False, 19, False), (False, 20, True), (True, 5, True), (None, None, True), (False, None, True),
])
def test_bateria(enchufado, pct, sigue):
    assert bateria_suficiente(enchufado, pct, 20) is sigue


def test_una_sola_instancia(tmp_path):
    a, b = Cerrojo(tmp_path / "x.lock"), Cerrojo(tmp_path / "x.lock")
    assert a.adquirir()
    assert not b.adquirir()
    a.liberar()
    assert b.adquirir()
    b.liberar()


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_prioridad_baja_baja_el_disco():
    codigo = ("import ctypes; from bot.tarea_local import prioridad_baja; assert prioridad_baja(); "
              "v = ctypes.c_ulong(); ctypes.windll.ntdll.NtQueryInformationProcess("
              "ctypes.c_void_p(-1), 33, ctypes.byref(v), 4, None); print(v.value)")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert int(r.stdout) == 0  # prioridad de E/S «muy baja» (2 = normal)


# --- espera creciente tras un bloqueo -------------------------------------------------

def test_espera_crece_y_se_limpia_al_funcionar(tmp_path):
    from bot.tarea_local import Esperas
    ahora = datetime(2026, 10, 31, tzinfo=timezone.utc)
    e = Esperas(tmp_path / "espera.json", 2, 24)
    assert [e.bloqueo("pccomponentes", ahora) for _ in range(6)] == [2, 4, 8, 16, 24, 24]
    e.guardar()
    e = Esperas(tmp_path / "espera.json", 2, 24)  # sobrevive entre ejecuciones
    assert e.hasta("pccomponentes", ahora + timedelta(hours=23))
    assert e.hasta("pccomponentes", ahora + timedelta(hours=25)) is None
    e.funciona("pccomponentes")
    assert e.bloqueo("pccomponentes", ahora) == 2  # vuelve a empezar


def test_espera_a_mano_y_archivo_roto(tmp_path):
    from bot.tarea_local import Esperas
    ruta = tmp_path / "espera.json"
    ruta.write_text("{roto", encoding="utf-8")
    e = Esperas(ruta)
    ahora = datetime(2026, 10, 31, tzinfo=timezone.utc)
    e.esperar("pccomponentes", 6, ahora)
    assert e.hasta("pccomponentes", ahora + timedelta(hours=5, minutes=59))
    assert e.bloqueo("pccomponentes", ahora) == 4  # cuenta como segundo bloqueo


async def test_ciclo_marca_bloqueo(db, cfg, monkeypatch):
    class Bloqueada(Simulada):
        nombre = "bloqueada"

        async def listar(self, categorias):
            raise Bloqueado("HTTP 403")

    monkeypatch.setattr(correo, "enviar", lambda a, c: None)
    r = await ejecutar(cfg, db, [Bloqueada()])
    assert r.tiendas[0].bloqueado and not r.tiendas[0].ok


@respx.mock
async def test_en_espera_no_hace_ni_una_peticion_a_la_tienda(tmp_path, cfg, monkeypatch):
    import argparse
    from bot import __main__ as cli
    from bot.tarea_local import Esperas

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    pcc = respx.get(url__startswith="https://www.pccomponentes.com/")
    e = Esperas(tmp_path / "espera_tiendas.json")
    e.esperar("pccomponentes", 6, datetime.now(timezone.utc))
    e.guardar()
    args = argparse.Namespace(db=str(tmp_path / "h.sqlite"), salida=str(tmp_path / "o.json"),
                              solo=None)
    assert await cli._ciclo(args, cfg, solo_local=True) == 0
    assert pcc.call_count == 0 and not respx.calls  # ni PcComponentes ni nada más
