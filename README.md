# Rev Nation MX · Editorial Studio (`@revnationmx`)

Estudio web ligero para generar láminas editoriales de Fórmula 1 en formato **Instagram Feed (`4:5`, 1080×1350)** y **Reel / Story (`9:16`, 1080×1920)** con estética Editorial Suiza (*British Racing Green mate + grano analógico + tipografías `Bebas Neue` e `IBM Plex` embebidas*) y datos reales vía **OpenF1** (sin login requerido).

## Modos incluidos
1. **Batalla (Pos + Ritmo):** evolución de posiciones, detección automática de Safety Cars y comparativa de ritmo vuelta a vuelta.
2. **Ritmo Limpio (Stints):** degradación de neumáticos vuelta a vuelta (hasta 4 pilotos, filtrando pits/SC).
3. **Estrategia Top 10:** barras editoriales de compuestos (`SOFT`, `MEDIUM`, `HARD`, `INTER`) del Top 10 de carrera.
4. **Qualy (Mapa + Velocidad):** mapa de dominancia real `(X, Y)` + curva de velocidad en vuelta rápida.

## Despliegue rápido en Docker (Proxmox LXC `103`)

```bash
git clone https://github.com/liciolorenzoni0-commits/revnation-studio.git /opt/revnation-studio
cd /opt/revnation-studio
docker compose up -d --build
```

Abrir en tu red local: `http://<IP-DOCKER>:8505`

## Actualizar a una nueva versión

```bash
cd /opt/revnation-studio && git pull && docker compose up -d --build
```

> El caché de consultas a OpenF1 se guarda en `/opt/revnation-studio/cache` para cargas instantáneas tras la primera consulta de cada GP.
