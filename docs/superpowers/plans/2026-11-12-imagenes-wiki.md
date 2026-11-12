# Imágenes del juego y carriles por color — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la app se lea de un vistazo: retratos de héroes e imágenes de objetivos de deadlock.wiki, y los carriles York/Broadway/Greenwich con su color en toda la app.

**Architecture:** El servidor gana un proxy-caché de imágenes (`/img/<origen>/<archivo>`) con lista cerrada de orígenes, para respetar la CSP `img-src 'self'`. Los datos de carril (nombre + color) viven en `objetivos.json` y viajan en las respuestas de partida, informe y mapa. El front gana un módulo `art.js` (retratos, objetivos, pastillas de carril) que usan todas las vistas.

**Tech Stack:** Python 3 (solo biblioteca estándar, `unittest`), JS vanilla en módulos ES, CSS.

**Spec:** `docs/superpowers/specs/2026-11-12-imagenes-wiki-design.md`

## Global Constraints

- Sin dependencias nuevas; sin paso de compilación.
- No tocar la CSP: `img-src 'self' data: blob:` sigue igual. Ninguna imagen se pide fuera de la app desde el navegador.
- Orígenes de imágenes permitidos, exactamente: `wiki` → `https://cdn.deadlock.wiki/`, `api` → `https://assets-bucket.deadlock-api.com/assets-api-res/images/`.
- Caché de imágenes en `data/cache/img/<origen>/…` (`data/` ya está en `.gitignore`). No se añade ninguna imagen del juego al repositorio.
- Colores de carril: York `#F1CC30` (amarillo), Broadway `#29b1cc` (azul), Greenwich `#59b247` (verde). Ids de carril: 1 = York, 3 = Broadway, 4 = Greenwich.
- Nunca "izquierda/centro/derecha" en textos de la UI; si hace falta orientar: "visto con Hidden King abajo".
- La urna queda fuera de este plan.
- Interfaz y mensajes en español. Los 32 tests actuales siguen pasando.
- Trabajar en la rama `feat/imagenes-wiki` (no en `main`).

## Review Focus

1. Wiki caída o archivo inexistente: ninguna vista queda rota; el retrato pasa al respaldo de la API y, si falla, a la inicial del héroe. → test de servidor 404 rápido + fallo recordado (Task 2) y verificación en navegador (Task 3).
2. Nombres de héroe con caracteres especiales (`Mo & Krill`, `The Doorman`, `Lady Geist`) → test de `safe_name` con `&` y verificación de retrato en Task 3.
3. `/img/` como vector de ataque: `..`, rutas absolutas, extensiones no imagen, orígenes desconocidos, respuestas que no son imagen o de más de 5 MB → tests en Task 2.
4. `objetivos.json` antiguo sin `colores` (o editado desde Ajustes) → los colores por defecto se aplican igual → test en Task 1.
5. Pantallas estrechas (≈380 px): franjas de retratos y pistas de carril no desbordan horizontalmente → verificación en navegador con `resize_window` móvil en Tasks 4 y 6.

---

### Task 1: Identidad de carril en los datos

**Files:**
- Modify: `objetivos.json` (bloque `carriles` y nuevo bloque `colores`)
- Modify: `scouting/matches.py` (`load_objective_map`, nuevo `load_lane_styles`, `overview`)
- Modify: `scouting/report/__init__.py` (`run` añade `lanes`)
- Modify: `scouting/report/metricas/m03_carriles.py` (texto informativo)
- Modify: `scouting/server.py` (`objmap_get` devuelve `colores`; `objmap_set` acepta y guarda `colores`)
- Test: `tests/test_lanes.py`

**Interfaces:**
- Produces: `matches.load_lane_styles(path=None) -> dict[int, {"nombre": str, "color": str, "alias": str}]` (siempre incluye 1, 3, 4; usa defaults si falta `colores`).
- Produces: `overview(...)["lanes"]` y `report.run(...)["lanes"]`: `{ "1": {"nombre","color","alias"}, ... }` (claves str).
- Produces: `GET /api/objective-map` → `{"objetivos", "carriles", "colores"}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_lanes.py`

```python
def test_lane_styles_defaults_and_names():
    s = matches.load_lane_styles()
    assert s[1] == {"nombre": "York", "color": "#F1CC30", "alias": "amarillo"}
    assert s[3] == {"nombre": "Broadway", "color": "#29b1cc", "alias": "azul"}
    assert s[4] == {"nombre": "Greenwich", "color": "#59b247", "alias": "verde"}

def test_lane_styles_without_colores_block(tmp_path):  # objetivos.json antiguo
    # copia de objetivos.json sin "colores" -> mismos colores por defecto
    ...
    assert matches.load_lane_styles(p)[1]["color"] == "#F1CC30"

def test_objective_label_uses_lane_name():
    objs, lanes = matches.load_objective_map()
    assert matches.objective_label(1, objs, lanes) == "Guardian · York"
    assert matches.objective_label(8, objs, lanes) == "Walker · Greenwich"

def test_overview_and_report_carry_lanes():
    ov = matches.overview(FIXTURE["match_info"], {})
    assert ov["lanes"]["3"]["nombre"] == "Broadway"
    out = report.run("x", [FIXTURE], TEAM1_ACCOUNTS)
    assert out["lanes"]["4"]["color"] == "#59b247"

def test_no_side_words_in_lane_texts():
    out = report.run("x", [FIXTURE], TEAM1_ACCOUNTS)
    txt = json.dumps(out, ensure_ascii=False).lower()
    for w in ("izquierda", "(izq.)", "(der.)", "derecha", "(centro)"):
        assert w not in txt
```
(Usar `unittest.TestCase` como el resto del proyecto; `tmp_path` → `tempfile.mkdtemp()`.)

- [ ] **Step 2: Run** `python -m unittest tests.test_lanes -v` — Expected: FAIL (`load_lane_styles` no existe).

- [ ] **Step 3: Implement**
  - `objetivos.json`: `"carriles": {"1": "York", "2": "Carril 2", "3": "Broadway", "4": "Greenwich"}` y `"colores": {"1": {"color": "#F1CC30", "alias": "amarillo"}, "3": {"color": "#29b1cc", "alias": "azul"}, "4": {"color": "#59b247", "alias": "verde"}}`. Actualizar `_nota` (sin lados).
  - `load_lane_styles`: defaults en una constante `LANE_DEFAULTS` con los tres valores de la Global Constraints; el archivo los sobrescribe.
  - `overview()` y `report.run()` añaden `"lanes"`.
  - `m03_carriles.py`: sustituir el texto "1 = izquierda, 3 = centro, 4 = derecha…" por "Carriles por color: York (amarillo), Broadway (azul) y Greenwich (verde)…" y mantener la nota del mapeo editable.
  - `server.py`: `objmap_get` añade `colores`; `objmap_set` valida colores `^#[0-9a-fA-F]{6}$` y los guarda (400 si no). Si el POST no trae `colores` (Ajustes hoy no los envía), se conservan los del archivo. Test: POST sin `colores` → `load_lane_styles()[1]["color"]` sigue siendo `#F1CC30`.

- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: todo OK (33+ tests).

- [ ] **Step 5: Commit** `git commit -m "feat: carriles York/Broadway/Greenwich con color en datos e informe"`

---

### Task 2: Proxy-caché de imágenes

**Files:**
- Create: `scouting/images.py`
- Modify: `scouting/server.py` (`do_GET` despacha `/img/` → `self._image(path)`)
- Test: `tests/test_images.py`

**Interfaces:**
- Produces: `images.SOURCES = {"wiki": "https://cdn.deadlock.wiki/", "api": "https://assets-bucket.deadlock-api.com/assets-api-res/images/"}`
- Produces: `images.safe_name(origin: str, name: str) -> str | None` (nombre ya decodificado; `None` si no es válido).
- Produces: `images.get(origin: str, name: str, opener=None) -> tuple[bytes, str] | None` (bytes, content-type; `None` si no disponible). `opener(url) -> (status, headers: dict, body: bytes)` inyectable para tests; por defecto urllib con timeout 15 s y User-Agent `deadlock-scouting-local/1.0`.
- Produces: `GET /img/<origen>/<archivo>` → 200 con `Cache-Control: public, max-age=604800` o 404 JSON.

- [ ] **Step 1: Write the failing tests** in `tests/test_images.py` (redirigir la caché a un `tempfile.mkdtemp()` parcheando `images.CACHE_DIR`):

```python
def test_safe_name():
    assert images.safe_name("wiki", "Mo_&_Krill_vertical.png") == "Mo_&_Krill_vertical.png"
    assert images.safe_name("api", "heroes/abrams_sm.webp") == "heroes/abrams_sm.webp"
    for bad in ["../x.png", "a/../../b.png", "/etc/x.png", "x.exe", "x.png?y=1", "C:x.png", ""]:
        assert images.safe_name("wiki", bad) is None
    assert images.safe_name("evil", "x.png") is None
    assert images.safe_name("wiki", "sub/x.png") is None   # la wiki no usa subcarpetas

def test_fetch_caches_and_reuses():
    calls = []
    def opener(url): calls.append(url); return 200, {"Content-Type": "image/png"}, PNG_1PX
    assert images.get("wiki", "Walker_Icon.png", opener) == (PNG_1PX, "image/png")
    assert images.get("wiki", "Walker_Icon.png", opener)[0] == PNG_1PX
    assert calls == ["https://cdn.deadlock.wiki/Walker_Icon.png"]

def test_upstream_url_is_quoted():
    # "Mo_&_Krill_vertical.png" -> ".../Mo_%26_Krill_vertical.png"

def test_rejects_non_image_and_oversize():
    # Content-Type text/html -> None ; cuerpo de 5 MB + 1 -> None; nada escrito en caché

def test_failure_is_remembered():
    # opener devuelve 404; dos llamadas seguidas -> una sola llamada al opener (ventana 600 s)

def test_http_route():
    # con el servidor de test (como HttpHardening): GET /img/wiki/..%2Fx.png -> 404;
    # con un archivo ya en caché: GET /img/wiki/Walker_Icon.png -> 200, Content-Type image/png,
    # Cache-Control contiene max-age=604800; Host ajeno -> 403 (check existente)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_images -v` — Expected: FAIL (módulo no existe).

- [ ] **Step 3: Implement** `scouting/images.py`:
  - Regex de nombre: segmentos `[A-Za-z0-9_\-.&%()]+`; `wiki` admite 1 segmento, `api` hasta 3; extensión final `png|jpg|jpeg|webp|svg`; ningún segmento `.`/`..`.
  - Límite 5 MB (`MAX_BYTES = 5 * 1024 * 1024`); Content-Type debe empezar por `image/`.
  - Escritura atómica (`.tmp` + `os.replace`); guardar el content-type junto al archivo (`<archivo>.type`) o derivarlo de la extensión al servir.
  - Fallos recordados en memoria 600 s (`_FAILED: dict[(origin,name)] -> ts`).
  - Bloqueo por clave para no descargar dos veces la misma imagen en paralelo.
  - `server.py`: en `do_GET`, `if u.path.startswith("/img/")`: separar `<origen>/<resto>`, `urllib.parse.unquote(resto)`, `images.get(...)`; 200 con `_send(200, body, ctype, headers={"Cache-Control": ...})` (ajustar `_send` para que el `Cache-Control` pasado en `headers` sustituya al de por defecto); 404 si `None`.

- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: todo OK.

- [ ] **Step 5: Commit** `git commit -m "feat: proxy-caché de imágenes de la wiki y la API"`

---

### Task 3: Módulo de arte del front y estilos base

**Files:**
- Create: `static/js/art.js`
- Modify: `scouting/server.py` (`heroes()`: `image` pasa a ruta `/img/api/...`; añade `wiki_image`)
- Modify: `static/app.css` (tokens de carril, `.portrait`, `.avatar`, `.lane-chip`, `.obj-img`)
- Test: `tests/test_images.py` (test de `heroes()`)

**Interfaces:**
- Consumes: `/img/<origen>/<archivo>` (Task 2); `lanes` de Task 1.
- Produces (`art.js`):
  - `wikiHeroFile(name: string) -> string` — `"Mo & Krill"` → `"Mo_%26_Krill_vertical.png"`, `"The Doorman"` → `"The_Doorman_vertical.png"`.
  - `heroPortrait(hero: {id, name, image?}, {size='md'|'sm'|'lg', shape='card'|'round'}) -> HTMLElement` — `<img loading="lazy" alt=name>` con cadena de respaldo wiki → `hero.image` (API) → `<span class="avatar initial">` con la inicial.
  - `objectiveImg(type: string, ownerTeam: 0|1|null, {size}) -> HTMLElement` — mapa de la spec: Walker `Walker_Icon.png`, Base guardian `Hidden_King_base_guardians.png`/`Archmother_base_guardians.png`, Shrine `Shrines.png`, Titan/Core `Patrons.png`, Midboss `Mid-Boss_model.png`, Rejuvenator `Rejuvenator_crystal.png`, KOTH `Unstable_Rift.png`; Guardian → SVG en línea de rombo. Respaldo: icono de `icons.js`.
  - `laneStyle(laneId, lanes) -> {nombre, color, alias}` y `laneChip(laneId, lanes) -> HTMLElement` (pastilla con punto de color, nombre y alias en pequeño; `style="--lane: <color>"`).
  - `getLanes() -> Promise<lanes>` (cacheado, de `/api/objective-map`).
- Produces (`/api/heroes`): cada héroe `{id, name, image: "/img/api/heroes/…", wiki_image: "/img/wiki/<Nombre>_vertical.png"}`.

- [ ] **Step 1: Write the failing test** — `heroes()` con `kv hero_images` de ejemplo `{"1": "https://assets-bucket.deadlock-api.com/assets-api-res/images/heroes/inferno_sm.webp"}` devuelve `image == "/img/api/heroes/inferno_sm.webp"` y `wiki_image == "/img/wiki/Infernus_vertical.png"`; una URL de otro host → `image` `None`.
- [ ] **Step 2: Run** el test — FAIL.
- [ ] **Step 3: Implement** `heroes()` + `art.js` + CSS. Tokens: `--lane-york: #F1CC30; --lane-broadway: #29b1cc; --lane-greenwich: #59b247;`.
- [ ] **Step 4: Verify**
  - `python -m unittest discover -s tests` → OK.
  - En el navegador (`preview_start scouting`), consola: `const a = await import('/static/js/art.js'); document.body.append(a.heroPortrait({id:18,name:'Mo & Krill'}), a.heroPortrait({id:999,name:'Nuevo Héroe'}), a.laneChip(1, await a.getLanes()))` → el primero muestra el retrato, el segundo la inicial "N", la pastilla dice "York · amarillo" en amarillo. Sin errores CSP en consola.
- [ ] **Step 5: Commit** `git commit -m "feat: módulo de arte (retratos, objetivos, carriles) en el front"`

---

### Task 4: Vista de partida

**Files:**
- Modify: `static/js/views/matches.js` (`scoreboard`, `resumen`, `objetivos`, `midboss`, `minimapa`)
- Modify: `static/js/map.js` (nuevo tipo de capa `images` y uso de `paths` con color por capa)
- Modify: `scouting/server.py` (`map_info` añade `lane_paths` y `koth`)
- Modify: `static/app.css`
- Test: `tests/test_images.py` (test de `map_info`)

**Interfaces:**
- Consumes: `art.js` (Task 3), `m.lanes` (Task 1).
- Produces (`/api/map`): `lane_paths: [{lane: 1|3|4, color, points: [[x, y], ...]}]` (punto absoluto = `origin[0:2]` + `P0_points[i][0:2]` de cada `zipline_paths`; carril asignado comparando el color, sin distinguir mayúsculas, con `load_lane_styles`) y `koth: [[x, y], ...]` (de `entities.unstable_rifts[].position`).
- Produces (`map.js`): capa `{kind: 'images', items: [{x, y, src, size, label}]}` (dibuja la imagen ya cargada centrada; si no cargó, un círculo con el color de `label`). `paths` admite `L.color` por capa (ya lo hace) y `L.width`.

- [ ] **Step 1: Write the failing test** — `map_info` con un `map_asset` falso de 2 tirolinas (`#29b1cc` origen `[-1280,-10774,0]`, puntos `[[0,0,0],[0,1000,5]]`; `#F1CC30`) devuelve `lane_paths[0] == {"lane": 3, "color": "#29b1cc", "points": [[-1280, -10774], [-1280, -9774]]}` y `koth` con las posiciones x, y.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**
  - Cabecera de partida: franja de 6 retratos por equipo a cada lado del marcador (estilo B del boceto `.superpowers/brainstorm/mockups/estilo.html`, clases `.B .hero-banner`).
  - Marcador/tabla: `heroPortrait(..., {shape:'round', size:'sm'})` delante del nombre del héroe.
  - Objetivos: una pista por carril (York, Broadway, Greenwich, en ese orden) con borde y fondo del color del carril; cada objetivo destruido es `objectiveImg(type, owner)` en su minuto, con borde del color del equipo dueño y `title` "Guardian de Hidden King · 9:28". Fila extra "Base" para Shrines, Titan y Core. Se conserva la tabla y el CSV debajo.
  - Tarjeta KOTH en Objetivos: `objectiveImg('KOTH')`, bloque "No disponible: la API no trae los cash-in del KOTH" y la columna Comeback Gold Koth por equipo.
  - Midboss: `objectiveImg('Midboss')` en la cabecera; las filas con robo llevan `objectiveImg('Rejuvenator')`.
  - Minimapa: capas nuevas activables "carriles" (on por defecto: `paths` con `lane_paths`, ancho 3, alfa 0.55), "objetivos" (`images` en `objective_positions` con la imagen de su tipo: `tier1_*` Guardian, `tier2_*` Walker, `titan` Patron, `core` Patron) y "KOTH" (`images` con `Unstable_Rift.png`).
- [ ] **Step 4: Verify**
  - Tests → OK.
  - Navegador en `#partidas/109084310`: la franja muestra 12 retratos; pestaña Objetivos con 3 pistas amarilla/azul/verde y el Walker de Greenwich de Hidden King a 24:28; minimapa con carriles de color y 2 marcas de KOTH. `resize_window` mobile: sin scroll horizontal de página (`document.documentElement.scrollWidth <= innerWidth`).
- [ ] **Step 5: Commit** `git commit -m "feat: partida con retratos, pistas de carril e imágenes de objetivos"`

---

### Task 5: Informe de equipo

**Files:**
- Modify: `scouting/report/__init__.py` (`run` añade `our_heroes`)
- Modify: `static/js/blocks.js`, `static/js/charts.js` (`timeline` con imágenes; etiquetas de carril coloreadas)
- Modify: `static/js/views/report.js` (cabecera con héroes)
- Test: `tests/test_match.py` (nuevo test en `SideAndReport`)

**Interfaces:**
- Consumes: `art.js`, `out.lanes` (Task 1).
- Produces: `report.run(...)["our_heroes"]: [{"hero_id": int, "matches": int}]` ordenado por partidas desc, máx. 12, contando héroes del lado propio en cada partida analizada.
- Produces: `timeline({rows, lanes, art})`: si un evento trae `kind` de objetivo, se pinta `objectiveImg(kind)` (≤ 22 px) con borde de `side`; filas cuyo `label` empieza por un nombre de carril llevan franja del color del carril.

- [ ] **Step 1: Write the failing test** — con la partida fixture y la plantilla del equipo 1: `out["our_heroes"]` tiene 6 elementos, todos con `matches == 1`, y sus `hero_id` son los del equipo 1.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**
  - `run` calcula `our_heroes`.
  - Cabecera del informe: rejilla de `heroPortrait` con "×N" de `our_heroes`.
  - `blocks.js`: en `bars`, si una etiqueta coincide con un nombre de `lanes`, se pinta como `laneChip`; en `table`, celdas de la columna `carril` como `laneChip`; títulos de sección "Midboss" y "KOTH / Rifts" llevan `objectiveImg('Midboss')`/`objectiveImg('KOTH')`.
  - La línea de tiempo por partida usa imágenes de objetivos; colores de evento siguen siendo este equipo/rival (verde/rojo).
- [ ] **Step 4: Verify**
  - Tests → OK.
  - Navegador: informe con la cuenta `1055638874` y la partida `109084310`: cabecera con 6 retratos; "Primer Guardian: carril" con etiquetas York/Broadway/Greenwich en su color; línea de tiempo con imágenes. Sin errores de consola.
- [ ] **Step 5: Commit** `git commit -m "feat: informe con héroes, carriles por color e imágenes de objetivos"`

---

### Task 6: Resto de vistas

**Files:**
- Modify: `static/js/views/players.js` (avatar del héroe principal)
- Modify: `static/js/views/hero.js` (selector en rejilla de retratos)
- Modify: `static/js/views/profile.js` (top 5 como tarjetas)
- Modify: `static/js/views/home.js` (mosaico de retratos en la portada)
- Modify: `static/app.css`

**Interfaces:**
- Consumes: `heroPortrait`, `getHeroes()` (`/api/heroes` de Task 3).

- [ ] **Step 1: Implement**
  - Jugadores: `heroPortrait(heroes[0], {shape:'round', size:'sm'})` antes del nombre (si tiene héroes).
  - Por héroe: rejilla de tarjetas (retrato + nombre) con búsqueda; la seleccionada resaltada; se conserva `store.get('hero')`. Accesible con teclado (botones).
  - Perfil: top 5 como tarjetas con retrato, partidas, WR y KDA; la tabla completa sigue en el desplegable.
  - Inicio: mosaico de retratos (los 12 héroes más jugados entre los jugadores) atenuado detrás del bloque de bienvenida.
- [ ] **Step 2: Verify**
  - `python -m unittest discover -s tests` → OK.
  - Navegador: cada vista sin errores de consola; Por héroe usable con Tab/Enter; `resize_window` mobile sin scroll horizontal en las cuatro vistas.
  - Con la red cortada a la wiki (simular renombrando temporalmente `images.SOURCES["wiki"]` a un host inválido y vaciando `data/cache/img/wiki`), los retratos pasan a la imagen de la API o la inicial.
- [ ] **Step 3: Commit** `git commit -m "feat: retratos en jugadores, por héroe, perfil e inicio"`

---

## Cierre

- [ ] `python -m unittest discover -s tests` → OK.
- [ ] `git status` limpio salvo `data/`; ninguna imagen del juego en el repositorio (`git ls-files | grep -Ei "vertical|Walker_Icon|Patrons|Shrines|Mid-Boss|Unstable_Rift"` → vacío).
- [ ] Actualizar `README.md` (sección "Cómo funciona": proxy de imágenes y carriles) y `HANDOFF.md` §12.
