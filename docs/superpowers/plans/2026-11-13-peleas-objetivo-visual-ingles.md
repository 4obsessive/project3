# Objective fights, more visual stats, English UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kills/deaths shown also without midboss/KOTH fights; stats with more images (nothing removed); whole UI in English.

**Architecture:** Demo summary gains midboss first-damage time and KOTH end time (summary rebuilt from stored raw rows). A pure classifier `scouting/fights.py` labels every death event `midboss`/`koth`/`rest` per match; `playerstats` and the report map/players metrics consume it, so report and match view agree. Then English + visuals are applied screen group by screen group.

**Tech Stack:** Python 3.15 stdlib, vanilla JS, `python -m unittest`.

**Spec:** `docs/superpowers/specs/2026-11-13-peleas-objetivo-visual-ingles-design.md`

## Global Constraints

- Midboss fight: victim death position within **2500** world units of (0,0) and time in [first damage to that midboss, its death + **60 s**]; without demo: [death − 60 s, death + 60 s]. One window per midboss.
- KOTH fight: victim death position within **2000** units of (−7648, 0) or (7648, 0) and time in [cash-in start, end + **60 s**], end = completed time, else the give-up/abandon time from raw rules. Without demo: KOTH unknown → match excluded from "without objective fights" figures (counted and said).
- A death in both windows → midboss if nearer the pit, else KOTH.
- Same convention as existing maps: kills and deaths both use the victim's death position; team 1 rotated 180° for "own base at bottom".
- Nothing removed from the UI; nothing invented (missing → "not available"/"–"); findings only as counts; lanes by name and colour.
- English UI: every user-facing string in English; game names (heroes, York/Broadway/Greenwich, Hidden King/Archmother) unchanged; number/date formatting `en-US`. Server log lines and code comments may stay Spanish. README/HANDOFF stay Spanish.
- Images only through the existing proxy/`art.js` (`heroPortrait`, `objectiveImg`, `laneChip`); no new hosts.

## Review Focus

- Match with demo but no KOTH (no cash-in): no KOTH fights, match still included in "rest".
- Match without demo: midboss split works, KOTH unknown → excluded from rest figures with a count.
- Death with missing position: counted in totals but never classified as an objective fight (class `rest`? no — `unknown`), excluded from maps as today.
- Untranslated leftovers: a test fails on common Spanish words in `static/js` and report metric texts.
- Report and match view show the same per-match split.

---

### Task 1: Demo summary — midboss first damage and KOTH end
**Files:** `scouting/demo.py`, `tests/test_demo.py`.
**Produces:** `SUMMARY_VERSION = 3`; each midboss entry gains `"t_first"` (game s of first damage of that entity, from raw midboss rows `t0`; None for rejuv-only entries); each KOTH entry gains `"end_t"` (= `completed_t` if completed, else the abandon/give-up time in game seconds from the raw rules — the builder checks which column/transition marks the abandon; None if unknown). Summaries rebuild from stored raw rows (existing mechanism).
- [ ] Tests (fixture `tests/fixtures/demo_135801973.json`): midboss #1 `t_first` = `round(game_seconds_from_tick(77467, rules))`; #2 from tick 106044; KOTH entries `end_t == completed_t` for the 3 completed ones; synthetic abandoned cash-in → `end_t` = abandon time; version is 3 and an old v2 summary is rebuilt on read.
- [ ] RED → implement → GREEN → suite → commit `feat(demo): inicio del daño al midboss y fin del KOTH en el resumen`.

### Task 2: Fight classifier
**Files:** Create `scouting/fights.py`; `tests/test_fights.py`.
**Produces:** `classify(mi, demo_summary=None) -> {"koth_known": bool, "events": [ {**death_event, "fight": "midboss"|"koth"|"rest"|"unknown"} ]}` (death events = `matches.deaths(mi)`; `unknown` = no position). Constants `MIDBOSS_RADIUS=2500`, `RIFT_RADIUS=2000`, `AFTER_S=60`, `RIFTS=[(-7648,0),(7648,0)]`, `PIT=(0,0)`. Midboss windows from demo summary `midboss[].t_first`/`t` when demo `state=="done"`, else metadata `mid_boss[].destroyed_time_s` ± 60. KOTH windows from demo `koth[]` (`start_t`, `end_t`), `koth_known = demo done`.
- [ ] Tests: synthetic events at the pit inside/outside the window, near a rift during/after a cash-in (+59 s in, +61 s out), far away during a window → rest, both windows → nearest; real fixture 135801973 with its demo summary: counts per class are consistent (sum = total) and every `midboss` event is within 2500 of (0,0); without demo → `koth_known False`.
- [ ] RED → implement → GREEN → suite → commit `feat(peleas): clasificar kills y muertes en midboss, KOTH o resto`.

### Task 3: Split in player stats, report and match view (data + Spanish→English for touched strings only where new)
**Files:** `scouting/playerstats.py` (add `kill_cells_rest`, `death_cells_rest`, `kills_rest`, `deaths_rest`, `fights` counts; None for rest fields when `koth_known` False), `scouting/server.py` (`match_payload_extras` passes the demo summary; payload adds `fights: {koth_known, counts:{midboss,koth,rest,unknown}}`), `scouting/report/__init__.py` (`MatchCtx.fights` lazy), `scouting/report/metricas/m02_mapa.py` (rest maps + rest zone tables + summary block with counts and "N matches excluded: KOTH not identifiable without demo"), `m08_jugadores.py` (per player rest kills/deaths and rest zone maps), `static/js/views/matches.js` (Minimapa: toggle "Exclude objective fights"; Jugadores: rest maps next to the existing ones).
- [ ] Tests: report m02 rest totals == sum over matches of per-match `classify` rest counts; match without demo excluded with its count; m08 per player rest == playerstats rest; payload has `fights`.
- [ ] Implement; controller checks in browser. Commit `feat(peleas): kills y muertes sin peleas de midboss ni KOTH`.

### Task 4: English + visuals — team report
**Files:** `scouting/report/__init__.py` (texts), all `scouting/report/metricas/*.py` (titles, columns, notes, findings, unavailable reasons → English), `static/js/views/report.js`, `static/js/blocks.js`, `static/app.css`, tests asserting Spanish strings.
**Visual:** column `fmt: 'heroes'` (portraits from hero ids, hover = name) used for duo/hero columns; objective icons in section titles (existing SECTION_ART) and in Guardian/Midboss/KOTH columns; in-cell mini bars for comparable numeric columns (`bar: true` column flag rendered by blocks.js); headline cards block type `cards` (`{type:"cards", items:[{title, value, hero_ids?, objective?, lane?}]}`) for: top damage duo per lane, most kills player, most first-gank suffered lane.
- [ ] Tests updated to English; new test that report output text has no Spanish leftovers (word list: "partidas", "muertes", "carril", "línea", "equipo", "jugador", "daño", "no disponible", "rival", "minuto").
- [ ] Commit `feat(informe): informe en inglés y más visual`.

### Task 5: English + visuals — match view
**Files:** `static/js/views/matches.js`, `scouting/matches.py` (user-facing labels, e.g. objective labels), `scouting/server.py` (HttpError messages shown to users), `static/app.css`.
**Visual:** portraits in all player rows (already mostly), objective icons in objective/midboss/KOTH lists, mini bars in economy and player tables, a headline card row on Resumen (MVP if provided, top damage, top farmer) with portraits.
- [ ] Commit `feat(partidas): vista de partida en inglés y más visual`.

### Task 6: English + visuals — rest of the app
**Files:** `static/index.html`, `static/js/main.js`, `ui.js`, `util.js` (`en-US` formatting), `search.js`, `api.js` messages, `views/home.js`, `players.js`, `profile.js`, `hero.js`, `climbers.js`, `teams.js`, `settings.js`, `explorer.js`, server messages surfaced to users.
**Visual:** portraits where players/heroes are listed without one; lane chips; mini bars in ranking tables.
- [ ] Test: scan `static/` (js + html) for the Spanish word list above (ignoring code comments `//` and `/* */`) → none in UI strings.
- [ ] Commit `feat(ui): toda la interfaz en inglés y más visual`.

### Task 7: Docs
`README.md`, `HANDOFF.md` (Spanish): objective-fight definition and constants, English UI, visual blocks. Commit `docs: peleas de objetivo, inglés y estilo visual`.
