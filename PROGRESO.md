# Progreso

## Fase 0 — Análisis y plan ✅ (29/10/2026)
Tabla de viabilidad en el plan. Viables desde IP doméstica: PcComponentes, MediaMarkt, Samsung,
Chollometro RSS (`/rss/nuevos`), Amazon (riesgo de CAPTCHA en Actions). Pendientes de investigar:
Apple, Xiaomi. Bloquean (Akamai/Cloudflare): El Corte Inglés, Fnac, Worten, Carrefour, Back Market.
URLs verificadas: PcC `/categorias/portatiles` (JSON-LD con `seller`), MM
`/es/category/smartphones-263.html?sort=currentprice+asc` (JSON-LD + `__PRELOADED_STATE__`
con `marketplaceSeller`/`onlineStatus`).

## Fase 1 — Núcleo ✅ (30/10/2026)
- Módulos: modelos, db (SQLite), normalizar/clave, referencia, reglas (2 modos), confirmar,
  avisos (dedup + tienda rota 1/día), correo SMTP, http, ciclo async, exportar JSON, CLI,
  tienda `simulada`, `sonda`. 44 tests en verde con Python 3.12 (uv).
- Email real: `test-email` y `--simular-alerta` enviados OK.
- Repo: https://github.com/TryTrick/bot-precios (identidad git local: TryTrick noreply).
  `.env` ignorado; comprobado que ningún valor del `.env` está en los archivos subidos.
- Sonda en Actions (run 41112806123), resultado leído por la API pública de anotaciones:
  - OK desde Actions: MediaMarkt, Samsung, Chollometro, Apple, Xiaomi.
  - **PcComponentes: 403 Cloudflare desde Actions** (en local sí funciona).
  - Amazon 503 (anti-robot) en local y en Actions → descartado salvo vía Chollometro.
  - ECI, Fnac, Worten, Carrefour, Back Market: 403 desde Actions.
- Leer resultado de un run: `GET /repos/TryTrick/bot-precios/actions/runs?head_sha=<sha>` →
  jobs → `check-runs/<id>/annotations` (sin token).

## Fase 2 — Tiendas ✅ (30/10/2026)
### MediaMarkt ✅
- `bot/tiendas/mediamarkt.py`: parsea `__PRELOADED_STATE__` (Apollo) en listado y ficha; EAN en el
  100 % de productos. Filtro `?marketplace=MediaMarkt`; `sort=currentprice asc` barrido hasta
  `rastreo.barrido_hasta` (330 €, máx. 15 págs.) + 1 pág. de rotación `currentprice desc`.
  12 productos/pág., máx. 30 págs. Categorías del sitemap oficial.
- Sin gráficas: las 470 son de marketplace. Ciclo real: 66 peticiones, 688 productos, 137 s.
- Fixtures recortados (solo entradas que usa el parser) + 6 tests (respx para paginación).
- Cambio en `clave_producto`: conserva todas las palabras del modelo salvo `_NO_MODELO`
  (colores, genéricas); relojes por tamaño mm + LTE; "5G" distingue modelos.
Orden revisado: MediaMarkt → Chollometro → Samsung → Xiaomi → Apple; PcComponentes: decisión del
usuario = solo local (`solo_local: true` en config.yaml; se salta si `GITHUB_ACTIONS=true`).

### Chollometro ✅
- `bot/tiendas/chollometro.py`: RSS `/rss/nuevos` + `/rss/hot` (30 elementos c/u, ~50 min, sin
  paginación). Filtra tiendas fiables (`pepper:merchant`), categoría del feed y categoría deducida
  del título. Ignora tiendas ya vigiladas directamente. Solo avisos (`solo_avisos`), no buscador.
- Reconsulta: JSON del hilo (`threadId`, `price`, `nextBestPrice`, `isExpired`, `status`), solo
  para precios ≤ `barrido_hasta`. `nextBestPrice` = precio tachado (último recurso).
- Enlace del aviso = hilo de Chollometro (la URL de la tienda no se publica). No se puede verificar
  el vendedor (nota en el email). Fuente solo-avisos vacía ≠ caída.

### Samsung ✅
- `bot/tiendas/samsung.py`: API de su buscador `searchapi.samsung.com/v6/front/b2c/product/finder/hybris`
  (`newhybris`/`gpv2` no traen precio). `type` = `pfCategoryTypeCode` de cada página all-…
  (móviles 01010000, tablets 01020000, relojes 01030000, audio 01040000, portátiles 03010000,
  monitores 07010000). `num=100` → 1 petición por categoría. Capacidad desde `fmyChipList`.
- Ciclo real MM + Chollometro + Samsung: 75 peticiones, 134 s, 864 productos, 8 claves emparejadas
  entre tiendas en el primer ciclo (crecerá con la rotación).

### PcComponentes ✅ (solo local)
- `bot/tiendas/pccomponentes.py`: JSON-LD `ItemList` (40/pág., `offers.seller.name`) y ficha
  `product` (`gtin13`, `itemCondition`, `offers.offers.offeredBy`). `?sort=` verificado:
  price_asc/price_desc/sales/activation_date; `?page=N`.
- Sin filtro de vendedor en URL; por precio ascendente solo salen externos → sin barrido:
  ventas + novedades + 1 pág. rotación price_desc. Consolas: `videoconsolas-ps5`, `-nintendo-switch-2`
  (xbox sin listado). Ciclo local: 27 peticiones, 54 s, ~400 productos propios.

### Xiaomi ✅ (parcial)
- `bot/tiendas/xiaomi.py`: precios por variante solo vía JS/API no visible en el HTML. Se usan
  los bloques `goods` de `__PRELOADED_STATE__` en `/es/mobile/` y `/es/wearables/` (2 peticiones):
  precio «desde» por familia, sin capacidad → título con «(precio desde)», clave None.

### Apple ✅ (iPhone e iPad)
- `bot/tiendas/apple.py`: índices `/es/shop/buy-iphone` y `/es/shop/buy-ipad` → páginas de modelo
  con `productSelectionData` (`products` + `displayValues.prices[].amountBeforeTradeIn`).
  Títulos desde claves internas (`256gb`→256GB, `wificell`→Wi-Fi + Cellular, `13inch`→13in); si la
  opción de tamaño nombra el modelo («iPhone 18 Pro Max») se usa como modelo. Sin stock por ref.
- Arreglado: «Wi-Fi + Cellular»/«GPS + Cellular» ya no cuenta como pack.

### Ciclo local completo (6 tiendas)
- 117 peticiones, 136 s, ~1.465 productos válidos, 0 caídas. 89 tests.
- En Actions: sin PcComponentes (solo_local) → ~90 peticiones; MediaMarkt marca el tiempo (~135 s).

## Fase 3 — Actions + Pages ✅ (primer run 30/10/2026 OK, rama `datos` y web publicadas)
- `.github/workflows/ciclo.yml`: cron */15, workflow_dispatch y push (bot/, site/, config).
  `concurrency: ciclo`. Historial: `git show FETCH_HEAD:historial.sqlite` de la rama `datos` y
  force-push de un commit único al terminar. Pages con upload-pages-artifact + deploy-pages
  (job `publicar`). Keepalive: el primer run programado tras las 00:00 UTC llama a
  `PUT .../actions/workflows/ciclo.yml/enable`. Resumen por tienda en GITHUB_STEP_SUMMARY.
- Secrets y Pages configurados por el usuario. Web: https://trytrick.github.io/bot-precios/

## Fase 4 — Web ✅
- `site/index.html`, `estilo.css`, `app.js` (~9 KB, sin frameworks, modo oscuro, móvil).
  Términos con números = coincidencia exacta; solo letras = prefijo. Ordena por precio, una
  línea por variante (clave), interruptor de reacondicionados, consulta en el `#hash`.
- Decisión: «5G»/«4G» ya no forman parte de la clave (S26 Ultra salía duplicado PcC/Samsung).

### Tarea local de PcComponentes (opción B, elegida por el usuario) ✅
- Tarea de Windows `bot-precios-local` (`scripts/instalar_tarea.ps1`): cada 30 min,
  `conhost --headless uv run python -m bot tarea-local`, una instancia (IgnoreNew + cerrojo
  en `datos/tarea_local.lock`), solo con red, límite 20 min. Log: `datos/tarea_local.log`.
- `bot/tarea_local.py`: sin cargador y batería < 20 % → no empieza. Sin conexión → no empieza
  (y no cuenta como tienda caída).
- Pausas de 5–10 s para www.pccomponentes.com (`red.pausas_por_host`). Tras un 403/429/reto el
  cliente no vuelve a pedir nada a ese host en el ciclo; PcComponentes cuenta como caída.
- Sin duplicados entre Actions y local (`bot/compartidos.py`): cada aviso guarda su huella
  (tienda vendedora, clave, categoría, precio). Actions las publica en `datos/avisos.json`; la
  tarea local en la rama `avisos-local` (solo si avisa). Cada lado lee las del otro antes de
  avisar. Mismo chollo = misma tienda + (misma clave sin bajar >2 %, o misma categoría y precio ±2 %),
  72 h. Límite: si ambos lo detectan en el mismo cuarto de hora pueden llegar dos.
- La opción C (subir los datos de PcComponentes a la web) queda para más adelante.

## Fase 5 — Verificación ⏳
