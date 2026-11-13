# Fase de líneas y desglose por jugador — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estadísticas de la fase de líneas (0–600 s) por dúo y línea, primer gankeo por línea y desglose jugador por jugador, en el informe (agregado) y en la vista de partida (una partida), con el mismo cálculo.

**Architecture:** Tres módulos puros por partida — `scouting/lanes.py` (línea de cada jugador por posiciones), `scouting/lanephase.py` (dúos, daño, Guardians, gankeos) y `scouting/playerstats.py` (desglose por jugador) — que consumen metadatos + filas crudas de una 4.ª consulta al demo. `matches.overview` los expone para la partida; dos métricas nuevas del informe los agregan.

**Tech Stack:** Python 3.15 stdlib, JS vanilla (ES modules), `python -m unittest`.

**Spec:** `docs/superpowers/specs/2026-11-13-fase-lineas-y-jugadores-design.md`

## Global Constraints

- Fase de líneas = 0–600 s de juego. Gankeo se busca en 60–600 s. Tiempo de juego de un tick: `(tick − paused_ticks_vigentes) / 64` (`demo.game_seconds_from_tick`).
- Línea de un jugador: mediana de posiciones vivas en 60–300 s → carril del recorrido más cercano de `lane_paths.json` (ids 1 York, 3 Broadway, 4 Greenwich). Válido solo si cada equipo tiene exactamente 2 jugadores en cada línea; si no, todas las líneas de esa partida = None («no disponible»).
- Equipos del demo no aparecen aquí: la consulta nueva devuelve cuentas (`att`, `vic` = account_id).
- Nada inventado ni interpretado; sin consejos. Lo que falta → None / «no disponible». Cada bloque lleva `n`.
- Presupuesto del demo 150 POST/h; la consulta nueva es 1 POST por partida.
- Interfaz en español; carriles por nombre y color (`laneChip`), nunca por lado.
- Tests sin red. Fixtures reales ya en el repo: `tests/fixtures/match_135801973.json.gz` (metadatos), `tests/fixtures/demo_lane_135801973.json` (`{"query", "rows":[{att,vic,b,dmg}]}`, 664 filas, b = tramo de 320 ticks), `tests/fixtures/demo_135801973.json` (rules para pausas), `lane_paths.json` (recorridos).

## Review Focus

- Partida donde las posiciones no dan 2 y 2: líneas None, ningún dúo/gankeo inventado, KDA/farm/mapas siguen.
- Partida sin demo o con la consulta nueva pendiente: daño aproximado marcado `source: "aprox"`, reparto rival/gankeo None, gankeos solo por kills.
- Jugador que muere antes del 60 s o desconectado (posiciones casi vacías): su línea None → partida no válida para dúos, sin excepción.
- Guardian que no cae: tiempo None, contado aparte («no cae en X de N»).
- Informe con partidas mezcladas (con y sin demo): medias de daño de fase de líneas solo con demo, `n` explícito.

---

### Task 1: Línea de cada jugador por posiciones

**Files:** Create `scouting/lanes.py`; Test `tests/test_lanephase.py` (clase `Lanes`).

**Interfaces — Produces:**
- `load_paths(path=None) -> list[{"lane": int, "points": [[x,y],...]}]` (lee `lane_paths.json` de la raíz).
- `assign_lanes(mi, paths) -> {slot: lane|None}` — lanes todas None si no hay 2 y 2 por equipo y línea.
- `duos(mi, lanes) -> {team: {lane: [slot, slot]}}` (vacío si lanes inválidas).

- [ ] **Step 1: Tests** (fixture 135801973; mapa account→slot desde `mi["players"]`):
  - `test_assign_lanes_real_match`: por account_id → lane: 298155885→3, 888853854→3, 298305257→4, 984254212→4, 906011648→1, 5278896→1, 483770846→1, 35187362→1, 911856667→4, 97533101→4, 87241154→3, 344946432→3.
  - `test_duos_two_per_lane`: `duos` da 2 slots por (team, lane) para los 6 pares.
  - `test_invalid_when_not_two_and_two`: moviendo las posiciones de un jugador (copia del mi con su `match_paths` alterado, o parcheando la función de medianas) a otra línea → todas None y `duos` vacío.
  - `test_player_without_positions`: un jugador sin posiciones vivas → todas None, sin excepción.
- [ ] **Step 2:** `python -m unittest tests.test_lanephase -v` → FAIL. **Step 3:** implementar. **Step 4:** PASS + suite completa.
- [ ] **Step 5: Commit** `feat(lineas): línea de cada jugador por posiciones`

### Task 2: Consulta del demo de fase de líneas

**Files:** Modify `scouting/demo.py`; Test `tests/test_demo.py`.

**Interfaces — Produces:**
- `QUERIES["lane_damage"]` = la consulta del fixture `demo_lane_135801973.json` (`query`), con el límite de ticks como constante `LANE_TICK_LIMIT = 48000` (600 s × 64 = 38400 + margen para pausas; las filas se recortan a 600 s de juego al usarlas).
- `lane_rows(con, match_id) -> list[dict] | None` — filas crudas `lane_damage` de esa partida, o None si no están.
- Relleno: una fila `done` cuyo `raw` no tiene la clave `"lane_damage"` se completa pidiendo **solo** esa consulta (1 POST) y fusionándola en `raw`; el estado sigue `done` mientras tanto y `summary()` sigue sirviendo el resumen existente. Las partidas nuevas piden las 4 consultas. Orden: primero `pending`, después rellenos (ambos `match_id DESC`). Mismo presupuesto, misma gestión de 429/NoDemo/errores (un error en el relleno no cambia el estado `done`; se reintenta con el mismo backoff guardado aparte, p. ej. columna `lane_attempts`/`lane_next_try` o en kv).
- `run_queries(match_id, only=None)` — `only` = lista de claves de QUERIES a pedir.

- [ ] **Step 1: Tests** (opener falso, sin red): `test_new_match_runs_four_queries`; `test_done_row_backfills_only_lane_query` (1 POST, raw fusionado, state sigue done, summary igual); `test_lane_rows_none_until_backfilled`; `test_backfill_error_keeps_done`; `test_pending_before_backfill_order`.
- [ ] **Steps 2–4:** RED, implementar, GREEN + suite.
- [ ] **Step 5: Commit** `feat(demo): consulta de daño entre héroes en fase de líneas y relleno de partidas hechas`

### Task 3: Resumen de fase de líneas por partida

**Files:** Create `scouting/lanephase.py`; Test `tests/test_lanephase.py` (clase `LanePhase`).

**Interfaces:**
- Consumes: `lanes.assign_lanes`, `lanes.duos`, `demo.game_seconds_from_tick`, `matches.objectives`, `matches.deaths`, `damage_matrix`.
- Produces: `lane_phase(mi, lane_rows=None, rules=None, paths=None) -> dict`:
  ```
  {"valid": bool, "source": "demo"|"aprox"|None,
   "lanes": {"<lane>": {"<team>": {"slots": [s1,s2], "heroes": [h1,h2],
        "dmg_done": int|None, "dmg_taken": int|None,            # total con héroes, 0–600 s
        "dmg_done_lane": int|None, "dmg_taken_lane": int|None,  # solo entre rivales de la misma línea (demo)
        "dmg_taken_gank": int|None,                             # recibido de jugadores de otras líneas (demo)
        "guardian_taken_t": int|None, "guardian_lost_t": int|None,  # caída del Guardian de esta línea (rival / propio)
        "deaths": int, "kills": int,                            # antes de 600 s
        "first_gank_suffered": {"t","attacker_slot","victim_slot","kind": "dano"|"kill"}|None,
        "first_gank_made": {...}|None}}},                       # el equipo gankea esta línea desde otra
   "players": {"<slot>": {"lane": int|None, "dmg_done": ..., "dmg_taken": ..., "ganks_made": int, "ganks_suffered": int, "deaths": int, "kills": int}}}
  ```
  Con `lane_rows` (demo): cada fila → segundos con `rules`; solo 0–600 s; gankeo = primera fila en 60–600 s con `dmg > 0` de un atacante cuya línea ≠ línea de la víctima (o kill de `deaths()` así), el que ocurra antes. Sin `lane_rows`: `dmg_done/taken` = interpolación lineal al 600 s de `damage_matrix` (suma a/desde héroes enemigos), `source "aprox"`, campos `_lane`/`_gank` None, gankeos solo por kills. Guardians de `objectives()` (tipo "Guardian", campo de línea y `destroyed_s`; equipo dueño). Si `valid` False: `lanes` = {} y jugadores con lane None.
- [ ] **Step 1: Tests** (fixtures reales): `test_valid_and_source_demo`; `test_dmg_sums_match_rows` (para un jugador, `players[slot].dmg_done` = suma de `dmg` de sus filas con t ≤ 600, calculada en el test a partir del fixture); `test_lane_split_adds_up` (`dmg_taken = dmg_taken_lane + dmg_taken_gank`, ignorando daño de compañeros si lo hubiera); `test_first_gank_is_cross_lane_and_after_60` (attacker y victim en líneas distintas, 60 ≤ t ≤ 600, y no hay ninguna fila cruzada anterior); `test_guardian_times_from_objectives`; `test_without_demo_is_aprox` (lane_rows None → source "aprox", `_lane` None, valores numéricos ≥ 0); `test_invalid_lanes` (paths que no dan 2 y 2 → valid False, lanes {}); `test_json_serializable`.
- [ ] **Steps 2–4:** RED, implementar, GREEN + suite.
- [ ] **Step 5: Commit** `feat(lineas): resumen de fase de líneas por partida (dúos, daño, Guardians, gankeos)`

### Task 4: Desglose por jugador por partida

**Files:** Create `scouting/playerstats.py`; Test `tests/test_lanephase.py` (clase `PlayerStats`).

**Interfaces — Produces:** `player_stats(mi, lane_phase_result, cal=None) -> list[dict]` por jugador: `slot, team, account_id, hero_id, lane, kills, deaths, assists, kda, last_hits, denies, net_worth, nw_per_min, nw_at_600, troopers_per_min, jungla_per_min, sources {id: gold}, player_damage, damage_taken, kill_cells [[col,row,count]], death_cells [[col,row,count]]` (celdas con `report.cell_of` y la calibración del minimapa, normalizadas como el informe: base propia abajo), más los campos de fase de líneas del jugador. Reutiliza `matches.economy` y `matches.deaths`.
- [ ] **Step 1: Tests** (fixture 109084310 y 135801973): valores directos de los metadatos (kills/deaths/assists, last_hits, net_worth final del slot 10 del fixture 109084310 = los del jugador); `kill_cells` suma = kills con posición; `death_cells` suma = muertes con posición; `test_json_serializable`.
- [ ] **Steps 2–4**, **Step 5: Commit** `feat(jugadores): desglose por jugador por partida`

### Task 5: Partida — payload y vistas «Fase de líneas» y «Jugadores»

**Files:** Modify `scouting/server.py` (overview/match payload), `static/js/views/matches.js`, `static/app.css`; Test `tests/test_lanephase.py` (payload).

**Interfaces:** el payload de `GET /api/matches/<id>` añade `"lane_phase": lanephase.lane_phase(...)` (con `demo.lane_rows` y las `rules` crudas del demo si existen) y `"player_stats": playerstats.player_stats(...)`; el sondeo `/api/matches/<id>/demo` también los devuelve para refrescar cuando llegue el relleno.
- [ ] **Step 1: Test** `test_match_payload_has_lane_phase_and_players` (servidor sobre BD temporal con la partida 135801973 y el demo crudo del fixture; o la función que arma el payload).
- [ ] **Step 2: Implement.** Pestaña «Fase de líneas»: por línea (chip con color), dos tarjetas (equipo 0 y 1) con retratos del dúo, daño hecho/recibido (barras), reparto línea/gankeo, Guardian tirado/perdido (minuto), primer gankeo hecho y sufrido (héroe que gankea, minuto). Fuente: «demo» o «aprox., sin demo». Si `valid` False: «no disponible: las posiciones no permiten saber la línea de cada jugador». Pestaña «Jugadores»: tabla de los 12 (retrato, línea, KDA, farm/min, net worth/min, NW a los 10, daño, fase de líneas) y, al elegir un jugador, sus minimapas de kills y muertes (capa `highlight` o `cells` existente) y sus almas por fuente.
- [ ] **Step 3: Verify:** suite completa; el controlador comprueba en el navegador.
- [ ] **Step 4: Commit** `feat(partidas): pestañas de fase de líneas y jugadores`

### Task 6: Informe — fase de líneas y jugadores

**Files:** Create `scouting/report/metricas/m07_fase_lineas.py`, `m08_jugadores.py`; Modify `scouting/report/__init__.py` (`MatchCtx.lane_phase`, `MatchCtx.player_stats` perezosos; `run(..., lane_data=None, player_ids=None)`), `scouting/server.py` (`report_run` pasa `lane_data={mid: (lane_rows, rules)}` y `player_ids={account_id: {"player_id", "name"}}` desde la tabla de jugadores/cuentas enlazadas); Test `tests/test_lanephase.py` (clase `ReportLanes`).

**Interfaces:**
- m07 «Fase de líneas (min 0–10)»: por línea, tabla de dúos del equipo (par de héroes sin orden) con `n`, media de daño hecho, recibido, recibido de gankeos (solo demo, con su `n`), minuto medio en que tiran el Guardian rival y «no cae en X de N», minuto medio en que pierden el suyo y «no cae en X de N». Ordenada por daño hecho. Primer gankeo por línea: minuto medio y mínimo, sufrido y hecho, y héroes que más gankean esa línea. Bloque de cobertura: partidas con líneas válidas / con demo de fase de líneas.
- m08 «Jugadores»: por jugador de la plantilla (identidad por `player_ids`, si no la cuenta): partidas, héroes, líneas, KDA medio, farm/min, net worth/min, NW a los 10, daño, muertes y kills en fase de líneas, gankeos hechos/sufridos; y por jugador un mapa de zonas donde más muere y otro donde más mata (bloques `table` con `map` highlight, como m02).
- Findings solo como recuentos.
- [ ] **Step 1: Tests** con la partida 135801973 (plantilla = cuentas del equipo 1) y lane_data del fixture: secciones presentes; un dúo por línea con `n == 1`; daños del informe == los de `lane_phase` de esa partida (mismo cálculo); jugadores = 6 con sus kills; sin demo → daño de fase de líneas «no disponible» en el informe.
- [ ] **Steps 2–4**, **Step 5: Commit** `feat(informe): fase de líneas por dúo y desglose por jugador`

### Task 7: Documentación
**Files:** `README.md`, `HANDOFF.md`. Explicar: línea por posiciones (por qué no `assigned_lane`), consulta nueva y relleno, definición de gankeo (60–600 s, otra línea, daño o kill), fuente «aprox.» sin demo, identidad de jugador. **Commit** `docs: fase de líneas y desglose por jugador`.
