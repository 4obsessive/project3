# Deadlock Scouting — especificación para construir desde cero

Proyecto nuevo. No hay código previo que conservar: este documento recoge **qué hay que construir**, **lo que ya se sabe con certeza** de la API y de las partidas (verificado con datos reales en una iteración anterior) y **qué hay que verificar**. Úsalo como fuente de verdad; donde diga "sin verificar", compruébalo en vivo antes de construir encima.

Usuario: habla español, uso personal, en su ordenador (`localhost`). La interfaz puede estar en inglés; mensajes de terminal y documentación en español.

---

## 1. Objetivo

Una herramienta local con dos partes:

1. **Scouting de jugadores**: bajar la leaderboard de Deadlock (región Europa, entera), enriquecer cada jugador con sus stats y roles, marcar quién está en un equipo y quién está libre, y gestionar notas de contacto.
2. **Análisis de partidas y equipos**: cargar partidas por ID, ver objetivos, Midboss y posiciones sobre el minimapa, y generar un **informe estadístico de un equipo** a partir de N partidas suyas.

Arranque con **un solo comando** (p. ej. `python app.py`) que abre una web en `http://127.0.0.1:8000` y se actualiza sola en segundo plano.

---

## 2. Funcionalidades (por prioridad)

### Fase 1 — base de datos y scouting
- **Leaderboard completa** de una región (`Europe` por defecto). Guardar cada descarga como *snapshot* (para tendencias y climbers).
- **Stats del último mes** por jugador (30 días): partidas, winrate, KD, KDA, daño, objetivos, y **todos los héroes jugados** con sus stats (no solo el top 5).
- **Roles** por jugador a partir de sus héroes del mes (tabla de la sección 6). Un jugador puede tener varios roles si cada uno pesa ≥25 % de sus partidas. Mostrar el desglose (ej. `catcher 94% · carry 3%`).
- **Cuentas múltiples**: un mismo jugador puede tener varias cuentas; se enlazan y sus stats se suman.
- **Equipos** desde `equipos.txt` (formato en sección 7). Vista de **libres** vs **con equipo**.
- **Campos manuales** por jugador que nunca se sobrescriben al actualizar: Twitter/X, Twitch, Discord, mayor de edad (`sí/no/desconocido`, nunca la edad exacta), estado (`pendiente, en seguimiento, contactado, en prueba, fichado, descartado`), notas, equipo.
- **Auto-actualización** cada 24 h (configurable) en segundo plano, con el progreso visible en la web, y botón "Actualizar ahora". Reanudable si falla a mitad.

### Fase 2 — vistas de scouting en la web
- **Jugadores**: tabla ordenable y filtrable (texto, libres/con equipo, rol, partidas mínimas del mes, nuevos en 7/30 días).
- **Fiabilidad** según partidas del mes: Alta ≥25, Media 10–24, Baja <10.
- **Score 0–100** con pesos ajustables por el usuario (KDA, winrate, volumen de partidas, flexibilidad = 1 − cuota del héroe principal). Suavizar KDA y winrate hacia la media cuando hay pocas partidas para que una muestra pequeña no gane.
- **Por héroe**: eliges un héroe y ves los mejores jugadores con él (KDA, KD, winrate, partidas). Mostrar **mínimo 30 jugadores**: empezar exigiendo 15 partidas con ese héroe y bajar el mínimo solo si hace falta, avisando de cuánto se ha bajado.
- **Climbers**: quién más sube en la leaderboard en 7/14/30 días comparando snapshots (solo los que suben; aparte, los nuevos en el ranking). Avisar si aún no hay historial suficiente: **la API no da el ranking pasado**, se acumula desde la primera descarga.
- **Perfil de jugador** (panel lateral): stats, top 5 héroes del mes, otras cuentas, enlace a Steam (`https://steamcommunity.com/profiles/[U:1:<account_id>]`), **tendencias** (rank, KDA y winrate en el tiempo) y **top 5 dúos** (sección 4), más edición de los campos manuales.

### Fase 3 — partidas
- Cargar una partida por **ID** (desde la API) o **subiendo su JSON**. Guardarla.
- **Objetivos**: tabla por equipo con el minuto en que cae cada Guardian, Walker, Base guardian, Shrine, Titan y Core (con "primer golpe" si no cayó), línea de tiempo y CSV.
- **Midboss**: quién lo mata, quién lo reclama y cuándo.
- **Minimapa**: posiciones de los jugadores (calor por equipo) y muertes (✕) sobre la imagen del mapa, con filtros por equipo, jugador y minuto. Exportar PNG.
- **Explorador** de todos los campos de la partida (tablas automáticas a partir de las listas del JSON, gráficas, búsqueda), porque el usuario quiere poder analizar todo lo que trae.

### Fase 4 — informe de equipo
Especificación completa del usuario en la sección 9. Entrada: un equipo (de `equipos.txt` + cuentas extra) y N partidas; el lado (Hidden King / Archmother) se **detecta** por qué jugadores de la plantilla hay en cada equipo, con opción manual.

---

## 3. API — deadlock-api.com

Base `https://api.deadlock-api.com` · Docs OpenAPI en `/docs` · API key opcional en cabecera `X-API-KEY` (más margen de rate limit) · Devuelve **429** con rate limit (respetar `Retry-After`, backoff).

**Lección aprendida:** pedir stats jugador a jugador es lentísimo (30 min para 25 jugadores). Pedir siempre **en lote** (`account_ids` separados por comas, ~50 por petición).

| Endpoint | Para qué | Estado |
|---|---|---|
| `GET /v1/leaderboard/{region}?leaderboard_id=` | Ranking | **Verificado (2026-11-12)**. Regiones: `Europe, Asia, NAmerica, SAmerica, Oceania`. Cada entrada: `account_name`, `possible_account_ids` (**lista**, a veces de 50+ cuentas o vacía), `rank` (= posición), `top_hero_ids` (vacío en ~la mitad desde 2026-07-31). Sin `leaderboard_id` devuelve la **temporada actual** (Beta Season 2, `1002`, empezó el 2026-11-05): solo 61 entradas en Europa (Asia 12, NAmerica 76, SAmerica 1, Oceania 6), porque la temporada acaba de empezar. `leaderboard_id=1001` (Beta Season 1) devuelve **1000** en Europa. Las temporadas e IDs salen de `GET /v1/assets/ranked-seasons`. Valve la actualiza cada hora. |
| `GET /v1/players/rank?account_ids=` | Badge actual por cuenta (para elegir la cuenta) | **Verificado**. `badge` (tier·10+subtier, p. ej. 112), hasta 1000 cuentas por petición. **Límite: 10 000 cuentas/min y 100 000/h por IP** (cada cuenta del lote cuenta, y las peticiones rechazadas con 429 **también** cuentan: tras un 429 hay que esperar la ventana de 60 s entera). Regla de elección que funciona: badge más alto; en empate, nombre de Steam = nombre de la leaderboard y después más partidas en 30 días. Ej.: MikaelS → `385814004` (badge 112, 462 partidas), no `1074124575` (badge 94). Season 1 Europa: ~42 000 candidatas para 1000 nombres (~5 min la primera vez; luego se cachea). |
| `GET /v1/players/hero-stats?account_ids=a,b,c&min_unix_timestamp=T` | Stats por héroe, en lote y por fecha | **Verificado**. Hasta 1000 cuentas (50 → 2 s; 400 → 13 s). Campos: `matches_played, wins, kills, deaths, assists, total_player_damage, total_player_damage_taken, total_boss_damage, total_creep_damage, total_neutral_damage, time_played, last_played`, por minuto (`damage_per_min, obj_damage_per_min, networth_per_min, …`), `accuracy, crit_shot_rate, mvp_rank_counts, matches` (lista de IDs). **No hay ningún campo de curación.** Daño a objetivos solo como `obj_damage_per_min` (y `total_boss_damage`). |
| `GET /v1/players/{id}/mate-stats?same_party=true&min_unix_timestamp=T` | Compañeros de grupo | **Verificado**: `mate_id, wins, matches_played, matches` (**sí trae la lista de IDs**) → el dúo real se deduce (partida en la que ese compañero era el único otro miembro del grupo). El winrate del dúo sale de `match-history` (`match_result` = equipo ganador; victoria si `match_result == player_team`). |
| `GET /v1/players/{id}/match-history` | Historial de partidas | **Verificado**: `match_id, start_time, hero_id, player_team, match_result, player_kills/deaths/assists, net_worth, match_duration_s, player_match_outcome`… Sirve para buscar partidas recientes de un equipo. |
| `GET /v1/players/steam?account_ids=` | Nombres de Steam | **Verificado**: `personaname, profileurl, avatar*, countrycode, realname, friends[], matches_played_last_30d`. Pesado (~3 KB/cuenta por la lista de amigos): solo se usa para cuentas sin nombre y desempates. No se guardan `realname` ni `countrycode` (privacidad). |
| `GET /v1/assets/heroes` | id → nombre de héroe | Funciona. Filtrar `player_selectable && !disabled`. Todos los héroes de la tabla de roles existen. |
| `GET /v1/assets/map` | Minimapa | **Verificado**: `radius` 10752, imágenes (el PNG `minimap_midtown_mid.png` es la misma imagen que el AVIF del usuario: coincidencia 99,92 %), `objective_positions` (`team0_tier1_1/3/4`, `tier2_…`, `titan`, `core`) y campamentos con posición de mundo **y** relativa → calibración oficial exacta (sección 5). |
| `GET /v1/assets/generic-data` | Datos varios | `map_districts`: Hidden King = distrito *amber*, Archmother = *sapphire*. No relaciona distrito con equipo 0/1. |
| `GET /v1/players/{id}/mmr-history` | Historial de MMR | Marcado como obsoleto, ~20 req/min, da puntos y no posición. No usar para climbers. |
| `GET /v1/matches/{id}/metadata` | Partida completa (~1,3 MB) | **Verificado** con la partida `109084310`. Límite "from S3" 100 req/10 s. |

Statlocker no tiene API pública útil; usa los mismos datos.

---

## 4. Estructura verificada de una partida

Todo bajo `match_info`:

- `match_id`, `duration_s`, `winning_team` (0/1), `start_time`, `game_mode`, `match_mode`.
- `players[]`: `player_slot`, `team`, `account_id`, `hero_id`, `kills`, `deaths`, `assists`…
  - `stats[]`: muestras cada pocos minutos con `time_stamp_s`, `net_worth`, `gold_sources[]` (`source`, `gold`…), `custom_user_stats[]` (`id`, `value`).
  - `death_details[]`: `game_time_s`, `death_pos {x,y,z}`, `killer_pos {x,y,z}`, `killer_player_slot`.
  - `power_up_buffs[]`, `items[]`, etc.
- `objectives[]`: `team` (= **dueño** del objetivo; lo destruye el rival), `team_objective_id`, `legacy_objective_id`, `destroyed_time_s` (0 = no cayó), `first_damage_time_s`, `creep_damage`.
- `mid_boss[]`: `team_killed`, `team_claimed`, `destroyed_time_s`. El significado exacto de `team_claimed` no está documentado (interpretación: si lo reclama quien no lo mató, es un robo).
- `custom_user_stats[]` (catálogo `id` → `name`), incluye **"Comeback Gold Koth"**.
- `match_paths`: `interval_s` (1), `x_resolution`/`y_resolution` (16383), `paths[]` con `player_slot`, `x_min`, `x_max`, `y_min`, `y_max`, `x_pos[]`, `y_pos[]`, `health[]`, `combat_type[]`, `move_type[]`.
  - **Decodificación**: `x = x_min + x_pos / x_resolution * (x_max - x_min)` (igual en y). Una posición por segundo. Verificado contra las posiciones de muerte (error mediano ~184 u en un mundo de ~20 000 u).
  - **`health == 0` = muerto**, y su posición queda aparcada fuera del mapa: filtrarla siempre.

### Mapeo de `team_objective_id` (inferido; encaja con los tiempos reales)
| ID | Objetivo |
|---|---|
| 0 | Core (fin de partida) |
| 1–4 | Guardian, carril 1–4 |
| 5–8 | Walker, carril 1–4 |
| 9 | Titan |
| 10–11 | Shrines (shield generators) 1–2 |
| 12–15 | Base guardians (barrack bosses), carril 1–4 |

En el mapa actual de 3 carriles faltan 2, 6 y 13 (carril 2). Verificar con más partidas y permitir corregir el mapeo desde la interfaz.

**Comprobado (2026-11-12):** `/v1/assets/map` usa la misma numeración de carriles (`tier1_1`, `tier1_3`, `tier1_4`): carril 1 = izquierda, 3 = centro, 4 = derecha del minimapa, igual para ambos equipos (los carriles son absolutos). Votando posiciones de los atacantes en los 20 s previos a cada caída en la partida 109084310 el resultado es coherente pero ruidoso; el mapeo queda editable (`objetivos.json` / Ajustes). En todas las partidas los Guardians caen antes que los Walkers del mismo carril (test). Ojo: `players[].assigned_lane` usa **otra** numeración (1/4/6) y es relativa al equipo; no sirve para nombrar carriles.

Otros campos útiles verificados en la partida: `players[].stats[]` trae `player_healing`, `teammate_healing`, `self_healing` (la curación sí existe por partida, solo falta en hero-stats); `damage_matrix`; `players[].power_up_buffs[].pickup_times_s`; `players[].assigned_lane`; `match_info.teams[]`, `team_score`, `match_tracked_stats` vienen vacíos.

### Lo que NO existe en los datos (no inventarlo)
- **Rifts / KOTH**: ni eventos, ni ganador, ni tiempos. La única pista es la stat "Comeback Gold Koth" (el equipo ganó al menos uno yendo por detrás), que no es un recuento.
- **Cristales del Midboss**, quién lo inicia, intentos fallidos.
- **Curación** por héroe en hero-stats.
- Que el equipo 0 sea Hidden King y el 1 Archmother lo dice una fuente de terceros: **verificarlo**.
  - **Comprobado (2026-11-12):** el equipo 0 tiene la base **abajo** del minimapa (spawn de sus 6 jugadores en y ≈ −10 100 y `team0_core` en `top_relative` 0,92). `generic-data` dice que Hidden King es el distrito *amber* y Archmother *sapphire*, pero **ningún endpoint relaciona amber/sapphire con 0/1**. Sigue siendo de terceros; la app lo muestra con esa advertencia.

---

## 5. Minimapa

El usuario aporta la imagen `minimap_midtown_mid.avif` (1024×1024): capa negra **semitransparente**. Zonas caminables con alpha ~180; edificios y exterior transparentes. Sobre fondo oscuro no se ve: **dibujarla sobre fondo claro** cuando tenga transparencia. Algunos navegadores no abren AVIF: convertirla a WebP/PNG sin pérdida o incluirla en el proyecto.

**Calibración obtenida** (mundo → esquinas de la imagen) con la partida 109084310:
`x: -10548 … 10436` · `y: -10577 … 10406` · invertir Y = sí · invertir X = no.
El 97 % de las posiciones de jugadores vivos cae en zona caminable. El mapa es casi simétrico al girarlo 180°, así que la orientación salió por ajuste (97,6 % frente a 95,2 %) y **no es segura**. Recalibrar con varias partidas: buscar `span, x0, y0` (y las inversiones) que maximicen *precisión × cobertura* de las posiciones de vivos sobre la máscara `alpha > 100` dilatada 2 px. Guardar la calibración junto a la imagen.

**Resuelto (2026-11-12):** `/v1/assets/map` da la calibración oficial: radio 10752 centrado en 0, `left = 0.5 + x/21504`, `top = 0.5 − y/21504` (comprobado con las posiciones mundo/relativas de los campamentos). Sobre la partida 109084310 la oficial da **98,7 %** de posiciones vivas en zona caminable, frente a 97,1 % de la calibración anterior y 97,0 % girada 180°; con los spawns, la orientación queda confirmada. Guardada en `static/minimap.json`; la recalibración por ajuste sigue disponible.

Problema que hubo: el mapa a veces no aparecía porque se dibujaba antes de que la imagen terminase de cargar. Esperar a la carga y redibujar cuando llegue; si no hay imagen, avisarlo en pantalla.

---

## 6. Roles por héroe (definidos por el usuario)

Un héroe puede tener varios roles; sus partidas se reparten a partes iguales.

| Rol | Héroes |
|---|---|
| Carry | Wraith, Venator, Rat King, Mina, Warden, Vyper, Seven, Lady Geist |
| Off-carry | Pocket, Celeste, Mina, Infernus, Mirage, Shiv |
| Support | Nurse Harrow, Paige, Rem, Dynamo, Viscous, The Doorman, Sinclair, Kelvin, Ivy, Mo & Krill, Solomon, McGinnis, Vindicta, Graves |
| Frontline (tanque) | Yamato, Apollo, Silver, Abrams, Drifter, Baba, Mo & Krill, Victor, Billy, Shiv, Calico |
| Initiator (iniciador) | Haze, Grey Talon, Lash, Violet, Deadman Danny |
| Catcher | Bebop, Mo & Krill, Paradox, Holliday, Lash |

Nota: Calico se asignó como "iniciador" cuando ese rol se agrupaba con frontline; al separar Initiator, el usuario movió solo a Lash, Violet, Deadman Danny, Haze y Grey Talon, así que Calico sigue en Frontline. Confirmar con el usuario. Comparar nombres de forma normalizada (sin mayúsculas, símbolos ni "The"). La tabla debe poder editarse fácilmente.

---

## 7. Formato de `equipos.txt` (del usuario, mantener)

Una línea por jugador: uno o varios IDs (varias = cuentas del mismo jugador) y después el nombre del equipo.
```
35187362 Buff Enjoyers
483770846, 802747733 Buff Enjoyers
```
Aceptar como ID: número (account_id = steamid3 sin `[U:1:]`), `[U:1:N]`, steam64 (`account_id + 76561197960265728`) o URL de perfil. Un ID tiene ≥5 dígitos (permite equipos que empiezan por número, como "100 Thieves"). Las cuentas que no estén en la leaderboard deben guardarse igualmente como plantilla del equipo (sirven para detectar el lado en las partidas).

---

## 8. Arquitectura recomendada

Lecciones de la versión anterior:
- La web acabó siendo un único archivo Python con ~100 KB de HTML/JS en un string, crecido a base de parches. **Separar el front** (HTML/CSS/JS en archivos estáticos) desde el principio.
- El render de mapas (calor, puntos, cuadrícula) se duplicó en tres sitios: **un único módulo de mapa** para minimapa, partidas e informe.
- Recalcular el resumen de todos los jugadores en cada petición fue lento (~0,2 s y 1,1 MB por petición con 1000 jugadores): **materializar o cachear** los resúmenes tras cada actualización.
- Las partidas pesan ~1,3 MB: guardarlas comprimidas o extraer a tablas lo necesario (eventos de muerte, objetivos, posiciones decodificadas).

Propuesta (el stack concreto lo decide Code; preferir pocas dependencias):
- **Backend** Python: cliente de API con lotes, caché y backoff; SQLite; tareas en segundo plano; API JSON local.
- **Frontend** estático (vanilla o ligero), servido por el mismo proceso.
- **Informe de equipo** como **registro de métricas**: cada métrica es una función que devuelve bloques (`table`, `bars`, `histogram`, `timeline`, `map`, `text`, `unavailable`) que la web pinta sin conocerlas. Añadir una métrica no debe exigir tocar la web. Si una métrica falla, solo falla su sección.
- **Tests** desde el principio con la partida real `match_109084310.json` como fixture: decodificación de `match_paths`, mapeo de objetivos, detección de lado, métricas del informe.
- Un `README` con cómo arrancar, y `requirements.txt`.

Modelo de datos mínimo: jugadores (con campos manuales separados de los automáticos), cuentas enlazadas, snapshots de leaderboard, stats del mes por cuenta y héroe, historial de stats, caché de compañeros, partidas, plantillas de equipo.

---

## 9. Informe de equipo (especificación del usuario, resumida)

Analizar **N partidas de un equipo en conjunto** (ej. 20 de Buff Enjoyers), indicando en qué lado jugó cada una, y sacar patrones, no resúmenes por partida.

1. **Kills y muertes en el minimapa**: puntos sobre el mapa (el usuario lo prefiere a calor), zonas con más muertes, zonas con más kills y zonas donde gana o pierde enfrentamientos (balance kills − muertes). **Representarlo siempre sobre el mapa, nunca como coordenadas.** Opción para normalizar el lado (girar 180° las partidas de un lado para que la base propia quede siempre abajo).
2. **Guardians y Walkers**: qué carril pierde el primero y en qué minuto, qué carril presionan primero, si descuidan alguno, orden habitual de destrucción. Porcentajes por carril, medias y medianas, línea de tiempo.
3. **Midboss**: minuto medio y mediana, frecuencia, kills justo antes (ventana configurable, 90 s por defecto), ventaja de kills y de net worth al hacerlo, contexto (ventaja / igualdad / desventaja). Escenarios separados: cuando lo mata el equipo y cuando lo mata el rival (¿lo roban?). **Cristales e intentos: no disponibles** → marcarlo así.
4. **KOTH**: **no disponible** en los datos → explicarlo y mostrar solo la pista de "Comeback Gold Koth".
5. **Reglas estadísticas** (obligatorias): no inventar ni estimar; separar datos confirmados de interpretaciones; indicar el número de partidas en cada estadística; medias, medianas y distribuciones; avisar con muestras pequeñas (<10); buscar patrones repetidos, no casos aislados.
6. **Presentación** visual: gráficos, mapas, tablas, líneas de tiempo. Terminar con **Conclusiones generales**: fortalezas, debilidades, patrones repetidos, qué mejorar y oportunidades tácticas.
7. **Ampliable**: el usuario irá añadiendo métricas.

---

## 10. Restricciones

- **Solo local**: escuchar en `127.0.0.1`, validar la cabecera `Host` (contra DNS rebinding), aceptar escrituras solo como JSON.
- **Privacidad**: muchos jugadores del top son menores. No hacer scraping de datos personales ni buscar identidades. Redes y mayor de edad se rellenan a mano con lo que el jugador hace público; nunca guardar la edad exacta.
- **Honestidad de datos**: lo que la API no da se muestra como "no disponible", no se rellena.
- Si el usuario conserva un `scouting.db` antiguo, ofrecer importar sus campos manuales (redes, estado, notas, equipo) y su historial de snapshots.

---

## 11. Plan sugerido

1. Esqueleto del proyecto, `requirements.txt`, README y tests con la partida real.
2. **Verificar en vivo** todo lo marcado "sin verificar" (sección 3 y 4) y ajustar este documento.
3. Fase 1 y 2 (scouting + web), con actualización en segundo plano.
4. Fase 3 (partidas) con el módulo único de mapa y la calibración.
5. Fase 4 (informe de equipo) con el registro de métricas.

---

## 12. Estado (2026-11-12)

Construido desde cero siguiendo el plan de la sección 11. Ver `README.md` para arrancar (`python app.py`) y la estructura.

- **Hecho y probado en vivo**: actualización completa de Europa (temporada actual 1002 + Beta Season 1 → 1010 jugadores, ~12 min la primera vez, casi todo por el límite de `/players/rank`; las siguientes reutilizan la resolución de cuentas cacheada), vista de jugadores, por héroe, perfil con tendencias y dúos reales, partidas por ID, minimapa, explorador, informe de 12 partidas reales (lado detectado solo en las 12), recalibración con 13 partidas.
- **Tests**: 24 (`python -m unittest discover -s tests`), sin red: decodificación de `match_paths` contra posiciones de muerte, filtrado de muertos, spawn del equipo 0 abajo, mapeo de objetivos, Midboss, detección de lado, todas las métricas, fallo aislado de una métrica, actualizador con cliente falso (resolución de cuentas, reanudación tras corte, campos manuales que sobreviven, fusión de cuentas, climbers).
- **Decisiones tomadas por defecto** (cambiables):
  - Además de la temporada actual se descarga la Beta Season 1 (`extra_leaderboard_ids: [1001]` en `config.json`), porque la actual solo tiene 61 jugadores en Europa. Climbers usa solo la temporada actual.
  - Calico está en **Initiator** (`roles.json`), confirmado por el usuario el 2026-11-12.
  - Interfaz en español.
  - Los snapshots importados de un `scouting.db` antiguo se asignan a la temporada cuyo intervalo contiene su fecha. El importador es *best-effort*: no se conoce el esquema antiguo; usar «Simular» primero.
- **Pendiente / no verificado**: equipo 0 = Hidden King solo por fuentes de terceros; `team_claimed` del Midboss sigue sin documentar; mapeo de objetivos coherente pero inferido. Climbers necesita al menos dos snapshots separados en el tiempo (se acumulan desde hoy).
