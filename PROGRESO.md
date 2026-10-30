# Progreso

## Fase 0 — Análisis y plan ✅ (29/10/2026)
Tabla de viabilidad en el plan. Viables desde IP doméstica: PcComponentes, MediaMarkt, Samsung,
Chollometro RSS (`/rss/nuevos`), Amazon (riesgo de CAPTCHA en Actions). Pendientes de investigar:
Apple, Xiaomi. Bloquean (Akamai/Cloudflare): El Corte Inglés, Fnac, Worten, Carrefour, Back Market.
URLs verificadas: PcC `/categorias/portatiles` (JSON-LD con `seller`), MM
`/es/category/smartphones-263.html?sort=currentprice+asc` (JSON-LD + `__PRELOADED_STATE__`
con `marketplaceSeller`/`onlineStatus`).

## Fase 1 — Núcleo 🟡 (código y tests hechos; falta email real y repo)
- Hecho: modelos, db (SQLite), normalizar/clave, referencia, reglas (2 modos), confirmar,
  avisos (dedup + tienda rota 1/día), correo SMTP, http (límites/pausas/Bloqueado), ciclo
  async, exportar JSON, CLI, tienda `simulada`. 44 tests en verde.
- Comando `sonda` + workflow `sonda.yml`. Sonda local 19:14: Carrefour respondió 200 (antes 403
  → intermitente, reevaluar en fase 2); Amazon dio 503 (su página anti-robot) → poco fiable.
- Pendiente: usuario instala uv, crea `.env`, `test-email` + `--simular-alerta` con email real;
  crear repo en GitHub, primer push, workflow `sonda.yml` para probar tiendas desde Actions.

## Fase 2 — Tiendas ⏳
Orden: PcComponentes → MediaMarkt → Chollometro → Samsung → Amazon → Apple → Xiaomi.

## Fase 3 — Actions + Pages ⏳
## Fase 4 — Web ⏳
## Fase 5 — Verificación ⏳
