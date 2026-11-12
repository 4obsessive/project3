# Deadlock Scouting

Herramienta local (solo en tu ordenador) para:

1. **Scouting de jugadores**: leaderboard de una región, stats del último mes por jugador y héroe, roles, equipos, libres, notas de contacto, climbers y dúos.
2. **Análisis de partidas y equipos**: partidas por ID o JSON, objetivos, Midboss, minimapa, explorador de todos los campos e **informe estadístico de un equipo** a partir de N partidas.

Datos: [deadlock-api.com](https://api.deadlock-api.com/docs).

## Arrancar

Requisitos: Python 3.9 o superior. **No hace falta instalar nada** (solo biblioteca estándar).

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

## Seguridad y privacidad

- Escucha solo en `127.0.0.1`, valida la cabecera `Host` (contra DNS rebinding) y solo acepta escrituras en JSON.
- No hace scraping de datos personales. Redes y mayor de edad se rellenan a mano con lo que el jugador hace público; nunca se guarda la edad exacta.
- Lo que la API no da (KOTH/Rifts, cristales del Midboss, curación por héroe en hero-stats…) se muestra como «no disponible».

## Estructura

```
app.py                     arranque
scouting/api.py            cliente de la API (lotes, caché, backoff 429)
scouting/db.py             esquema SQLite
scouting/updater.py        actualización en segundo plano (reanudable)
scouting/summary.py        resúmenes materializados
scouting/players.py        cuentas, fusiones, campos manuales, perfil, dúos
scouting/analysis.py       climbers, plantillas, partidas recientes de un equipo
scouting/matches.py        partidas: guardado, objetivos, Midboss, muertes, posiciones
scouting/minimap.py        imagen, calibración y recalibración
scouting/report/           informe de equipo (registro de métricas)
scouting/server.py         servidor HTTP + API JSON
static/                    web (HTML/CSS/JS); js/map.js es el único módulo de mapa
tests/                     tests con la partida real
```
