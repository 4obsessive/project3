# Deadlock Scouting

Herramienta local (solo en tu ordenador) para:

1. **Scouting de jugadores**: leaderboard de una región, stats del último mes por jugador y héroe, roles, equipos, libres, notas de contacto, climbers y dúos.
2. **Análisis de partidas y equipos**: partidas por ID o JSON, objetivos, Midboss, minimapa, explorador de todos los campos e **informe estadístico de un equipo** a partir de N partidas.

Datos: [deadlock-api.com](https://api.deadlock-api.com/docs).

## Arrancar

Requisitos: Python 3.9 o superior. **No hace falta instalar nada** (solo biblioteca estándar). Los datos del demo (Midboss, KOTH) requieren **Python 3.14 o superior** (`compression.zstd`); con una versión anterior la app funciona igual y esas secciones salen como «no disponible: requiere Python 3.14+».

```bash
python app.py
```

Abre `http://127.0.0.1:8000` y se actualiza sola en segundo plano (la primera vez tarda unos minutos; el progreso se ve arriba a la derecha).

Opciones:

| Comando | Qué hace |
|---|---|
| `python app.py --puerto 8001` | otro puerto |
| `python app.py --sin-actualizar` | no lanza la actualización automática |
| `python app.py --no-abrir` | no abre el navegador |
| `python app.py --importar C:\ruta\scouting.db` | importa campos manuales y snapshots de la versión anterior |
| `python app.py --calibrar` | recalibra el minimapa con las partidas guardadas (no guarda; compara) |

Tests (usan la partida real `match_109084310.json`; sin red):

```bash
python -m unittest discover -s tests -v
```

## Archivos que puedes editar

| Archivo | Para qué |
|---|---|
| `equipos.txt` | Plantillas. Una línea por jugador: uno o varios IDs y el nombre del equipo (`483770846, 802747733 Buff Enjoyers`). IDs: número, `[U:1:N]`, steam64 o URL de perfil. |
| `roles.json` | Tabla héroe → roles y umbral (25 %). También desde la web (Ajustes). |
| `objetivos.json` | Mapeo `team_objective_id` → objetivo y carril. También desde Ajustes. |
| `config.json` | Región, leaderboards extra, intervalo de actualización, días de stats, API key. También desde Ajustes. |
| `static/minimap.json` | Calibración del minimapa (mundo → imagen). |

Los datos se guardan en `data/` (`scouting.db` y `matches/*.json.gz`). Los campos manuales (redes, mayor de edad, estado, notas, equipo) nunca se sobrescriben al actualizar.

## Cómo funciona

- **Actualización** (cada 24 h por defecto, o «Actualizar ahora»): leaderboard de la temporada actual + las extra (por defecto la Beta Season 1) → elección de la cuenta de cada entrada → `equipos.txt` → stats por héroe en lotes de 50 cuentas → nombres de Steam → resúmenes materializados. Si se corta, se reanuda desde donde iba.
- **Elección de cuenta**: cada entrada de la leaderboard trae varias `possible_account_ids` (un nombre puede ser de muchas cuentas). Se elige la de **badge** más alto (`/v1/players/rank`); en empate, la cuyo nombre de Steam coincide y después la de más partidas.
- **Score 0–100**: KDA y winrate suavizados hacia la media (10 partidas ficticias) y pasados a percentil, volumen (log) y flexibilidad. Pesos ajustables en la web.
- **Climbers**: la API no da el ranking pasado; se compara entre snapshots propios, que se acumulan desde la primera descarga.
- **Dúos**: `mate-stats` da las partidas en grupo con cada compañero; si en una partida solo aparece un compañero, era un dúo. El resultado sale del historial de partidas.
- **Informe de equipo**: registro de métricas en `scouting/report/metricas/`. Cada archivo registra una función con `@metric(...)` que devuelve bloques (`text`, `table`, `bars`, `histogram`, `timeline`, `map`, `unavailable`); la web los pinta sin conocer la métrica. Para añadir una métrica, crea un archivo nuevo en esa carpeta. Si una métrica falla, solo falla su sección.
- **Datos del demo**: al guardar una partida se encola en segundo plano (también las ya guardadas sin datos, al arrancar) y un trabajador consulta el demo con SQL (`POST /v1/matches/demo/query`, 3 consultas por partida: rejuvenators, reglas del juego/KOTH y daño al Midboss). Nunca repite una consulta resuelta. Estados por partida: `pending` (en cola), `done`, `nodemo` (la API no tiene el demo; se recuerda y no se reintenta), `error` (tras 5 intentos, reintentos espaciados 600 s × nº de intento) y `unavailable` (Python < 3.14). Presupuesto propio de **150 consultas/h** (el límite de la API es 200/h por IP), persistido en la base de datos; tras un 429 espera ≥ 61 s. Estado en `GET /api/demo/status`. Las vistas nunca esperan al demo: muestran lo de los metadatos y «datos del demo: pendientes/no disponibles».
- **Tiempo y equipos del demo**: segundos de partida = `(tick − ticks en pausa) / 64`. El demo numera los equipos 2 y 3; se mapean a la API: 2 → 0 (Hidden King), 3 → 1 (Archmother).
- **Midboss, rejuvenators y KOTH**: Midboss = `DamageEvent.victim_class = 8`; el equipo que lo inicia es el de más daño, y «robado» es que lo mate el otro. Rejuvenators = `RejuvStatusEvent` con `event_type = 4`. KOTH cash-in = transiciones de `m_nKothScoringTeam`/`m_timeKoth*` en `CCitadelGameRulesProxy` (inicio, quién lo completa y cuándo, o «no completado»).
- **Economía**: almas por fuente (`gold_sources`: Kills, Troopers, Jungla, Objetivos, Tesoro, Asistencias, Denies, Catch-up de equipo, Asesinato por habilidad, Cultist Sacrifice, Rompibles, objetos) y ritmos por minuto por fases (0–10, 10–20, 20+ min). Sale de las muestras `stats` de los metadatos (cada 3–5 min), no del demo: `GoldHistoryEvent` viene vacío y `CurrencyChangedEvent` usa 39 códigos sin documentar. Las fuentes 5, 8, 9, 10 y 13 llevan el nombre de la API, sin confirmar; «Haunts» no tiene correspondencia conocida y no se muestra.
- **Remontada**: un equipo está en remontada cuando su net worth es < 0,9 × el del rival (regla del 10 %), interpolado de las muestras `stats` de los metadatos. Cada Midboss y cada cash-in de KOTH indica si quien lo consigue iba en remontada.
- **Sin interpretaciones**: solo se muestra lo que sale de los datos; lo demás es «no disponible». Se eliminaron el «robo» deducido de `team_claimed`, el contexto ventaja/igualdad/desventaja del Midboss, el MVP estimado (solo con `mvp_rank` de la partida), la «pista» de Comeback Gold Koth como lectura de KOTH y las conclusiones no confirmadas (`confirmed=False`, tipo «interpretación»). Se mantienen la detección del lado y el mapeo de objetivos (editable).
- **Imágenes** (`/img/`): el navegador solo carga recursos de la propia app (CSP), así que el servidor hace de proxy-caché de las imágenes de dos orígenes permitidos, `cdn.deadlock.wiki` y `assets-bucket.deadlock-api.com`. Se guardan en `data/cache/img/` la primera vez que se piden; no se versiona ninguna imagen. Si una no carga, la web muestra un icono o la inicial del héroe.
- **Estilo «City Never Sleeps»** (`static/app.css`, tokens en `:root`): fondo marrón cálido `--bg #1a1310`, texto crema `--text #f3e6cf`, acento naranja `--accent #e0612a`, turquesa `--teal #3fb8a8`, marcos claros `--frame #e9dcc3`; titulares de cartel con una palabra en etiqueta naranja, pasos numerados en círculo turquesa, retratos como cartas inclinadas y mapas en marcos. Sin fuentes externas (pila de sistema); colores de carril y de equipo intactos.
- **Carriles por color**: York (amarillo `#F1CC30`), Broadway (azul `#29b1cc`) y Greenwich (verde `#59b247`), iguales para ambos equipos. Los colores y alias se pueden editar en `objetivos.json` (bloque `colores`).

## Seguridad y privacidad

- Escucha solo en `127.0.0.1`, valida la cabecera `Host` (contra DNS rebinding) y solo acepta escrituras en JSON.
- No hace scraping de datos personales. Redes y mayor de edad se rellenan a mano con lo que el jugador hace público; nunca se guarda la edad exacta.
- Salidas a internet: además de la API de Deadlock, la app descarga imágenes de `cdn.deadlock.wiki` y `assets-bucket.deadlock-api.com`, y los resultados de las consultas del demo de `demo-extracts.deadlock-api.com` (con `User-Agent`). Solo esos tres hosts (lista cerrada) y sin seguir redirecciones. Las imágenes tienen límite de 5 MB y solo se aceptan PNG/JPEG/WebP; los resultados del demo tienen sus propios topes (20 MB comprimido / 100 MB descomprimido). Las peticiones de otros sitios al proxy se rechazan.
- Lo que la API no da (cristales del Midboss, curación por héroe en hero-stats, KOTH/Midboss sin demo…) se muestra como «no disponible».

## Estructura

```
app.py                     arranque
scouting/api.py            cliente de la API (lotes, caché, backoff 429)
scouting/db.py             esquema SQLite
scouting/updater.py        actualización en segundo plano (reanudable)
scouting/summary.py        resúmenes materializados
scouting/players.py        cuentas, fusiones, campos manuales, perfil, dúos
scouting/analysis.py       climbers, plantillas, partidas recientes de un equipo
scouting/matches.py        partidas: guardado, objetivos, Midboss, muertes, posiciones, economía, remontada
scouting/demo.py           datos del demo: cola, presupuesto, consultas SQL, resumen
scouting/minimap.py        imagen, calibración y recalibración
scouting/report/           informe de equipo (registro de métricas)
scouting/server.py         servidor HTTP + API JSON
static/                    web (HTML/CSS/JS); js/map.js es el único módulo de mapa
tests/                     tests con la partida real
```
