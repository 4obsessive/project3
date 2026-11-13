# Diseño: fase de líneas (min 0–10) y desglose por jugador

Fecha: 2026-11-13 · Estado: borrador, pendiente de aprobación del usuario

## Intención

Preparar partidas contra un rival y analizar al propio equipo. El usuario quiere saber cómo juega cada pareja de héroes
en su línea durante la fase de líneas (hasta el minuto 10) y un desglose jugador por jugador. Regla del usuario
(2026-11-13): **todo lo que sale en el informe sale de cada partida**; la vista de una partida muestra lo mismo que el
informe, a escala de una sola partida. Regla vigente: nada inventado ni interpretado; lo que no está en los datos →
«no disponible».

## Objetivos

1. **Fase de líneas, por línea (York/amarillo, Broadway/azul, Greenwich/verde)**, ventana 0–600 s de juego:
   - Dúo (pareja de héroes del mismo equipo en la misma línea) que **más daño hace** a héroes.
   - Dúo que **más daño recibe** de héroes.
   - Dúo que **tira antes el Guardian enemigo** de su línea (minuto en que cae, aunque sea después del 10).
   - Dúo que **pierde antes su Guardian**.
   - **Primer gankeo** de la línea: el primer segundo en que un jugador cuya línea es otra hace daño (o mata) a un jugador
     de esa línea. Se indica quién gankea (héroe y su línea), a quién y en qué minuto; separado en gankeo hecho por el
     equipo y gankeo sufrido.
   - Daño de cada dúo separado en: daño a los rivales de su línea / daño recibido de los rivales de su línea / daño
     recibido de gankeos.
2. **Desglose por jugador**, jugador por jugador: héroes jugados, línea, KDA, dónde muere más y dónde mata más (zonas del
   mapa con minimapa resaltado, como las tablas de zonas del informe), farm (troopers/min, jungla/min, last hits, denies),
   economía (net worth/min, net worth a los 10 min, almas por fuente), daño a héroes, daño recibido, y sus números de
   fase de líneas (daño hecho/recibido hasta el 10, muertes antes del 10, gankeos hechos y sufridos).
3. **Dos sitios, mismo cálculo**: el informe de equipo suma las partidas (medias, recuentos, «en X de N partidas»); la vista
   de partida muestra los mismos bloques para esa partida (los dos equipos, los 6 dúos y los 12 jugadores).

## Datos (verificado el 2026-11-13, partida 135801973)

- `assigned_lane` de la API **no es fiable** (jugadores con la misma línea asignada juegan en lados opuestos). La línea de
  cada jugador se obtiene de sus **posiciones** (metadatos, 1 por segundo): mediana de posiciones vivas entre ~60 y
  ~300 s, asignada a la línea cuyo recorrido (zipline de `map_info.lane_paths`, colores amarillo/azul/verde) está más
  cerca. En las partidas comprobadas salen 2 jugadores por equipo y línea. Si no salen 2 y 2 se marca la línea como
  «no disponible» para esa partida en vez de forzar dúos.
- Daño entre héroes con su segundo: **consulta nueva al demo** (4.ª por partida; probada):
  ```sql
  SELECT pa.acc AS att, pv.acc AS vic, CAST(d.tick / 320 AS INT) AS b, sum(d.damage) AS dmg
  FROM DamageEvent d
  JOIN (SELECT DISTINCT ("m_hHeroPawn" & 16383) AS pawn, "m_unEconAccountID" AS acc FROM CCitadelPlayerController
        WHERE "m_hHeroPawn" IS NOT NULL AND "m_unEconAccountID" > 0) pa ON d.entindex_attacker = pa.pawn
  JOIN (SELECT DISTINCT ("m_hHeroPawn" & 16383) AS pawn, "m_unEconAccountID" AS acc FROM CCitadelPlayerController
        WHERE "m_hHeroPawn" IS NOT NULL AND "m_unEconAccountID" > 0) pv ON d.entindex_victim = pv.pawn
  WHERE d.tick < <LIMITE> AND d.victim_class = 1 AND pa.acc <> pv.acc GROUP BY 1,2,3 ORDER BY 3
  ```
  Tramos de 5 s (320 ticks). `<LIMITE>` = ticks de 600 s de juego más las pausas (fórmula de tiempo ya usada:
  `(tick − ticks en pausa) / 64`); el constructor elige cómo fijarlo (p. ej. un margen y recortar al convertir).
  Cada fila se pasa a segundos de juego con la fórmula existente. Cuentas → jugadores por `account_id`.
- Kills con segundo exacto: `death_details` de los metadatos (ya usado).
- Guardians por línea: `matches.objectives()` (ya existe, con línea y minuto en que cae).
- Farm/economía: `matches.economy()` y `stats` (ya existen).
- **Sin demo** (partidas antiguas o pendientes): daño de fase de líneas interpolado al 600 s desde `damage_matrix`
  (muestras cada 180 s), sin separar daño de gankeos; gankeos solo por kills (un jugador de otra línea mata a uno de la
  línea). Cada bloque indica qué fuente usó y en cuántas partidas.

## No objetivos

- Fases posteriores al minuto 10 (salvo el minuto en que cae cada Guardian).
- La urna (aplazada). «Haunts» (sin correspondencia conocida).
- Interpretaciones o consejos («deberían…»): solo datos y recuentos.

## Anti-objetivos

- Formar dúos o líneas a la fuerza cuando las posiciones no dan 2 y 2.
- Contar como gankeo el daño entre rivales de la misma línea.
- Que el informe y la vista de partida den números distintos para la misma partida.

## Restricciones

- Python 3.15 stdlib, JS vanilla. Interfaz en español. Carriles por nombre y color, nunca por lado.
- Presupuesto del demo: 150 consultas/h; con 4 por partida, ~37 partidas/h. Las partidas ya `done` necesitan la consulta
  nueva: se piden solo las que falten (no repetir las 3 anteriores; los resultados crudos ya se guardan).
- Tests sin red; guardar como fixture el resultado real de la consulta nueva para la partida 135801973.

## Enfoques

1. **Demo + posiciones** (elegido por el usuario): daño exacto por segundo y gankeos aunque no maten; respaldo con
   metadatos cuando no hay demo.
2. Solo metadatos: sin coste de consultas, pero daño cada 3 min y gankeos solo por kills. Queda como respaldo.

## Decisiones tomadas en la revisión (llamadas mías; el usuario puede corregirlas)

- **De quién es el informe:** como el resto del informe, cubre al equipo analizado (la plantilla). Para preparar contra un
  rival se genera el informe con la plantilla del rival; para analizarse, con la propia. Los dúos y jugadores del informe
  son los de ese equipo; los rivales concretos de cada partida se ven en la vista de partida (los dos equipos).
- **Ranking de dúos:** se listan todos los dúos de héroes del equipo por línea con su `n` (partidas), ordenados por la
  media. No se oculta ningún dúo; el `n` siempre visible evita leer como patrón un dúo visto una vez.
- **Identidad de jugador:** el jugador de la app (cuentas enlazadas en Jugadores), con la cuenta como respaldo si no está
  enlazada.
- **Gankeo:** la línea de cada jugador es fija en la partida. Se busca entre 60 s y 600 s (antes, todos van de camino);
  cuenta cualquier daño > 0 o kill de un jugador de otra línea a uno de esta línea.
- **Línea «no disponible» en una partida:** esa partida no cuenta en los bloques que dependen de la línea (dúos, gankeos,
  daño de fase de líneas) y sí en KDA, farm, economía y mapas. Cada bloque dice su `n`.
- **Guardian que no cae:** no se inventa un tiempo. Media sobre las partidas en que cayó y, aparte, «no cae en X de N».
- **Partidas ya hechas:** la consulta nueva se encola sola para todas las partidas con demo, detrás de las nuevas (mismo
  orden que hoy). Mientras falte, el informe muestra lo que haya y dice en cuántas partidas está.
- **Sin demo:** en la vista de partida, el daño de fase de líneas sale de `damage_matrix` interpolado y marcado «aprox.,
  sin demo»; el reparto rivales de línea / gankeos sale «no disponible». En el informe, las medias de daño de fase de
  líneas usan solo partidas con demo (con su `n`); las aproximadas no se mezclan.

## Lo que queda al constructor

- Algoritmo concreto de línea por posiciones (ventana temporal, distancia a los recorridos) y el umbral de «2 y 2».
- Forma del resumen de fase de líneas por partida y cómo se agrega en el informe (medias por dúo de héroes; un dúo se
  identifica por la pareja de héroes, sin importar el orden, y su línea).
- Presentación en informe y partida dentro del estilo actual (v3 + CNS), reutilizando tablas, barras y mapas de zonas.
- Cómo pedir solo la consulta nueva para partidas ya `done` (el esquema de `demo_jobs` ya guarda los resultados crudos).
