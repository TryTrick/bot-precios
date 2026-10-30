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

## Fase 2 — Tiendas 🟡
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
- Siguiente: PcComponentes (solo local) → Xiaomi → Apple.

## Fase 3 — Actions + Pages ⏳
## Fase 4 — Web ⏳
## Fase 5 — Verificación ⏳
