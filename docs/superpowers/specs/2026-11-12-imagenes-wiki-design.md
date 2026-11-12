# Diseño: imágenes del juego y carriles por color

Fecha: 2026-11-12 · Estado: aprobado por el usuario (2026-11-12)

## Intención

La app ya tiene un diseño oscuro y cuidado (PR #1), pero se basa en texto e iconos de línea. El usuario quiere que se lea **de un vistazo**, con imágenes reales del juego sacadas de deadlock.wiki: retratos de héroes en todas partes, imágenes de los objetivos (Guardians, Walkers, Midboss…) donde se hable de ellos, y los tres carriles diferenciados por color en toda la app. El uso principal es preparar partidas contra rivales y revisar al propio equipo, así que Partidas e Informe son lo más importante.

## Objetivos

1. Retratos de héroes allí donde aparezca un héroe.
2. Imágenes de objetivos en la vista de partida, en el informe y sobre el minimapa.
3. Carriles con identidad propia (nombre y color) en **toda** la app.
4. Mantener la estética actual del PR #1, que ya es cercana al estilo "HUD del juego" que eligió el usuario (opción B del boceto).

## No objetivos

- Cambiar métricas, cálculos o el backend de datos (salvo lo necesario para servir imágenes).
- Reescribir el frontend con un framework o añadir paso de compilación.
- Imágenes de objetos (ítems) y de rangos: quedan para después.
- La urna de almas: aplazada por decisión del usuario. Los datos de partida no traen ningún evento de urna (lo que aparece como "urn" es la habilidad `tengu_urn`); su deducción a partir de posiciones se estudiará más adelante.

## Anti-objetivos (sería un fracaso aunque funcione)

- Que la app dependa de la wiki para pintarse: si la wiki falla o es lenta, ninguna vista debe quedarse rota o vacía.
- Subir el arte de Valve a GitHub.
- Debilitar la política de seguridad (CSP) del PR #1 para poder enlazar imágenes de fuera.
- Nombrar los carriles por lado ("izquierda/derecha"): el minimapa del juego se gira según el equipo, así que el lado cambia y el color no.

## Restricciones

- CSP actual: `img-src 'self' data: blob:`. Las imágenes deben servirse desde la propia app.
- Sin dependencias nuevas (solo biblioteca estándar de Python, JS vanilla).
- Tests existentes (32) deben seguir pasando; las piezas nuevas del servidor llevan tests.

## Enfoques considerados

1. **Proxy y caché de imágenes en la propia app** (elegido). El servidor sirve `/img/...`, descarga la imagen la primera vez desde una lista cerrada de orígenes (cdn.deadlock.wiki y assets-bucket.deadlock-api.com) y la guarda en `data/cache/img/`. Respeta la CSP, funciona sin conexión tras la primera carga y no sube nada al repositorio.
2. Reescribir el frontend con un framework: descartado; rehace lo que ya funciona y añade dependencias.
3. Enlazar las imágenes de la wiki directamente: descartado; rompe la CSP del PR #1 y deja la app a merced de la wiki.

El usuario recibió los tres y la recomendación (1) antes de aplazar el tema; al retomarlo pidió "mejora este diseño con imágenes de la wiki", coherente con (1).

## Decidido por el usuario

- Estilo "HUD del juego" (opción B del boceto `.superpowers/brainstorm/mockups/estilo.html`).
- Carriles diferenciados por color: amarillo, azul y verde.
- Imágenes de deadlock.wiki: personajes, objetivos, etc.

## Diseño

### Carriles

| Carril (id de objetivo) | Nombre | Color oficial | Sobre el mapa con el equipo 0 abajo |
|---|---|---|---|
| 1 | York | amarillo `#F1CC30` | izquierda |
| 3 | Broadway | azul `#29b1cc` | centro |
| 4 | Greenwich | verde `#59b247` | derecha |

Colores tomados de `zipline_paths` de `/v1/assets/map` (los mismos que usa el juego) y coherentes con `Map_colored.png` de la wiki.

- `objetivos.json`: los nombres de carril pasan a "York", "Broadway" y "Greenwich", y cada carril tiene su color (`"color": "#F1CC30"`…), editable como el resto del mapeo.
- En el front, tokens CSS `--lane-york`, `--lane-broadway`, `--lane-greenwich` y un componente `laneChip(carril)` (pastilla con color, nombre y subtítulo "amarillo"/"azul"/"verde") usado en todas las tablas, títulos y leyendas.
- Gráficas por carril (p. ej. "Primer Guardian: carril" del informe): la etiqueta de cada grupo lleva su color, y las secciones por carril llevan una franja lateral del color.
- Minimapa: capa opcional (activada por defecto) con los recorridos de tirolina de cada carril en su color, semitransparente, para orientarse.
- El texto "izquierda/centro/derecha" desaparece; si hace falta orientar, se dice "visto con Hidden King abajo".

### Imágenes: servidor

- Ruta `GET /img/<origen>/<archivo>` con `origen ∈ {wiki, api}`.
  - `wiki` → `https://cdn.deadlock.wiki/<archivo>`.
  - `api` → `https://assets-bucket.deadlock-api.com/assets-api-res/images/<archivo>`.
- Validación: nombre de archivo con caracteres seguros (letras, dígitos, `_ - . % &` y `/` para subcarpetas de la API), sin `..`, extensión `png|jpg|jpeg|webp|svg`; tamaño máximo 5 MB; tipo de contenido de la respuesta debe ser imagen.
- Caché en `data/cache/img/<origen>/<archivo>`; se sirve con `Cache-Control: max-age` largo. Si la descarga falla, 404 rápido y se recuerda el fallo un rato (para no martillear la wiki).
- Catálogo de imágenes en `static/js/art.js`: `heroImg(heroId)` (retrato vertical de la wiki por nombre de héroe; si falla, la imagen de la API del héroe), `objectiveImg(tipo, equipo)` y `laneColor(carril)`. Los nombres de archivo de héroe se derivan del nombre (`Mo & Krill` → `Mo_%26_Krill_vertical.png`).
- `<img>` con `loading="lazy"`, `alt` con el nombre y `onerror` que pasa a la imagen de respaldo y, si también falla, a un marcador con la inicial del héroe.

### Imágenes de objetivos

| Objetivo | Imagen |
|---|---|
| Guardian | no hay imagen propia en la wiki → icono propio con la forma de rombo de `Map_colored.png` |
| Walker | `Walker_Icon.png` |
| Base guardian | `Hidden_King_base_guardians.png` / `Archmother_base_guardians.png` según el dueño |
| Shrine | `Shrines.png` |
| Titan / Core (Patron) | `Patrons.png` |
| Midboss | `Mid-Boss_model.png`; robo/reclamo con `Rejuvenator_crystal.png` |
| KOTH (Unstable Rift) | imagen de la wiki si existe (página "Unstable Rift" / KOTH); si no, icono propio |

**KOTH:** objetivo del usuario. Los datos no traen eventos de cash-in (ni ganador, ni tiempo, ni recuento). Se muestra: (1) sus 2 puntos de aparición sobre el minimapa, de `entities.unstable_rifts` de `/v1/assets/map`; (2) la sección KOTH del informe y de la partida con su imagen, el bloque "no disponible" y la pista "Comeback Gold Koth", como ahora.

### Vistas

- **Partida** (prioridad):
  - Cabecera con la franja de los 6 retratos por equipo a los lados del marcador.
  - Marcador con avatar redondo de cada héroe.
  - Pestaña Objetivos: tres pistas de carril (una por color) con la imagen de cada objetivo en el minuto en que cae, coloreada por el equipo dueño.
  - Midboss con su imagen.
  - Minimapa: iconos de objetivos en su posición (de `objective_positions`), puntos del KOTH y la capa de carriles.
- **Informe** (prioridad):
  - Cabecera con los héroes más jugados por la plantilla en la muestra.
  - Sección de carriles con pastillas y colores de carril, y las líneas de tiempo con imágenes de objetivos. En el informe, el color de cada objetivo sigue siendo "este equipo" (verde) / "rival" (rojo), como ahora; el color del carril va en la pista, no en el objetivo. *(Decisión mía: en el informe importa quién lo tumba, no qué lado.)*
  - Midboss con su imagen.
- **Jugadores**: avatar del héroe principal junto al nombre.
- **Por héroe**: selector en rejilla de retratos en lugar del desplegable.
- **Perfil**: top 5 héroes como tarjetas con retrato.
- **Inicio**: un mosaico de retratos como fondo de la portada.

## Lo que queda a quien lo construya

- Tamaños exactos, recortes de los retratos y animaciones, dentro de la estética actual.
- Icono propio del Guardian (rombo) y del Core si `Patrons.png` no encaja a tamaño pequeño.
- Si una imagen de objetivo de la wiki resulta ilegible a 24–32 px, sustituirla por un icono propio del mismo color (anotar el cambio).

## Riesgos

- La wiki puede renombrar archivos: el respaldo de la API y el marcador con inicial evitan huecos.
- Héroes nuevos sin retrato en la wiki: mismo respaldo.
- Licencia: arte de Valve servido desde la wiki para uso personal y local; no se redistribuye.
