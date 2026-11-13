# Deadlock Scouting

Herramienta local (solo en tu ordenador) para:

1. **Scouting de jugadores**: leaderboard de una región, stats del último mes por jugador y héroe, roles, equipos, libres, notas de contacto, climbers y dúos.
2. **Análisis de partidas y equipos**: partidas por ID o JSON, objetivos, Midboss, minimapa, explorador de todos los campos e **informe estadístico de un equipo** a partir de N partidas.

**La interfaz web está toda en inglés** (este README y HANDOFF.md siguen en español, son para quien desarrolla). Datos: [deadlock-api.com](https://api.deadlock-api.com/docs).

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
- **Datos del demo**: al guardar una partida se encola en segundo plano (también las ya guardadas sin datos, al arrancar) y un trabajador consulta el demo con SQL (`POST /v1/matches/demo/query`, 4 consultas por partida: rejuvenators, reglas del juego/KOTH, daño al Midboss y daño entre héroes en la fase de líneas). Nunca repite una consulta resuelta. Estados por partida: `pending` (en cola), `done`, `nodemo` (la API no tiene el demo; se recuerda y no se reintenta), `error` (tras 5 intentos, reintentos espaciados 600 s × nº de intento) y `unavailable` (Python < 3.14). Presupuesto propio de **150 consultas/h** (el límite de la API es 200/h por IP; con 4 consultas por partida salen ~37 partidas/h), persistido en la base de datos; tras un 429 espera ≥ 61 s. Estado en `GET /api/demo/status`. Las vistas nunca esperan al demo: muestran lo de los metadatos y «datos del demo: pendientes/no disponibles».
- **Tiempo y equipos del demo**: segundos de partida = `(tick − ticks en pausa) / 64`. El demo numera los equipos 2 y 3; se mapean a la API: 2 → 0 (Hidden King), 3 → 1 (Archmother).
- **Midboss, rejuvenators y KOTH**: Midboss = `DamageEvent.victim_class = 8`; el equipo que lo inicia es el de más daño, y «robado» es que lo mate el otro. Rejuvenators = `RejuvStatusEvent` con `event_type = 4`. KOTH cash-in = transiciones de `m_nKothScoringTeam`/`m_timeKoth*` en `CCitadelGameRulesProxy` (inicio, quién lo completa y cuándo, o «no completado»).
- **Economía**: almas por fuente (`gold_sources`: Kills, Troopers, Jungla, Objetivos, Tesoro, Asistencias, Denies, Catch-up de equipo, Asesinato por habilidad, Cultist Sacrifice, Rompibles, objetos) y ritmos por minuto por fases (0–10, 10–20, 20+ min). Sale de las muestras `stats` de los metadatos (cada 3–5 min), no del demo: `GoldHistoryEvent` viene vacío y `CurrencyChangedEvent` usa 39 códigos sin documentar. Las fuentes 5, 8, 9, 10 y 13 llevan el nombre de la API, sin confirmar; «Haunts» no tiene correspondencia conocida y no se muestra.
- **Remontada**: un equipo está en remontada cuando su net worth es < 0,9 × el del rival (regla del 10 %), interpolado de las muestras `stats` de los metadatos. Cada Midboss y cada cash-in de KOTH indica si quien lo consigue iba en remontada.
- **Sin interpretaciones**: solo se muestra lo que sale de los datos; lo demás es «no disponible». Se eliminaron el «robo» deducido de `team_claimed`, el contexto ventaja/igualdad/desventaja del Midboss, el MVP estimado (solo con `mvp_rank` de la partida), la «pista» de Comeback Gold Koth como lectura de KOTH y las conclusiones no confirmadas (`confirmed=False`, tipo «interpretación»). Se mantienen la detección del lado y el mapeo de objetivos (editable).
- **Fase de líneas (min 0–10)**: `scouting/lanes.py` deduce la línea de cada jugador de sus **posiciones** (mediana de las posiciones vivas entre 60 y 300 s, recorrido más cercano de `lane_paths.json`), no de `assigned_lane`, que no es fiable (jugadores con la misma línea asignada juegan en lados opuestos). Si no salen 2 jugadores por equipo y línea, la línea es «no disponible» en esa partida y no se fuerzan dúos. `scouting/lanephase.py` calcula por línea y dúo (pareja de héroes): daño hecho y recibido de héroes hasta el 600 s (inclusive), qué dúo tira antes el Guardian rival y cuál pierde antes el suyo (aunque sea después del 10), y los **gankeos**.
- **Gankeo**: daño > 0 o kill de un jugador cuya línea es otra a un jugador de esa línea, entre 60 y 600 s (antes todos van de camino). Es un episodio por mismo atacante y misma línea de la víctima; los golpes separados menos de 30 s se unen en uno. El daño entre rivales de la misma línea no cuenta. El informe separa daño a los rivales de la línea, recibido de ellos y recibido de gankeos.
- **Consulta nueva y relleno**: el daño entre héroes con su segundo sale de una 4.ª consulta al demo (`lane_damage`, tramos de 5 s). `LANE_TICK_LIMIT = (600 + 3600) * 64` ticks: 600 s de juego más hasta 1 h de pausas. El límite usado se guarda con las filas (`lane_damage_limit`; las filas antiguas, sin él, se consultaron con 48000, que solo cubre ~150 s de pausas). Si con las pausas de la partida el límite no llega a 600 s de juego, el daño del demo está incompleto y la partida cuenta como sin demo (modo aprox., con aviso «demo incompleto» en la vista y en el informe). Las partidas ya `done` solo piden esa consulta (1 POST cada una, sin repetir las otras tres; los resultados crudos ya se guardan) y van detrás de las nuevas: si hay una nueva pendiente y no caben sus 4 POST, el trabajador espera en vez de rellenar. Estado propio `lane_state`: `ok`, `nodemo` (sin demo, no se reintenta), `vacio` (la consulta no devolvió filas; no se guarda ni se reintenta) o `error`.
- **Sin demo («aprox.»)**: el daño de la fase de líneas se interpola al 600 s desde las muestras `stats` (`player_damage`/`player_damage_taken`), sin separar gankeos de daño de línea; los gankeos (recuentos y primer gankeo) salen «–», no disponibles, porque necesitan el demo. Cada bloque dice su fuente y en cuántas partidas. En el informe las medias de daño y la tabla/hallazgos de primer gankeo usan solo partidas con demo; las aproximadas no se mezclan.
- **Desglose por jugador** (`scouting/playerstats.py`): héroes, línea, KDA, dónde muere y mata (celdas de la **posición de muerte de la víctima**, con la base propia siempre abajo), farm, economía, daño hecho/recibido y números de la fase de líneas. El informe (`m07_fase_lineas.py`, `m08_jugadores.py`) suma las partidas del equipo analizado con su `n`; la vista de una partida tiene las pestañas **«Laning phase»** y **«Players»** con los mismos bloques para esa partida (ambos equipos, 6 dúos, 12 jugadores).
- **Nombre del jugador**: nombre en la app (`display_name` del jugador, con sus cuentas enlazadas), después nombre de Steam, y por último el `account_id`.
- **Interfaz en inglés**: todas las vistas, el informe, hallazgos, avisos y errores visibles están en inglés, con formato en-US (números y fechas). Rutas: `#home`, `#players`, `#hero`, `#climbers`, `#teams`, `#matches`, `#report`, `#settings` (los enlaces antiguos en español siguen funcionando). Los valores guardados en la base de datos (estado, mayor de edad) siguen en español internamente y se muestran con etiqueta en inglés. `tests/test_ui_english.py` y `tests/test_report_english.py` vigilan que no queden textos en español.
- **Peleas de objetivo** (`scouting/fights.py`): cada kill/muerte (posición = donde murió la víctima) se clasifica como `midboss`, `koth`, `rest` o `unknown`. Midboss: a ≤ `MIDBOSS_RADIUS` (2500) del pozo (0, 0) y en [primer daño al Midboss (`t_first`), su muerte + `AFTER_S` (60 s)]; sin demo, [muerte − 60 s, muerte + 60 s] con `mid_boss[].destroyed_time_s`. KOTH: a ≤ `RIFT_RADIUS` (2000) de alguna grieta (±7648, 0) y en [inicio del cash-in, `end_t` + 60 s]; solo con demo (`koth_known`), sin demo no se marca ninguna pelea KOTH y la partida se excluye de las cifras «sin peleas de objetivo». Cash-in abandonado: `end_t` es el primer cierre observado (`koth_start` vuelve a 0 sin equipo anotador); si no hay, regla fija `KOTH_OPEN_S` (60) + 60 s = 120 s desde el inicio. Si cae en ambas ventanas, gana el objetivo más cercano. Sin posición → `unknown` (cuenta en totales, no en mapas ni en «resto»). El resumen del demo es `SUMMARY_VERSION = 3`; las partidas con resumen anterior se recalculan desde los datos crudos.
- **Kills/muertes sin peleas de objetivo**: el informe (m02 mapa y m08 jugadores) y la vista de partida (pestaña «Players» con el desglose y los mapas sin peleas de objetivo, y casilla «Exclude objective fights» en la pestaña «Minimap») muestran mapas y tablas de zonas también solo con «resto», más el desglose midboss / KOTH / resto / sin posición. Los campos `*_rest` de `playerstats` y los bloques `rest_map` salen de los mismos datos en informe y partida.
- **Estilo visual**: tarjetas destacadas con imagen, columna de héroes con retratos, iconos de objetivo y barras dentro de las celdas para comparar números; sin quitar ninguna cifra. Mismas imágenes del proxy `/img/` (sin hosts nuevos).
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
scouting/demo.py           datos del demo: cola, presupuesto, consultas SQL, resumen, relleno de lane_damage
scouting/lanes.py          línea de cada jugador por posiciones (lane_paths.json)
scouting/lanephase.py      fase de líneas: dúos, daño, Guardians, gankeos
scouting/playerstats.py    desglose por jugador (zonas de muerte/kill, farm, economía, «resto»)
scouting/fights.py         clasifica kills/muertes: midboss, KOTH, resto, desconocida
scouting/minimap.py        imagen, calibración y recalibración
scouting/report/           informe de equipo (registro de métricas)
scouting/server.py         servidor HTTP + API JSON
static/                    web (HTML/CSS/JS); js/map.js es el único módulo de mapa
tests/                     tests con la partida real
```
