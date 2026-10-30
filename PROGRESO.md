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

## Fase 2 — Tiendas ⏳
Orden revisado: MediaMarkt → Chollometro → Samsung → Xiaomi → Apple; PcComponentes según decisión
del usuario (solo funciona en local).

## Fase 3 — Actions + Pages ⏳
## Fase 4 — Web ⏳
## Fase 5 — Verificación ⏳
