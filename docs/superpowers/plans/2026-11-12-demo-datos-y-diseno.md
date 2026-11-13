# Datos del demo, economía, mapas de zonas y estilo "City Never Sleeps" — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traer rejuvenators, KOTH cash-in y daño al midboss desde el demo de cada partida (automático al guardar), ampliar la economía, pintar las zonas del informe en mapas, eliminar toda interpretación y aplicar el estilo City Never Sleeps.

**Architecture:** Módulo nuevo `scouting/demo.py` con dos partes: funciones puras que convierten las filas de 3 consultas SQL en un resumen por partida, y un trabajador en segundo plano (cola persistida en SQLite) que lanza las consultas a `/v1/matches/demo/query`, sondea, descarga el `.ndjson.zst` y guarda el resumen. `matches.store()` avisa al trabajador. El informe y la vista de partida leen el resumen con `demo.summary(match_id)`; si no existe, muestran «no disponible».

**Tech Stack:** Python 3.15 stdlib (`compression.zstd`, sqlite3, urllib, threading), JS vanilla, CSS. Tests con `python -m unittest`.

**Spec:** `docs/superpowers/specs/2026-11-12-demo-datos-y-diseno-design.md`

## Global Constraints

- Sin dependencias nuevas. `compression.zstd` se importa con guarda: si falla (Python < 3.14), demo desactivado y la UI dice «no disponible: requiere Python 3.14+».
- Hosts de salida permitidos para el demo: `api.deadlock-api.com` (consultas) y `demo-extracts.deadlock-api.com` (resultados). Toda petición lleva `User-Agent: deadlock-scouting-local/1.0` (sin él, 403).
- Presupuesto del trabajador: **150 consultas POST por hora** (ventana deslizante); tras HTTP 429 espera ≥ 61 s. Nunca relanzar una partida en estado `done` o `nodemo`.
- Nada inventado ni interpretado: lo que no está en los datos → «no disponible». Sin tono `interpretation`, sin `confirmed=False`.
- Equipos del demo → API: `2 → 0` (Hidden King/Amber), `3 → 1` (Archmother/Sapphire).
- Tiempo de juego de un tick: `(tick − paused_ticks_vigentes_en_ese_tick) / 64`. Tiempo de juego de un valor `curtime` (columnas `koth_*`): `curtime − game_start − paused_ticks_vigentes / 64`.
- Remontada: un equipo está en remontada en `t` si `nw_equipo(t) < 0.9 × nw_rival(t)` (net worth de metadatos, `M.team_networth_at`).
- Interfaz en español; carriles por nombre y color, nunca por lado. 61 tests actuales siguen pasando (salvo los que se ajustan por lo eliminado, Task 3).
- Fuentes de almas (`gold_sources[].source`): 1 Kills, 2 Troopers, 3 Jungla, 4 Objetivos, 5 Tesoro, 6 Asistencias, 7 Denies, 8 Catch-up de equipo, 9 Asesinato (habilidad), 10 Objeto (10), 11 Cultist Sacrifice, 12 Rompibles, 13 Objeto (13). «Haunts» no se usa.

## Review Focus

- Partida sin demo (404 «No demo available» / «Failed to fetch match salts»): estado `nodemo`, vistas muestran «no disponible», no se reintenta en bucle.
- Reinicio de la app con trabajos a medias: lo `pending`/`running` se reanuda; nada se duplica.
- Midboss con 0 de daño de un equipo o con daño sin muerte (entidad sin rejuvenators): no rompe, el iniciador es el de más daño > 0; si ningún daño > 0, sin iniciador y sin «robado».
- KOTH que empieza y no se completa (vuelve a 0 sin equipo): «no completado», no se atribuye a nadie.
- Informe con mezcla de partidas con y sin demo: cada bloque del demo dice sobre cuántas partidas se calcula (`n`).

---

### Task 1: Resumen del demo (funciones puras)

**Files:**
- Create: `scouting/demo.py` (solo la parte pura en esta tarea)
- Test: `tests/test_demo.py`
- Fixture (ya existe, real): `tests/fixtures/demo_135801973.json` → `{"queries": {rejuv, rules, midboss}, "results": {"match_id", "rejuv": [...], "rules": [...], "midboss": [...]}}`

**Interfaces:**
- Produces:
  - `QUERIES: dict[str, str]` — copiar literalmente `queries` del fixture (rejuv, rules, midboss).
  - `game_seconds_from_tick(tick: int, rules: list[dict]) -> float` — usa el `paused_ticks` de la última fila de `rules` con `tick <=` el dado.
  - `game_seconds_from_curtime(curtime: float, tick: int, rules: list[dict]) -> float`
  - `summarize(results: dict) -> dict` con forma:
    ```
    {"version": 1,
     "midboss": [{"n": 1, "t": 1198, "damage": {"0": 0, "1": 15731}, "initiator": 1|None,
                  "killer": 1|None, "stolen": bool|None, "rejuv": {"0": 0, "1": 3}}],
     "koth": [{"n": 1, "start_t": 740, "completed_by": 1|None, "completed_t": 758|None}]}
    ```
    Equipos ya en numeración API (0/1). `killer` = `killing_team` de las filas `rejuv` dentro de los 30 s tras el último tick de daño de esa entidad; si no hay, `None`. `stolen` = `killer != initiator` solo si ambos no son `None`; si no, `None`. Midboss ordenados por `t` (último tick de daño). Ignorar entidades cuyo daño total sea 0 y sin rejuvenators. KOTH: un cash-in = cada valor distinto de `koth_start > 0` cuyo `koth_give_up` sea finito (< 1e30); completado si después aparece fila con `koth_team ∈ {2,3}` y `koth_scoring ≥ koth_start`.

- [ ] **Step 1: Write the failing tests** (`tests/test_demo.py`, clase `Summarize`, carga el fixture)
  - `test_tick_to_game_seconds`: `round(game_seconds_from_tick(78311, rules)) == 1198` y `round(game_seconds_from_tick(106774, rules)) == 1643` (metadatos: 1198 y 1642; tolerancia ±1).
  - `test_midboss`: `len(s["midboss"]) == 2`; primero: `damage == {"0": 0, "1": 15731}`, `initiator == 1`, `killer == 1`, `stolen is False`, `rejuv == {"0": 0, "1": 3}`; segundo: `rejuv == {"0": 0, "1": 3}`, `damage["1"] == 22027`.
  - `test_koth`: `len(s["koth"]) == 3`; `[k["completed_by"] for k in s["koth"]] == [1, 0, 0]`; `round(s["koth"][0]["start_t"]) == 740`, `round(s["koth"][0]["completed_t"]) == 758`.
  - `test_koth_not_completed`: con `rules` sintético (start 900, give_up 960, luego reset a 0 sin `koth_team` > 0) → `completed_by is None`.
  - `test_midboss_no_damage`: `results` con `midboss: []` y 3 rejuv → un midboss con `initiator None`, `stolen None`, `rejuv` contado.
  - `test_summary_json_serializable`: `json.dumps(summarize(...))`.
- [ ] **Step 2: Run** `python -m unittest tests.test_demo -v` → FAIL (módulo no existe).
- [ ] **Step 3: Implement** las funciones de Interfaces en `scouting/demo.py` (sin red; sin importar `compression`).
- [ ] **Step 4: Run** `python -m unittest tests.test_demo -v` → PASS; `python -m unittest` → 61 + nuevos OK.
- [ ] **Step 5: Commit** `feat(demo): resumen de rejuvenators, KOTH y daño al midboss desde consultas del demo`

### Task 2: Cola y trabajador del demo

**Files:**
- Modify: `scouting/demo.py` (cliente + cola + trabajador)
- Modify: `scouting/db.py` (tabla nueva en `SCHEMA`)
- Modify: `scouting/matches.py` (gancho al guardar)
- Modify: `scouting/server.py` (arranque del trabajador, `GET /api/demo/status`, `demo` en `match_overview`)
- Modify: `app.py` si el arranque de hilos vive ahí
- Test: `tests/test_demo.py` (clase `Worker`)

**Interfaces:**
- Consumes: `QUERIES`, `summarize` (Task 1).
- Produces:
  - Tabla `demo_jobs(match_id INTEGER PRIMARY KEY, state TEXT NOT NULL, summary TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0, next_try INTEGER NOT NULL DEFAULT 0, updated_at INTEGER)`; `state ∈ pending|done|nodemo|error`.
  - `AVAILABLE: bool` (import de `compression.zstd` correcto).
  - `enqueue(con, match_id: int) -> None` — inserta `pending` si no existe (no toca `done`/`nodemo`).
  - `summary(con, match_id: int) -> dict` → `{"state": "done", ...summarize...}` | `{"state": "pending"|"nodemo"|"error"|"unavailable", "reason": str}`.
  - `class DemoClient(opener=None, now=time.time, sleep=time.sleep)` con `run_queries(match_id) -> dict` (`results` como en el fixture). Lanza `NoDemo` en 404; `RateLimited` en 429.
  - `class Worker(con_factory, client, budget_per_hour=150)` con `start()`, `stop()`, `step() -> bool` (procesa una partida; `False` si no hay nada o no hay presupuesto). Errores: `attempts += 1`, `next_try = now + 600 * attempts`, tras 5 intentos queda `error` sin reintento.
  - `matches.ON_STORE: list[callable]` — `store()` llama a cada `fn(con, match_id)` al final; excepciones de los ganchos se registran y no rompen el guardado.
- [ ] **Step 1: Write the failing tests** (opener falso que responde por URL; sin red; saltar la clase si `not demo.AVAILABLE`)
  - `test_enqueue_idempotent_and_keeps_done`
  - `test_worker_success_stores_summary`: opener devuelve `{"job_id":"j","status":"queued"}`, luego `{"status":"done","result_url":"https://demo-extracts.deadlock-api.com/j.ndjson.zst"}`, luego `compression.zstd.compress` de las filas del fixture → `summary(con, mid)["state"] == "done"` y `midboss[0]["rejuv"] == {"0":0,"1":3}`. Cada petición capturada lleva `User-Agent`.
  - `test_nodemo_404_not_retried`: 404 → `state == "nodemo"`; segundo `step()` no hace peticiones.
  - `test_429_waits_and_keeps_pending`: tras 429, `state == "pending"`, `next_try ≥ now + 61`.
  - `test_budget_150_per_hour`: con 150 POST en la última hora `step()` devuelve `False` sin peticiones.
  - `test_result_url_other_host_rejected`: `result_url` en otro host → `error`, sin descargar.
  - `test_store_hook_enqueues`: `matches.store(con, fixture109084310, "test")` → fila `pending` en `demo_jobs` (con `ON_STORE` registrado por `demo.install(...)`).
  - `test_unavailable_without_zstd`: con `demo.AVAILABLE` parcheado a `False`, `summary()` devuelve `state "unavailable"` y razón con «Python 3.14».
- [ ] **Step 2: Run** `python -m unittest tests.test_demo -v` → FAIL.
- [ ] **Step 3: Implement.** Al arrancar el servidor: `demo.install()` registra el gancho, encola todas las partidas guardadas sin fila y arranca `Worker` en un hilo daemon (solo si `AVAILABLE`). Sondeo cada 3 s hasta 120 s; respuesta máx. 20 MB. `match_overview` añade `"demo": demo.summary(con, mid)`. `GET /api/demo/status` → recuentos por estado.
- [ ] **Step 4: Run** `python -m unittest` → todo OK.
- [ ] **Step 5: Commit** `feat(demo): cola persistente que trae el demo al guardar cada partida`

### Task 3: Eliminar interpretaciones

**Files:**
- Modify: `scouting/matches.py:227-234` (`midboss()` sin `stolen`), `scouting/report/metricas/m04_midboss.py`, `m05_koth.py`, `m02_mapa.py:77`, `m03_carriles.py:99,106`, `m99_conclusiones.py`, `scouting/report/__init__.py` (docstring y `finding()` sin `confirmed`), `static/js/blocks.js` (TONE), `static/js/views/matches.js` (columna «¿Robo?», nota de interpretación, `mvpOf` estimado, texto Comeback Gold Koth), `tests/test_match.py:94-95`.

**Interfaces:**
- Produces: `matches.midboss(mi) -> [{"n","t","team_killed","team_claimed"}]` (sin `stolen`). `ReportCtx.finding(kind, text, support=None, total=None)`.
- [ ] **Step 1: Write the failing tests** (en `tests/test_match.py`)
  - `test_midboss`: sustituir las aserciones de `stolen` por `self.assertNotIn("stolen", mb[0])`.
  - `test_report_has_no_interpretation`: recorrer `report.run(...)` → ningún bloque `text` con `tone == "interpretation"`, ninguna fila de conclusiones con `tipo == "interpretación"`, y `"contexto"`/`"robos"` no aparecen como claves de columnas de m04.
- [ ] **Step 2: Run** `python -m unittest tests.test_match -v` → FAIL.
- [ ] **Step 3: Implement.** m04: fuera `_context`, `stolen`, `robos`, el texto `interpretation` y las 3 `finding` con `confirmed=False`; quedan tiempos, quién mata/reclama, kills en la ventana y diferencia de net worth como números. m05 se queda mínimo (lo reescribe Task 4). Frontend: MVP solo si `mvp_rank === 1`; si no, no se pinta el bloque MVP.
- [ ] **Step 4: Run** `python -m unittest` → OK.
- [ ] **Step 5: Commit** `refactor: quitar todo lo interpretativo (robo por reclamo, contexto, MVP estimado, conclusiones sin confirmar)`

### Task 4: Informe — midboss, KOTH y remontada con datos del demo

**Files:**
- Modify: `scouting/report/__init__.py` (`MatchCtx.demo` perezoso), `scouting/report/metricas/m04_midboss.py`, `m05_koth.py`, `scouting/matches.py` (helper de remontada), `scouting/server.py:448` (pasar `con` o resúmenes a `report.run`)
- Test: `tests/test_demo.py` (clase `ReportWithDemo`)

**Interfaces:**
- Consumes: `demo.summary(con, mid)` (Task 2).
- Produces:
  - `report.run(team, match_datas, roster, side_overrides=None, params=None, demo_summaries=None)` — `demo_summaries: dict[int, dict]`; `MatchCtx.demo` devuelve el resumen o `None` si `state != "done"`.
  - `matches.comeback_team_at(mi, t) -> int|None` — equipo (0/1) en remontada según la regla del 0,9; `None` si ninguno.
- [ ] **Step 1: Write the failing tests** (fixture 109084310 como partida + resumen sintético con la forma de Task 1, `our = 1`)
  - `test_comeback_rule`: con un `mi` sintético de 2 jugadores (nw 9000 vs 10000 → `None`; 8999 vs 10000 → equipo del 8999).
  - `test_midboss_section_uses_demo`: sección `midboss` contiene tabla con columnas `rejuv_nuestros`, `rejuv_rival`, `dano_nuestro`, `dano_rival`, `iniciador`, `robado`; con resumen `stolen True` la fila dice «sí».
  - `test_midboss_section_without_demo`: sin resúmenes → bloque `unavailable` con «demo» en el título y la tabla de metadatos (quién mata/reclama) sigue.
  - `test_koth_section`: 3 cash-in del resumen → tabla con «Este equipo»/«Rival»/«No completado» y columna `remontada` (sí/no según `comeback_team_at` en `start_t`); bloque `n` = partidas con demo.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Cada midboss y cada cash-in se etiqueta con `remontada` (si el equipo que lo consigue estaba en remontada en ese `t`). Totales en el informe: midboss conseguidos, rejuvenators cogidos (media por midboss), robos hechos/sufridos (solo con `stolen` no `None`), KOTH completados por cada equipo y cuántos en remontada. Conclusiones solo como recuentos. El servidor construye `demo_summaries` con `demo.summary` de cada partida.
- [ ] **Step 4: Run** `python -m unittest` → OK.
- [ ] **Step 5: Commit** `feat(informe): midboss con rejuvenators y daño, KOTH cash-in y remontada desde el demo`

### Task 5: Economía ampliada (informe y partida)

**Files:**
- Modify: `scouting/matches.py` (helpers de fuentes), `scouting/report/metricas/m06_economia.py`, `scouting/matches.py:overview` (bloque `economy`)
- Test: `tests/test_match.py` (clase `Economy`)

**Interfaces:**
- Produces:
  - `matches.GOLD_SOURCES: dict[int, str]` (mapa de Global Constraints).
  - `matches.source_at(player, source: int, t: float) -> float` — `gold` de `gold_sources` interpolado como `stat_at`.
  - `matches.economy(mi) -> {"phases": [[0,600],[600,1200],[1200,dur]], "teams": {"0": {...}, "1": {...}}, "players": [{slot, team, sources: {id: gold}, per_min: {...}}]}`; `per_min` con claves `troopers_kills`, `jungla_kills`, `troopers_jungla_kills`, `almas`, y `fuente_<id>`; por equipo además `per_phase` con las mismas claves por fase. Kills de troopers = `creep_kills`, jungla = `neutral_kills`.
- [ ] **Step 1: Write the failing tests** (fixture 109084310)
  - `test_sources_sum_final`: para el jugador slot 10, `economy(mi)` → `sources` `{1: 2779, 2: 8631, 3: 2917, 4: 3518, 5: 931, 6: 2827, 7: 271, 8: 286, 12: 4347}` (los 0 se omiten).
  - `test_per_min`: slot 10, `per_min["troopers_kills"] == round(70 / (2416/60), 2)` y `per_min["jungla_kills"] == round(8 / (2416/60), 2)`.
  - `test_phases_cover_duration`: última fase termina en `duration_s`; valores por fase ≥ 0.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** m06: añadir (a) desglose medio de almas por fuente del equipo vs rival (barras con etiquetas de `GOLD_SOURCES`), (b) tabla por minuto (troopers/min, jungla/min, troopers+jungla/min, almas/min) por fase, equipo vs rival. Se mantiene lo actual de net worth.
- [ ] **Step 4: Run** `python -m unittest` → OK.
- [ ] **Step 5: Commit** `feat(economia): almas por fuente y ritmos por minuto por fase`

### Task 6: Vista de partida — midboss, KOTH, economía y estado del demo

**Files:**
- Modify: `static/js/views/matches.js` (`midboss()`, `kothCard()`, nueva pestaña/sección «Economía»), `static/app.css`

**Interfaces:**
- Consumes: `overview.demo` (Task 2: `{state, midboss, koth}` o `{state, reason}`), `overview.economy` (Task 5), `matches.GOLD_SOURCES` nombres llegan ya resueltos en `economy` (añadir `"source_names"` al payload).
- [ ] **Step 1: Implement.** Midboss: por cada uno, imagen Midboss, hora, quién lo mata, 3 iconos Rejuvenator coloreados por equipo que lo coge, daño por equipo en barra doble, «iniciado por» y «robado» solo si vienen. KOTH: lista de cash-in (hora inicio, completado por/«no completado», hora, etiqueta «en remontada»). Estado del demo: `pending` → «Cargando datos del demo…» (recarga la vista cada 20 s mientras siga pendiente), `nodemo` → «No disponible: esta partida no tiene demo», `unavailable` → la razón. Economía: tabla por jugador con columnas por fuente (iconos/nombres) y ritmos por minuto.
- [ ] **Step 2: Verify in browser:** `python app.py --no-abrir`, abrir la partida 135801973 → midboss 1 «3 rejuvenators para Archmother», KOTH 3 filas (12:20 Archmother, …), economía visible; abrir 109084310 → «No disponible: esta partida no tiene demo». Consola sin errores.
- [ ] **Step 3: Commit** `feat(partidas): midboss, KOTH y economía con datos del demo`

### Task 7: Mapas junto a las tablas de zonas

**Files:**
- Modify: `scouting/report/metricas/m02_mapa.py`, `static/js/map.js` (capa `highlight`), `static/js/blocks.js` (bloque `table` con `map` al lado)
- Test: `tests/test_match.py`

**Interfaces:**
- Produces: bloque `table` puede llevar `map: {grid, normalized, layers: [{kind: "highlight", cells: [[col,row,label]], side}]}`; `map.js` dibuja `highlight` como celdas con borde grueso y etiqueta (`A3`), color `side` (us/them).
- [ ] **Step 1: Write the failing test** `test_zone_tables_have_maps`: en la sección `mapa`, las tablas «Zonas con más muertes», «Zonas con más kills» y «Dónde ganan y pierden enfrentamientos» tienen `map.layers[0].kind == "highlight"` y sus `cells` coinciden con las zonas de sus filas.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (tabla y mapa lado a lado; en móvil, uno debajo del otro). **Step 4: Run** → PASS; comprobar en el navegador el informe de un equipo.
- [ ] **Step 5: Commit** `feat(informe): mapa resaltando las zonas de cada tabla`

### Task 8: Estilo "City Never Sleeps"

**Files:**
- Modify: `static/app.css`, `static/index.html`, `static/js/views/report.js` (titular con palabra destacada, índice numerado), `static/js/views/home.js`, `static/js/views/matches.js` (cartas inclinadas en cabecera), `static/js/util.js` si hace falta un helper `headline(text, highlight)`

**Interfaces:**
- Produces: `headline(before: string, highlight: string, after?: string) -> HTMLElement` en `util.js` (h2 con `<mark class="tag-word">`).
- [ ] **Step 1: Implement.** Tokens en `:root`: fondo `#1a1310`, superficie `#251b16`, texto crema `#f3e6cf`, acento naranja `#e0612a`, turquesa `#3fb8a8`; textura sutil con gradiente CSS (sin imágenes nuevas). Titulares: `font-family: "Bahnschrift", "Segoe UI Black", "Arial Black", sans-serif; font-weight: 800`, palabra destacada en etiqueta naranja ligeramente girada. Retratos `.portrait.card` como cartas con borde crema, giro alterno ±3°. Índice del informe y cronologías con número en círculo turquesa y línea discontinua. Mapas y paneles en marco claro con sombra. Mantener colores de carril y equipo, contraste AA en tablas, `@media print` legible y `prefers-reduced-motion`.
- [ ] **Step 2: Verify in browser:** inicio, jugadores, partida 135801973 e informe: capturas de pantalla, sin solapes a 375 px de ancho, consola sin errores.
- [ ] **Step 3: Commit** `style: estilo City Never Sleeps en toda la app`

### Task 9: Documentación

**Files:** `README.md`, `HANDOFF.md`
- [ ] **Step 1:** Documentar: datos del demo (qué, cuándo se piden, límite 150/h, estados, Python 3.14+), hosts de salida (`demo-extracts.deadlock-api.com`), fórmula tick→segundo, mapeo de equipos 2/3→0/1, fuentes de almas, eliminación de interpretaciones, regla de remontada.
- [ ] **Step 2:** `python -m unittest` → OK. **Commit** `docs: datos del demo, economía y estilo`
