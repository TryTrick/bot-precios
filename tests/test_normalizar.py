import pytest

from bot.normalizar import clave_producto, detectar_estado, es_accesorio, es_pack


@pytest.mark.parametrize("titulo", [
    "Funda para teléfono - SAMSUNG A53 Silicone Cover with Strap",
    "Cargador USB-C 45W Samsung",
    "Protector de pantalla cristal templado iPhone 16 Pro",
    "Correa Apple Watch 45mm Sport",
    "Cable USB-C a Lightning 1m",
    "Carcasa compatible con Galaxy S25 Ultra",
])
def test_accesorios(titulo):
    assert es_accesorio(titulo)


@pytest.mark.parametrize("titulo", [
    "Samsung Galaxy S25 Ultra 12/256GB Titanio Negro Libre",
    "Apple AirPods Pro 2 con estuche de carga MagSafe USB-C",
    "Sony WH-1000XM5 Auriculares inalámbricos",
    "Portátil ASUS Vivobook 15 X1504VA Intel Core i5/16GB/512GB SSD",
])
def test_no_accesorios(titulo):
    assert not es_accesorio(titulo)


def test_pack():
    assert es_pack("Consola PS5 Slim + 2 mandos")
    assert es_pack("Pack Samsung Galaxy S25 + Galaxy Buds")
    assert not es_pack("Samsung Galaxy S25 Ultra 256GB")


def test_estado():
    assert detectar_estado("iPhone 15 128GB Reacondicionado Grado A") == "reacondicionado"
    assert detectar_estado("Apple iPhone 15 128GB (Renewed)") == "reacondicionado"
    assert detectar_estado("Apple iPhone 15 128GB") == "nuevo"


def test_misma_clave_entre_tiendas():
    pcc = clave_producto("Samsung Galaxy S25 Ultra 12/256GB Titanio Negro Libre", "moviles")
    mm = clave_producto("Móvil - SAMSUNG Galaxy S25 Ultra, Titanium Black, 256 GB, 12 GB RAM, "
                        "6.9\" QHD+, Snapdragon 8 Elite", "moviles")
    amz = clave_producto("Samsung Galaxy S25 Ultra (256 GB), Smartphone Android 15 con IA, "
                         "12 GB RAM, Titanio Negro", "moviles")
    assert pcc == mm == amz == "moviles|samsung|s25-ultra|256gb"


@pytest.mark.parametrize("a,b", [
    ("Samsung Galaxy S25 256GB", "Samsung Galaxy S25 Ultra 256GB"),
    ("Samsung Galaxy S25 Ultra 256GB", "Samsung Galaxy S25 Ultra 512GB"),
    ("Apple iPhone 16 Pro 256GB", "Apple iPhone 16 Pro Max 256GB"),
    ("Samsung Galaxy S25+ 256GB", "Samsung Galaxy S25 Plus 512GB"),
])
def test_variantes_distintas(a, b):
    assert clave_producto(a, "moviles") != clave_producto(b, "moviles")


def test_dudoso_sin_clave():
    assert clave_producto("Smartphone libre gama alta 256GB", "moviles") is None  # sin marca
    assert clave_producto("Samsung Galaxy S25 Ultra Titanio", "moviles") is None   # sin capacidad
    assert clave_producto("Portátil HP 15 Intel Core i7", "portatiles") is None   # sin RAM/disco


def test_consolas_ps5():
    assert (clave_producto("Sony PlayStation 5 Slim Digital", "consolas")
            == clave_producto("Consola PS5 Slim Digital Edition", "consolas"))


def test_plus_con_simbolo():
    assert (clave_producto("Samsung Galaxy S25+ 256GB", "moviles")
            == clave_producto("Samsung Galaxy S25 Plus 256GB", "moviles"))
    assert (clave_producto("Samsung Galaxy S25+ 256GB", "moviles")
            != clave_producto("Samsung Galaxy S25 256GB", "moviles"))


def test_grafica():
    assert (clave_producto("MSI GeForce RTX 5070 12GB", "graficas")
            != clave_producto("MSI GeForce RTX 5070 Ti 16GB", "graficas"))
    assert clave_producto("MSI GeForce RTX 5070 Ti Ventus 3X 16GB GDDR7", "graficas").endswith("|16gb")
