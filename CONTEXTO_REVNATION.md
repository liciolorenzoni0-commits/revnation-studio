# Contexto del Proyecto · Rev Nation MX (`@revnationmx`)

Guía viva de referencia para cualquier chat o proyecto en Antigravity conectado a `liciolorenzoni0-commits/revnation-studio`.

---

## 1. Identidad de Marca y Línea Visual (Aprobada — Cero AI Slop)

* **Marca:** `@revnationmx` (Instagram / Threads) · **Web / Data Hub:** `liciolorenzoni.tech/f1` (HTML estático servido en `nginx`).
* **Enfoque editorial:** Noticias y análisis de F1 en español basados en datos reales ("desde el taller, sin humo"), con radar especial a pilotos México/LATAM (**Checo Pérez #11**, **Franco Colapinto #43**) y el **GP de la Ciudad de México**.
* **Paleta oficial (Editorial Suizo Motorsport):**
  * Fondo principal **British Racing Green mate:** `#0D2017` *(variantes permitidas: Racing Moss `#08150F`, Papel Crema Editorial `#F3EDE0`, Carbón Mate `#121417`)*
  * Tinta principal (crema/hueso): `#F3EDE0`
  * Tinta secundaria (salvia apagado): `#94A89B`
  * Líneas divisoras suizas (`1px`): `#274133`
  * Acento racing / incidentes: `#E63935`
* **Tipografías embebidas en `static/fonts/`:**
  * Titulares y cifras grandes: **`Bebas Neue`** (mayúsculas condensadas)
  * Etiquetas, ejes, métricas y colofón: **`IBM Plex Mono`**
  * Bajadas y notas cortas: **`IBM Plex Sans`**
* **Reglas estrictas Anti-AI-Slop:**
  1. **NO usar cajas redondeadas repetidas**, ni *pills* rojas tipo dashboard genérico, ni cajitas con borde alrededor de anotaciones o leyendas.
  2. **Etiquetas directas al final de cada curva** (`VER P1`, `RUS P9`, `ANT P4`) en lugar de cajas de leyenda.
  3. **Retícula suiza limpia:** márgenes simétricos (`72px` en lienzo de `1080px`), líneas finas de `1px`, columnas abiertas para estadísticas al pie y espacio negativo generoso.
  4. **Grano analógico sutil** sobre el fondo mate para quitar el acabado plástico digital.
  5. **Formatos de salida:** `4:5` Feed Instagram (`1080×1350`) y `9:16` Reel/Story (`1080×1920`, respetando zonas seguras arriba `155px` y abajo `210px`).

---

## 2. Datos F1: Hallazgo FastF1 (Octubre 2026) + Solución OpenF1

* **Cambio oficial de F1 (15 oct 2026):** `livetiming.formula1.com/static/` ahora exige cuenta **F1TV Access** (`F1_USERNAME` y `F1_PASSWORD` en `fastf1 >= 3.9.0`). Sin login, `fastf1` solo entrega calendario y resultados oficiales vía `jolpica-f1`.
* **Solución gratuita y sin login (usada en este repo):** **OpenF1 (`https://api.openf1.org/v1`)** provee gratis y sin autenticación:
  * `/sessions`, `/drivers`, `/laps`, `/position`, `/stints`, `/pit`, `/race_control`, `/weather`, `/car_data` (velocidad, acelerador, freno, marcha, RPM) y `/location` (coordenadas `X, Y` del trazado).
* **Buenas prácticas OpenF1:**
  * Cachear todas las respuestas en disco (`CACHE_DIR`) para recargas instantáneas y no disparar rate-limits (`HTTP 429`).
  * Descargar `location` solo **1 vez por sesión** (para el mapa del circuito) y aplicar backoff suave si aparece `429`.

---

## 3. Estructura de este Repositorio

* [`app.py`](./app.py) — Backend **FastAPI** ligero (sin `numpy`/`matplotlib` para mantener la imagen Docker ~160 MB) con endpoints:
  * `GET /api/health`
  * `GET /api/meetings?year=2026`
  * `GET /api/race/{session_key}` (pilotos, vueltas, posiciones, stints, Safety Cars, incidentes)
  * `GET /api/qualy_drivers/{session_key}`
  * `GET /api/qualy_compare/{session_key}?driver_a=12&driver_b=3` (telemetría + mapa `X, Y`)
* [`static/index.html`](./static/index.html) — **Estudio Editorial interactivo** en `<canvas>` `1080px` con 4 modos (`Batalla`, `Ritmo Limpio`, `Estrategia Top 10`, `Qualy Mapa + Velocidad`), textos editables en vivo y exportación directa a PNG.
* [`static/fonts/`](./static/fonts/) — Fuentes TTF locales (`Bebas Neue`, `IBM Plex Sans`, `IBM Plex Mono`) para render 100% offline/LAN.
* [`scripts/fetch_gp_data.py`](./scripts/fetch_gp_data.py) — Extractor combinado **FastF1 + OpenF1** para generar datasets JSON locales o dashboards estáticos para `liciolorenzoni.tech/f1`.
* [`scripts/make_editorial_poster.py`](./scripts/make_editorial_poster.py) — Generador Python batch (`matplotlib` + `Pillow` + grano analógico) para producir pósters `1080×1350` desde consola/cron.

---

## 4. Infraestructura y Preferencias de Trabajo (Homelab Proxmox)

* **Host Proxmox correcto:** `pve-desktop` (`https://192.168.68.202:8006`). **Nunca mezclar con `pve-thinkpad`.**
* **Contenedor Docker:** LXC `103` (`192.168.68.61`), directorio dedicado **`/opt/revnation-studio`**, puerto **`8505`** (`http://192.168.68.61:8505`).
* **Regla de oro:** Mantener `/opt/revnation-studio` **100% separado** de `/opt/media-stack` (nunca recrear ni tocar `gluetun`/`qbittorrent`).
* **Estilo de instrucciones preferido por Licio:** indicar primero `📍 Dónde` se ejecuta cada paso, dar comandos de **una sola línea listos para copiar y pegar**, seguidos de **Qué debe salir**.

### Comando de actualización en Proxmox (`pve-desktop` → `>_ Shell`)
```bash
pct exec 103 -- bash -c "cd /opt/revnation-studio && git pull && docker compose up -d --build && sleep 3 && curl -s http://localhost:8505/api/health && echo ''"
```
