# bot-precios

Monitor de errores de precio en tiendas españolas + buscador estático en GitHub Pages.
Plan aprobado: `C:\Users\llove\.claude\plans\pasted-content-id-1aad-vas-a-twinkly-truffle.md`. Estado: `PROGRESO.md`.

## Comandos
- Tests: `uv run pytest -q` (sin red; solo fixtures en `tests/fixtures/<tienda>/`)
- Ciclo local: `uv run python -m bot ciclo` (BD `datos/historial.sqlite`, salida `site/ofertas.json`)
- Una tienda: `uv run python -m bot ciclo --solo pccomponentes`
- Alerta simulada (email real con [PRUEBA]): `uv run python -m bot ciclo --simular-alerta`
- Email de prueba: `uv run python -m bot test-email`
- Tarea local (PcComponentes, sin ventana): `uv run python -m bot tarea-local`; se instala con
  `scripts/instalar_tarea.ps1` (tarea de Windows `bot-precios-local`, log `datos/tarea_local.log`); publica en la rama
  `datos-local` lo que Actions importa para la web (`bot/compartidos.py`)

## Convenciones
- Código, comentarios, logs y mensajes en español. Python 3.12, async con httpx, parser selectolax.
- Secretos solo en `.env` (ignorado) o GitHub Secrets: `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`.
- Todo lo ajustable va en `config.yaml` (regla de aviso, tiendas activas, red).
- Tienda nueva: módulo en `bot/tiendas/` con subclase de `Tienda` (`listar`, `ficha`), decorada con
  `@registrar`, importada en `tiendas/__init__.py:cargar_todas`, activada en `config.yaml`, con
  fixture real guardado y su test. Solo productos vendidos por la tienda (`vendido_por_tienda`).
- No inventar URLs/selectores: verificar con curl y guardar el HTML/JSON real como fixture.
- No saltarse CAPTCHAs ni retos anti-bot: 403/429/reto → `http.Bloqueado` → tienda caída
  (en local, además, espera creciente en `datos/espera_tiendas.json`).
- **No lanzar a mano nada que haga peticiones a PcComponentes sin preguntar al usuario.** Para
  probar: tests, fixtures o datos guardados.
- Una fila de precio por producto y día (`precios_diarios`); la referencia excluye el día de hoy
  del historial propio.
- Emparejado conservador (`normalizar.clave_producto`): ante la duda devuelve None.
