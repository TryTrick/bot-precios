"""Historial en SQLite.

Se guarda como mucho UNA fila de precio por producto y día (la última vista),
así el archivo crece despacio aunque el cron corra cada 15 minutos.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .modelos import Oferta

ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
    tienda TEXT NOT NULL,
    id_tienda TEXT NOT NULL,
    titulo TEXT NOT NULL,
    url TEXT NOT NULL,
    categoria TEXT NOT NULL,
    estado TEXT NOT NULL,
    marca TEXT,
    ean TEXT,
    clave TEXT,
    precio REAL NOT NULL,
    precio_tachado REAL,
    en_stock INTEGER NOT NULL,
    primera_vez TEXT NOT NULL,
    ultima_vez TEXT NOT NULL,
    PRIMARY KEY (tienda, id_tienda)
);
CREATE INDEX IF NOT EXISTS ix_productos_ean ON productos(ean);
CREATE INDEX IF NOT EXISTS ix_productos_clave ON productos(clave);

CREATE TABLE IF NOT EXISTS precios_diarios (
    tienda TEXT NOT NULL,
    id_tienda TEXT NOT NULL,
    dia TEXT NOT NULL,
    precio REAL NOT NULL,
    PRIMARY KEY (tienda, id_tienda, dia)
);

CREATE TABLE IF NOT EXISTS avisos (
    tienda TEXT NOT NULL,
    id_tienda TEXT NOT NULL,
    precio REAL NOT NULL,
    referencia REAL NOT NULL,
    enviado TEXT NOT NULL,
    tienda_real TEXT,   -- quién vende (en Chollometro, la tienda del chollo)
    clave TEXT,
    categoria TEXT
);
CREATE INDEX IF NOT EXISTS ix_avisos ON avisos(tienda, id_tienda);

CREATE TABLE IF NOT EXISTS estado_tiendas (
    tienda TEXT PRIMARY KEY,
    fallos_seguidos INTEGER NOT NULL DEFAULT 0,
    ultimo_ok TEXT,
    ultimo_error TEXT,
    ultimo_email_rota TEXT
);
"""


def hoy() -> str:
    return date.today().isoformat()


class Historial:
    def __init__(self, ruta: Path | str):
        if str(ruta) != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(ruta))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        columnas = {r[1] for r in self.con.execute("PRAGMA table_info(avisos)")}
        for col in ("tienda_real", "clave", "categoria"):  # BD creada antes de estas columnas
            if col not in columnas:
                self.con.execute(f"ALTER TABLE avisos ADD COLUMN {col} TEXT")

    def cerrar(self) -> None:
        self.con.commit()
        self.con.close()

    # --- productos y precios ---------------------------------------------

    def guardar(self, o: Oferta, clave: str | None, dia: str | None = None) -> None:
        dia = dia or hoy()
        self.con.execute(
            """INSERT INTO productos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tienda, id_tienda) DO UPDATE SET
                 titulo=excluded.titulo, url=excluded.url, categoria=excluded.categoria,
                 estado=excluded.estado, marca=excluded.marca,
                 ean=COALESCE(excluded.ean, productos.ean), clave=excluded.clave,
                 precio=excluded.precio, precio_tachado=excluded.precio_tachado,
                 en_stock=excluded.en_stock, ultima_vez=excluded.ultima_vez""",
            (o.tienda, o.id_tienda, o.titulo, o.url, o.categoria, o.estado, o.marca,
             o.ean, clave, o.precio, o.precio_tachado, int(o.en_stock), o.visto, o.visto),
        )
        self.con.execute(
            """INSERT INTO precios_diarios VALUES (?,?,?,?)
               ON CONFLICT(tienda, id_tienda, dia) DO UPDATE SET precio=excluded.precio""",
            (o.tienda, o.id_tienda, dia, o.precio),
        )

    def precios_tienda(self, tienda: str, id_tienda: str, desde: str,
                       hasta_excluido: str | None = None) -> list[float]:
        sql = "SELECT precio FROM precios_diarios WHERE tienda=? AND id_tienda=? AND dia>=?"
        args: list = [tienda, id_tienda, desde]
        if hasta_excluido:
            sql += " AND dia<?"
            args.append(hasta_excluido)
        return [r[0] for r in self.con.execute(sql, args)]

    def equivalentes(self, o: Oferta, clave: str | None) -> list[sqlite3.Row]:
        """Mismo producto (por EAN o clave) y mismo estado en OTRAS tiendas."""
        condiciones, args = [], []
        if o.ean:
            condiciones.append("ean=?")
            args.append(o.ean)
        if clave:
            condiciones.append("clave=?")
            args.append(clave)
        if not condiciones:
            return []
        sql = (f"SELECT * FROM productos WHERE ({' OR '.join(condiciones)}) "
               "AND estado=? AND tienda<>?")
        return list(self.con.execute(sql, [*args, o.estado, o.tienda]))

    def todos_productos(self) -> list[sqlite3.Row]:
        return list(self.con.execute("SELECT * FROM productos"))

    # --- avisos -------------------------------------------------------------

    def precio_ultimo_aviso(self, tienda: str, id_tienda: str) -> float | None:
        r = self.con.execute(
            "SELECT MIN(precio) FROM avisos WHERE tienda=? AND id_tienda=?",
            (tienda, id_tienda)).fetchone()
        return r[0]

    def registrar_aviso(self, tienda: str, id_tienda: str, precio: float, referencia: float,
                        tienda_real: str | None = None, clave: str | None = None,
                        categoria: str | None = None) -> None:
        self.con.execute(
            "INSERT INTO avisos (tienda, id_tienda, precio, referencia, enviado, tienda_real, "
            "clave, categoria) VALUES (?,?,?,?,?,?,?,?)",
            (tienda, id_tienda, precio, referencia, _ahora(), tienda_real or tienda, clave,
             categoria))
        self.con.commit()

    def avisos_desde(self, desde: str) -> list[dict]:
        """Huellas de los avisos enviados desde `desde` (ISO), para compartir y deduplicar."""
        filas = self.con.execute(
            "SELECT COALESCE(tienda_real, tienda) AS tienda, clave, categoria, precio, enviado "
            "FROM avisos WHERE enviado >= ? ORDER BY enviado", (desde,))
        return [dict(f) for f in filas]

    # --- estado de tiendas --------------------------------------------------

    def tienda_ok(self, tienda: str) -> None:
        self.con.execute(
            """INSERT INTO estado_tiendas (tienda, fallos_seguidos, ultimo_ok) VALUES (?,0,?)
               ON CONFLICT(tienda) DO UPDATE SET fallos_seguidos=0, ultimo_ok=excluded.ultimo_ok""",
            (tienda, _ahora()))

    def tienda_fallo(self, tienda: str, error: str) -> int:
        self.con.execute(
            """INSERT INTO estado_tiendas (tienda, fallos_seguidos, ultimo_error) VALUES (?,1,?)
               ON CONFLICT(tienda) DO UPDATE SET fallos_seguidos=fallos_seguidos+1,
               ultimo_error=excluded.ultimo_error""",
            (tienda, error[:500]))
        return self.estado_tienda(tienda)["fallos_seguidos"]

    def estado_tienda(self, tienda: str) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM estado_tiendas WHERE tienda=?",
                                (tienda,)).fetchone()

    def puede_avisar_rota(self, tienda: str, horas: float) -> bool:
        fila = self.estado_tienda(tienda)
        if not fila or not fila["ultimo_email_rota"]:
            return True
        ultimo = datetime.fromisoformat(fila["ultimo_email_rota"])
        return datetime.now(timezone.utc) - ultimo >= timedelta(hours=horas)

    def marcar_email_rota(self, tienda: str) -> None:
        self.con.execute("UPDATE estado_tiendas SET ultimo_email_rota=? WHERE tienda=?",
                         (_ahora(), tienda))
        self.con.commit()


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
