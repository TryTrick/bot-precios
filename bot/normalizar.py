"""Normalización de títulos: accesorios, packs, estado y clave de producto.

La clave sirve para emparejar el mismo producto entre tiendas cuando no hay
EAN. Es conservadora: si no se puede construir con seguridad devuelve None
y ese producto no se empareja con nada.
"""
from __future__ import annotations

import re
import unicodedata

from .modelos import NUEVO, REACONDICIONADO


def sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


# --- Accesorios y packs -----------------------------------------------------

# Si el título EMPIEZA por una de estas palabras, es un accesorio.
_ACCESORIO_INICIO = re.compile(
    r"^\s*(funda|carcasa|cargador|protector|cristal|cable|correa|adaptador|soporte|"
    r"estuche|base de carga|lapiz|stylus|teclado|raton|mochila|maletin|skin|"
    r"pegatina|vinilo|repuesto|bateria externa|powerbank|power bank|hub|dock|"
    r"almohadillas|tapones|recambio|mando|volante|tarjeta de memoria|"
    r"tarjeta regalo|suscripcion|bolsa|brazo|pie de monitor|limpiador)\b"
)
# Si el título CONTIENE una de estas expresiones, es un accesorio.
_ACCESORIO_CUALQUIERA = re.compile(
    r"\b(protector de pantalla|cristal templado|compatible con|funda para|"
    r"carcasa para|correa para|cargador para|cable para|repuesto para|"
    r"soporte para|para iphone|para samsung|para galaxy|para ipad|para macbook|"
    r"para apple watch|para airpods|para ps5|para nintendo switch|para xbox)\b"
)
_PACK = re.compile(r"\b(pack|kit|bundle|lote|combo)\b|\s\+\s")

_REACONDICIONADO = re.compile(
    r"\b(reacondicionad[oa]s?|renewed|refurbished|seminuevo|segunda mano|usad[oa]|"
    r"grado [abc]|como nuevo|reacondicionamiento)\b"
)


def es_accesorio(titulo: str) -> bool:
    t = sin_acentos(titulo)
    return bool(_ACCESORIO_INICIO.search(t) or _ACCESORIO_CUALQUIERA.search(t))


def es_pack(titulo: str) -> bool:
    return bool(_PACK.search(sin_acentos(titulo)))


def detectar_estado(titulo: str) -> str:
    return REACONDICIONADO if _REACONDICIONADO.search(sin_acentos(titulo)) else NUEVO


# --- Clave de producto ------------------------------------------------------

MARCAS = {
    "apple", "samsung", "xiaomi", "google", "oneplus", "oppo", "realme", "motorola",
    "honor", "huawei", "nothing", "sony", "lenovo", "asus", "acer", "hp", "dell",
    "msi", "gigabyte", "microsoft", "nintendo", "lg", "aoc", "benq", "philips",
    "nvidia", "amd", "intel", "zotac", "pny", "sapphire", "xfx", "powercolor",
    "garmin", "huawei", "amazfit", "bose", "jbl", "sennheiser", "jabra", "beats",
    "vivo", "tcl", "poco", "redmi", "iiyama", "corsair", "razer", "alienware",
    "valve", "meta", "fitbit", "polar", "suunto", "marshall", "anker", "soundcore",
}
# Algunas marcas se escriben como submarca; se reducen a la principal.
_ALIAS_MARCA = {"poco": "xiaomi", "redmi": "xiaomi", "alienware": "dell", "beats": "apple",
                "soundcore": "anker", "playstation": "sony"}

# Familias que identifican la marca aunque no se escriba.
_FAMILIA_MARCA = {"iphone": "apple", "ipad": "apple", "macbook": "apple", "airpods": "apple",
                  "galaxy": "samsung", "pixel": "google", "ps5": "sony", "ps4": "sony",
                  "playstation": "sony", "xbox": "microsoft", "geforce": "nvidia"}

# Palabras que NO forman parte de la clave: colores, nombres genéricos de
# categoría y relleno comercial. Cualquier otra palabra del modelo cuenta, así
# "Watch Fit 5 Pro" nunca se confunde con "Watch 5 Pro".
_NO_MODELO = set("""
negro negra blanco blanca azul rojo roja verde gris plata plateado oro dorado rosa morado
violeta amarillo naranja beige crema grafito titanio titanium black white blue red green grey
gray silver gold pink purple yellow orange midnight medianoche starlight estelar luz grafite
onyx cobalto marino oscuro claro natural desierto sombra lavanda menta coral cielo noche
movil smartphone telefono libre consola portatil tablet smartwatch reloj inteligente
auriculares monitor gaming tarjeta grafica edition edicion version con de y para el la the
and nuevo new reacondicionado reacondicionada seminuevo excelente muy bueno buen estado
dual sim wifi wi-fi nfc esim galaxy gps
""".split())

# Unidades/especificaciones que se eliminan antes de extraer el modelo.
_RUIDO = re.compile(
    r"\b\d+([.,]\d+)?\s?(mah|hz|mp|w|mm|ghz|nm|cm|kg|pulgadas|\"|''|”)(?=\W|$)|"
    r"\b\d{2,4}\s?g\b|\blte\b|\b202\d\b"  # gramos, pero no "5G"
)
_MM_RELOJ = re.compile(r"\b(\d{2})\s?mm\b")
_LTE_RELOJ = re.compile(r"\b(lte|4g|cel|cellular|celular|gps\s?\+\s?cel\w*)\b")
_CAPACIDAD = re.compile(r"\b(\d+)\s?(gb|tb)\b")
_CAPACIDAD_BARRA = re.compile(r"\b(\d+)\s?(?:gb)?\s?/\s?(\d+)\s?(gb|tb)\b")
_PULGADAS = re.compile(r"\b(\d{2}(?:[.,]\d)?)\s?(?:\"|''|”|pulgadas|\bpulg\b)")
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _capacidades_gb(t: str) -> list[int]:
    caps: list[int] = []
    for a, b, unidad in _CAPACIDAD_BARRA.findall(t):
        caps.append(int(a))
        caps.append(int(b) * (1024 if unidad == "tb" else 1))
    t = _CAPACIDAD_BARRA.sub(" ", t)
    for n, unidad in _CAPACIDAD.findall(t):
        caps.append(int(n) * (1024 if unidad == "tb" else 1))
    return caps


def _cabecera(t: str) -> str:
    """Parte del título que nombra el modelo: quita prefijos tipo 'Móvil - '
    y corta en la primera coma, barra vertical o paréntesis (allí empiezan
    las especificaciones, que cada tienda escribe a su manera)."""
    if " - " in t:
        antes, despues = t.split(" - ", 1)
        if not any(tok in MARCAS or tok in _ALIAS_MARCA for tok in _TOKEN.findall(antes)):
            t = despues
    t = re.split(r"[,|(\[]", t, maxsplit=1)[0]
    t = re.sub(r"(?<=[a-z0-9])\+", " plus", t)  # "S25+" -> "S25 plus"
    return t.replace("playstation 5", "ps5").replace("playstation 4", "ps4")


def detectar_marca(titulo: str, marca: str | None = None) -> str | None:
    if marca:
        m = sin_acentos(marca).strip()
        return _ALIAS_MARCA.get(m, m)
    tokens = _TOKEN.findall(sin_acentos(titulo).replace("+", " "))
    for tok in tokens:
        if tok in MARCAS or tok in _ALIAS_MARCA:
            return _ALIAS_MARCA.get(tok, tok)
    for tok in tokens:  # sin marca escrita: se deduce de la familia
        if tok in _FAMILIA_MARCA:
            return _FAMILIA_MARCA[tok]
    return None


def clave_producto(titulo: str, categoria: str, marca: str | None = None) -> str | None:
    """Devuelve 'categoria|marca|modelo|capacidad' o None si hay dudas."""
    t = sin_acentos(titulo)
    marca_n = detectar_marca(titulo, marca)
    if not marca_n:
        return None

    caps = _capacidades_gb(t)
    pulgadas = _PULGADAS.findall(t)
    t_limpio = _CAPACIDAD_BARRA.sub(" ", _cabecera(t))
    t_limpio = _CAPACIDAD.sub(" ", t_limpio)
    t_limpio = _RUIDO.sub(" ", t_limpio)

    modelo: set[str] = set()
    for tok in _TOKEN.findall(t_limpio):
        if tok in _NO_MODELO or (tok in MARCAS and tok not in _ALIAS_MARCA):
            continue  # la marca va aparte; las submarcas (redmi, poco) sí distinguen
        modelo.add(tok)
    if not any(any(c.isdigit() for c in tok) for tok in modelo):
        return None  # sin número de modelo no hay forma fiable de emparejar

    capacidad = _capacidad_por_categoria(categoria, caps)
    if capacidad is None:
        return None
    if categoria == "monitores" and pulgadas:
        capacidad = pulgadas[0].replace(",", ".") + "in"
    if categoria == "relojes":  # la variante es el tamaño de caja y si lleva LTE
        tam = _MM_RELOJ.findall(t)
        capacidad = (f"{tam[0]}mm" if tam else "") + ("-lte" if _LTE_RELOJ.search(t) else "")
    return "|".join([categoria, marca_n, "-".join(sorted(modelo)), capacidad])


def _capacidad_por_categoria(categoria: str, caps: list[int]) -> str | None:
    """Qué capacidad distingue variantes en cada categoría. '' = no aplica."""
    if categoria in ("moviles", "tablets"):
        almacen = [c for c in caps if c >= 32]
        return f"{max(almacen)}gb" if almacen else None  # sin almacenamiento: dudoso
    if categoria == "portatiles":
        ram = [c for c in caps if c <= 128]
        disco = [c for c in caps if c >= 128]
        if not ram or not disco:
            return None
        return f"{min(ram)}gb-{max(disco)}gb"
    if categoria == "graficas":
        vram = [c for c in caps if c <= 48]
        return f"{max(vram)}gb" if vram else None
    if categoria == "consolas":
        return f"{max(caps)}gb" if caps else ""
    return ""  # auriculares, monitores


def tokens_busqueda(titulo: str) -> list[str]:
    """Tokens normalizados para el buscador de la web."""
    return _TOKEN.findall(sin_acentos(titulo))
