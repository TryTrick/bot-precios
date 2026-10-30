# bot-precios

Vigila tiendas españolas fiables y hace dos cosas:

1. **Avisa por email de errores de precio.** Si un producto que normalmente vale 700 € o más
   aparece a 330 € o menos, llega un email en el mismo ciclo, con el precio de referencia y el
   enlace directo.
2. **Publica un buscador** en <https://trytrick.github.io/bot-precios/>. Escribes, por ejemplo,
   «samsung s26 ultra» y ves una línea por variante con la oferta más barata: tienda, precio,
   estado (nuevo o reacondicionado), enlace y hora de la última comprobación.

Es gratis: corre en GitHub Actions cada 15 minutos y la web es estática (GitHub Pages).
PcComponentes se vigila además desde tu PC con una tarea programada de Windows
(ver [Tarea local](#tarea-local-pccomponentes)).

## Cómo funciona

```
cron */15 (GitHub Actions)
 ├─ lee las tiendas en paralelo (pocas peticiones, pausas, sin saltarse bloqueos)
 ├─ por cada producto: precio de referencia → ¿cumple la regla? → vuelve a consultar
 │  la ficha para confirmarlo → email (sin repetir avisos)
 ├─ guarda el historial (SQLite) en la rama `datos`
 └─ genera site/ofertas.json y publica la web
```

- **Precio de referencia:** mediana de los precios propios del producto en los últimos 30 días
  (sin contar hoy, con al menos 3 días), combinada con la mediana del mismo producto en las
  demás tiendas. El precio tachado se usa solo como último recurso. Sin referencia no hay
  aviso.
- **Emparejado entre tiendas:** por EAN si existe; si no, por marca, modelo y capacidad.
  Ante la duda no se empareja.
- **Antes de avisar:** se vuelve a consultar la ficha y se comprueba el precio, que lo vende
  la propia tienda, que hay stock, que no es un accesorio ni un pack y que la variante coincide.
- **Sin duplicados:** un aviso por producto y precio, que solo se repite si el precio baja
  más. Actions y la tarea local comparten sus avisos para no mandar dos veces el mismo chollo.
- **Tienda rota:** si una tienda falla o devuelve 0 productos 3 ciclos seguidos, llega un
  email (como mucho uno al día por tienda). El resto de tiendas sigue funcionando.
- **Historial:** un único archivo SQLite con una fila por producto y día. Vive en la rama
  `datos` como un solo commit que se sobrescribe, así el repositorio no engorda. Se eligió
  porque las medianas son una consulta SQL y el archivo se mueve con un solo `git show`.

## Tiendas

| Tienda | Estado | Fuente |
|---|---|---|
| MediaMarkt | ✅ | Datos internos de la página de categoría; solo «vendido por MediaMarkt» |
| Samsung (tienda oficial) | ✅ | API del buscador de su web |
| Apple (tienda oficial) | ✅ iPhone e iPad | Datos de las páginas de compra |
| Xiaomi (tienda oficial) | ⚠️ parcial | Solo el precio «desde» de cada familia |
| PcComponentes | ✅ leída desde tu PC | JSON-LD de los listados (bloquea las IPs de GitHub); sale en la web |
| Chollometro | ✅ solo avisos | RSS de nuevos y populares, filtrado por tiendas fiables |
| Amazon, El Corte Inglés, Fnac, Worten, Carrefour, Back Market | ❌ | Protección anti-bot; solo llegan a través de Chollometro |

## Puesta en marcha

### En GitHub (una vez)

1. **Settings → Secrets and variables → Actions → New repository secret**:
   - `SMTP_USER`: la cuenta de Gmail que envía.
   - `SMTP_PASS`: una **contraseña de aplicación**, no tu contraseña normal. Requiere la
     verificación en 2 pasos activada; se crea en <https://myaccount.google.com/apppasswords>.
   - `EMAIL_TO`: quién recibe los avisos.
2. **Settings → Pages → Source: «GitHub Actions»**.
3. **Settings → Actions → General → Workflow permissions: «Read and write permissions»**.

El workflow `ciclo` se ejecuta solo. También se puede lanzar a mano en
**Actions → ciclo → Run workflow**. Cada run muestra una tabla por tienda en su resumen.

### En local

Necesitas [uv](https://docs.astral.sh/uv/); con `winget install astral-sh.uv` en Windows basta.
uv instala Python 3.12 por su cuenta.

```powershell
copy .env.example .env      # y rellénalo (.env está en .gitignore)
uv run pytest -q            # tests, sin red
uv run python -m bot test-email
uv run python -m bot ciclo  # ciclo completo; historial en datos/, web en site/ofertas.json
uv run python -m bot ciclo --solo mediamarkt
uv run python -m bot ciclo --simular-alerta   # email real marcado [PRUEBA] con un precio falso
uv run python -m bot sonda  # qué tiendas responden desde tu IP
```

Para ver la web en local: `uv run python -m http.server -d site 8000` y abre
<http://127.0.0.1:8000>.

## Cambiar la regla de aviso

Todo está en `config.yaml`; no hace falta tocar el código.

```yaml
aviso:
  modo: precio_final        # o "porcentaje"
  precio_final:
    referencia_min: 700     # el producto vale normalmente al menos esto…
    precio_max: 330         # …y aparece a este precio o menos
  porcentaje:
    caida_min: 50           # % de caída mínima respecto a la referencia
```

Si subes `precio_max`, sube también `rastreo.barrido_hasta`. MediaMarkt se recorre por precio
ascendente hasta ese importe, y es lo que garantiza ver todos los productos que podrían
disparar el aviso. En el mismo archivo están las categorías, las tiendas activas
(`activa: false` desactiva una), las pausas y la concurrencia.

Tras cambiar `config.yaml` en GitHub, el siguiente ciclo ya usa la regla nueva.

## Añadir una tienda

1. Comprueba que responde sin bloqueos (`uv run python -m bot sonda`, añadiendo su URL en
   `bot/sonda.py`) y también desde GitHub (**Actions → sonda → Run workflow**). Si devuelve
   403, CAPTCHA o «Just a moment…», no se puede: el bot no intenta saltarse protecciones.
2. Busca de dónde salen los datos (JSON-LD, estado embebido en la página o API de su propio
   buscador) y guarda una página real en `tests/fixtures/<tienda>/`.
3. Crea `bot/tiendas/<tienda>.py` con una subclase de `Tienda` decorada con `@registrar`:
   - `listar(categorias)` devuelve las `Oferta` de los listados, con `vendido_por_tienda`
     bien rellenado: solo cuentan los productos vendidos por la propia tienda.
   - `ficha(oferta)` vuelve a leer el producto para confirmar antes de avisar.
4. Impórtala en `cargar_todas()` de `bot/tiendas/__init__.py` y actívala en `config.yaml`
   (`solo_local: true` si bloquea las IPs de GitHub).
5. Escribe su test con el fixture (`tests/test_<tienda>.py`) y pasa `uv run pytest -q`.

## Tarea local (PcComponentes)

PcComponentes bloquea las IPs de GitHub, así que se vigila desde tu PC:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1
```

Crea la tarea `bot-precios-local` del Programador de tareas, con este comportamiento:

- Se ejecuta cada 30 minutos mientras tienes la sesión iniciada, sin ventana
  (`conhost --headless`) y con prioridad baja de CPU y disco.
- No empieza si no hay conexión, ni si el portátil va sin cargador por debajo del 20 % de
  batería. Nunca hay dos a la vez.
- Hace unas 28 peticiones con pausas de 5 a 10 segundos (unos 3–4 minutos por ciclo).
- Con un 403, un 429 o una página de reto deja de pedir en ese ciclo y espera al siguiente.
- El log está en `datos\tarea_local.log` (como mucho unos 4 MB, rotando).
- Para pausarla: Programador de tareas → `bot-precios-local` → Deshabilitar. Para quitarla:
  `Unregister-ScheduledTask -TaskName bot-precios-local -Confirm:$false`.

En cada ejecución sube a la rama `datos-local` dos archivos:
- `tiendas_locales.json`: los productos de PcComponentes vistos en las últimas 48 h, con su
  historial de 30 días. Actions los importa en cada ciclo: salen en la web con la hora real
  de la lectura y sirven de referencia para las demás tiendas.
- `avisos.json`: sus avisos, para que Actions no repita el mismo chollo si aparece también en
  Chollometro.

Si tu PC lleva más de 2 horas sin publicar, el pie de la web muestra PcComponentes como «sin
datos». Si lleva más de 48 horas, sus ofertas dejan de mostrarse.

## Limitaciones

- **Seis de las tiendas pedidas no se pueden leer**: El Corte Inglés y Fnac (Akamai); Worten,
  Carrefour y Back Market (Cloudflare); y Amazon (página anti-robot). No se intenta saltar
  esas protecciones. De ellas solo llegan los avisos que alguien publique en Chollometro.
- **Hay muy pocos reacondicionados**, porque Back Market es una de las bloqueadas.
- **PcComponentes depende de tu PC**: solo se actualiza con el PC encendido y la sesión
  iniciada. Sus precios en la web pueden tener hasta 30 minutos más de retraso que los demás.
  Los avisos de PcComponentes los manda tu PC, no Actions. Desde tu IP doméstica también ha
  respondido 403 alguna vez: el bot se detiene en la primera respuesta y lo vuelve a intentar
  al cabo de 30 minutos.
- **Chollometro**: no se puede comprobar si el chollo lo vende la tienda o un vendedor externo.
  El enlace lleva al hilo, no al producto. Su RSS solo cubre la última hora, más o menos.
- **MediaMarkt** no vende ninguna tarjeta gráfica directamente (todas son de vendedores
  externos), así que no hay gráficas en la web. La parte cara del catálogo se recorre por
  turnos y tarda unas horas en verse entera. Los productos de hasta 330 €, que son los que
  pueden disparar un aviso, se revisan en cada ciclo.
- **Xiaomi** solo publica el precio «desde» de cada familia, sin capacidad. Sus productos no
  se emparejan con otras tiendas y casi nunca tendrán referencia.
- **Apple** no da stock por variante. **Samsung** enlaza a la página del modelo, donde se elige
  la capacidad, no a la variante exacta.
- **Productos que ya no venden**: el buscador solo muestra lo que las tiendas vigiladas venden
  ahora. Hoy (30/10/2026), Samsung y MediaMarkt ya solo venden el S26 Ultra; el S25 Ultra
  solo lo tiene PcComponentes.
- **Productos nuevos**: si un producto se estrena con un error de precio y no hay historial
  en ninguna tienda, solo queda el precio tachado como referencia. Si no lo hay, no hay aviso.
  Los primeros días tras la puesta en marcha hay menos referencias.
- **El emparejado es conservador.** Títulos sin capacidad o sin número de modelo no se
  emparejan, y un mismo producto puede salir en dos líneas si cada tienda lo nombra de forma
  distinta. «5G» se ignora al emparejar, así que Redmi 15C y 15C 5G cuentan como el mismo
  producto (su diferencia de precio nunca dispara un aviso).
- **El cron de GitHub no es puntual.** El `*/15` puede retrasarse de 5 a 20 minutos en horas
  punta o saltarse alguna ejecución, y la primera ejecución programada de un workflow nuevo
  tarda en llegar. GitHub desactiva los crons tras 60 días sin actividad en el repositorio; el
  workflow lo evita reactivándose una vez al día.
- **Aún puede llegar un aviso duplicado** si Actions y la tarea local detectan el mismo chollo
  casi a la vez (en el mismo cuarto de hora). Los avisos compartidos se leen con una caché de
  unos 5 minutos.
- **Los precios son orientativos.** Una oferta deja de mostrarse en la web si no se ha visto
  en 48 horas. Compruébala siempre en la tienda.
- **El historial crece** unos 80 bytes por producto y día, sin purga automática: unos 36 MB
  al año con los ~1.200 productos actuales, más si la rotación descubre más catálogo. Habrá
  que recortarlo antes del límite de 100 MB por archivo de GitHub (en 1,5–3 años).
