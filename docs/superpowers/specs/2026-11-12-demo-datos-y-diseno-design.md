# Diseño: datos del demo (rejuvenators, KOTH, midboss, economía por minuto), mapas de zonas y estilo "City Never Sleeps"

Fecha: 2026-11-12 · Estado: revisado; pendiente de aprobación del usuario

## Intención

La app se usa para preparar partidas contra un rival y para analizar al propio equipo; Partidas e Informe de equipo son lo
principal. El usuario quiere más información de los objetivos de mitad de partida (midboss y sus rejuvenators, KOTH cash-in),
más economía (almas por fuente y por minuto) y que las zonas donde se gana o pierde se vean en el mapa. Además, un rediseño
visual inspirado en https://www.playdeadlock.com/cityneversleeps.

Regla del usuario (2026-11-12): **todo lo que no venga de las estadísticas se elimina**. Nada de deducciones por
posiciones u otras heurísticas. Lo que no está en los datos se muestra como «no disponible».

## Descubrimiento que lo hace posible (verificado en vivo el 2026-11-12)

edl.gg obtiene rejuvenators y KOTH del **demo** de la partida. La API de deadlock-api permite consultar el demo con SQL:

- `POST https://api.deadlock-api.com/v1/matches/demo/query` con `{"match_id", "query", "format": "ndjson"}` → `{job_id, status}`.
  La consulta se valida al enviarla (400 si una tabla/columna no existe).
- `GET /v1/matches/demo/query/{job_id}` → `status` queued/running/done/failed; con `done`, `result_url`.
- El resultado está en `https://demo-extracts.deadlock-api.com/<job>.ndjson.zst` (zstd). **Exige cabecera `User-Agent`** (sin ella
  da 403). Python 3.15 descomprime con `compression.zstd` (biblioteca estándar, sin dependencias).
- Límite: 200 consultas/h por IP (400/h con API key). Tarda ~15 s–1 min. Envíos idénticos (match, query, formato) reutilizan
  caché del servidor.
- Disponibilidad: partidas de octubre y noviembre de 2026 (p. ej. 126060059, 134513986, 135801973) → sí. Partida 109084310
  (fixture de los tests) → 404 «No demo available». Partida en curso sin salts → 404.
- Esquema: `GET /v1/matches/demo/schema?match_id=`. Nombres de tabla sin comillas (se normalizan); **columnas con mayúsculas
  entre comillas dobles**. La tabla `CCitadelGameRules` no existe como tal: usar `CCitadelGameRulesProxy` con columnas
  `m_pGameRules__…`.

Consultas probadas en la partida 135801973 (equipos del demo: 2 = Amber = Hidden King = equipo 0 de la API; 3 = Sapphire =
Archmother = equipo 1):

1. **Rejuvenators** — `SELECT tick, killing_team, user_team, event_type FROM RejuvStatusEvent`. `event_type = 4`: un jugador de
   `user_team` coge un rejuvenator del midboss que mató `killing_team`. Salen 3 filas por midboss (reparto 3/0, 2/1…).
   Otros `event_type` (5, 6) no se usan salvo que el constructor confirme qué son.
2. **KOTH** — en `CCitadelGameRulesProxy`, transiciones de `m_nKothScoringTeam`, `m_timeKothScoring`,
   `m_timeKothCashInStarted`, `m_timeKothGiveUp` (filtrar filas con algún valor > 0 y agrupar). Ejemplo real:
   cash-in empieza 787.5 s → equipo 3 lo completa en 805.5 s; empieza 1184.9 → equipo 2 en 1206.1; empieza 1643.3 → equipo 2
   en 1650.2. Un cash-in que empieza y vuelve a 0 sin `m_nKothScoringTeam` > 0 = abandonado/no completado. Los tiempos de estas
   columnas ya son segundos de juego.
3. **Daño al midboss** — `DamageEvent` trae `entindex_victim`, `entindex_attacker`, `victim_class`, `attacker_class`, `damage`.
   Falta identificar al midboss (su `victim_class` o su entidad) y el equipo del atacante (p. ej. vía `CCitadelPlayerPawn`
   `m_iTeamNum`). **Sin verificar**: si el constructor no logra identificarlo de forma fiable, esta parte se quita.
4. **Almas por minuto** — `GoldHistoryEvent(entindex_player, minute_records[match_minute, gold_records[currency_source, gold, events]])`.
   Columna con listas anidadas: el constructor decide si aplanar en SQL o en Python.

Ticks → segundos: el constructor debe calibrarlo (en 135801973 el tick 47326 ≈ 787 s de juego, ~60 ticks/s con desfase
inicial); comprobar contra `mid_boss[].destroyed_time_s` de los metadatos.

## Objetivos

1. **Datos del demo, automáticos.** Al guardar una partida (descarga, importación o desde el informe), se piden en segundo plano
   los datos del demo y se guardan. Nunca se repite una consulta ya resuelta. Si no hay demo, se recuerda («sin demo») y se
   muestra «no disponible».
2. **Midboss** (Partidas e Informe): por cada midboss, quién lo mata, reparto de los 3 rejuvenators por equipo y, si el
   punto 3 se verifica, daño por equipo → equipo que lo inició (más daño) y **robado** = lo mata el equipo que no lo inició.
   En el informe: cuántos midboss consigue el equipo, rejuvenators cogidos de media, robos hechos y sufridos.
3. **KOTH cash-in** (Partidas e Informe): lista de cash-in con inicio, quién lo completa y cuándo (o «no completado»).
   En el informe: cash-in completados por el equipo y por el rival.
4. **Mecánica de remontada**: marcar en el tiempo cuándo un equipo va **≥ 10 % por detrás en almas** (tiene resistencias de
   remontada). Se calcula con los datos (almas por equipo por minuto del demo; si no hay demo, con el net worth interpolado de los
   metadatos, indicándolo). Cada cash-in de KOTH y cada midboss se etiqueta con si el equipo que lo consigue estaba en remontada.
5. **Economía ampliada** (Partidas e Informe): desglose de almas por fuente como en la pantalla del juego (Troopers,
   Objetivos, Jungla, Kills, Asistencias, Denies, Catch-up de equipo, Rompibles…), por jugador y por equipo; y ratios por minuto:
   troopers/min, jungla/min, troopers+jungla/min, almas/min, almas por fuente/min, y su evolución por fases (0–10, 10–20, 20+ min).
   Sin demo, el desglose final sale de `gold_sources` de los metadatos (ya disponible en todas las partidas); lo por-minuto
   requiere el demo o se da en tramos de las muestras de `stats`.
6. **Mapas en las zonas** (Informe, sección mapa): junto a «Zonas con más muertes», «Zonas con más kills» y «Dónde ganan y pierden
   enfrentamientos», un minimapa que resalte exactamente esas zonas (las celdas de cada tabla), para no tener que buscarlas en el
   mapa general.
7. **Rediseño visual** de toda la app inspirado en City Never Sleeps (ver más abajo).
8. **Eliminar toda interpretación ya existente** (decisión del usuario, 2026-11-12: «Elimina todo lo que sea interpretación»):
   - Midboss: el «robo» basado en `team_claimed` ≠ quien lo mata (`stolen` en `matches.midboss`, columna «¿Robo?», nota
     «interpretación» en Partidas, `robos` y sus conclusiones en m04). Se sigue mostrando, como hecho, quién lo mata y quién lo
     reclama según los metadatos.
   - Midboss: el «contexto» (ventaja/igualdad/desventaja por margen de net worth) y el texto de tono `interpretation` de m04.
     Las cifras de kills antes del midboss y la diferencia de net worth en ese momento son datos y pueden quedarse como números.
   - MVP «estimado: KDA × oro» en Partidas: solo se muestra MVP si la partida trae `mvp_rank`; si no, no hay MVP.
   - KOTH: el bloque «Única pista: Comeback Gold Koth» y su lectura («ganó al menos un KOTH yendo por detrás»). Lo sustituye el
     KOTH del demo. El valor de la estadística puede quedar como columna numérica sin explicación interpretativa.
   - Conclusiones: todas las `ctx.finding(..., confirmed=False)` (m02, m03, m04) y el tipo «interpretación» de m99, el tono
     `interpretation` de los bloques de texto (`blocks.js` TONE) y su leyenda. Quedan solo conclusiones que son recuentos de los
     datos («van por delante a los 10 min en X de N»).
   - Se mantiene la **detección del lado** de cada partida (qué plantilla juega en qué equipo): el informe no funciona sin ella, se
     basa en las cuentas de los jugadores (dato) y ya se puede corregir a mano.
   - Se mantiene el mapeo de ids de objetivo a carril/tipo (`objetivos.json`): está verificado con datos y es editable.
   - Los tests que comprueban lo eliminado (`stolen` en test_match.py, etc.) se actualizan.

## Fuentes de almas (mapeo)

`currency_source` / `gold_sources[].source` (EGoldSource). Verificado con datos: 1 kills a héroes, 2 troopers, 3 jungla
(neutrales), 4 jefes/objetivos, 6 asistencias, 7 denies, 11 objeto Cultist Sacrifice (solo en quien lo compró), 12 rompibles
(todos los jugadores, 3–7 k). Por el esquema de la API (`avg_gold_*`): 5 tesoro, 8 bonus de equipo (catch-up), 9 asesinato por
habilidad, 10/13 objetos (Goose Egg / Trophy Collector). El constructor confirma 5/8/10/13 si puede; si no, se muestran con el
nombre de la API («Tesoro», «Bonus de equipo») y una nota. «Haunts» de la captura del usuario no tiene correspondencia
conocida: se pregunta al usuario y, mientras, no se inventa.

## No objetivos

- La urna de almas (aplazada por el usuario).
- Deducciones por posición o heurísticas (quién inició el midboss por presencia en el foso, ocupación de la grieta, etc.).
- Datos en directo de partidas en curso.
- Reescribir el frontend con un framework o añadir paso de compilación.

## Anti-objetivos

- Mostrar como dato algo deducido o inventado.
- Que una vista se rompa o se bloquee esperando al demo: el demo llega cuando llega; mientras, la vista muestra lo de los
  metadatos y un estado «datos del demo: pendientes/no disponibles».
- Agotar el límite de la API: nunca relanzar consultas ya resueltas, ni en bucle tras errores.
- Subir arte de Valve al repositorio o relajar la CSP.

## Restricciones

- Solo biblioteca estándar de Python 3.15 (`compression.zstd` incluido) y JS vanilla. Local en 127.0.0.1.
- Nuevo host de salida: `demo-extracts.deadlock-api.com` (solo para descargar resultados de consultas). Documentarlo junto a los
  demás hosts en README/HANDOFF.
- Tests existentes (61) siguen pasando; las piezas nuevas llevan tests con respuestas de la API simuladas (no se puede usar
  la red en los tests). Guardar como fixture el resultado real de las consultas sobre una partida con demo (p. ej. 135801973),
  que no contiene datos personales más allá de lo que ya hay en `match_109084310.json`.
- Interfaz en español. Carriles por nombre y color, nunca por lado.

## Enfoques

Para traer los datos del demo:

1. **Automático al guardar** (elegido por el usuario). Una cola en segundo plano en el servidor: al guardarse una partida se
   encola; un trabajador lanza las consultas, sondea, descarga, descomprime y guarda un resumen por partida. Respeta el
   límite (presupuesto por hora y espera tras 429), persiste el estado (pendiente / hecho / sin demo / error con reintento
   espaciado) y sobrevive a reinicios. El informe usa lo que haya.
2. Bajo demanda con un botón por partida: descartado por el usuario; el informe quedaría incompleto.

Para el rediseño: aplicar el estilo sobre el CSS y los componentes actuales (decisión del constructor; sin framework).

## Estilo "City Never Sleeps" (lo que se toma de la página)

- Fondo marrón muy oscuro y cálido con textura sutil; texto crema; acentos naranja quemado y turquesa.
- Titulares grandes con tipografía de cartel, gruesa y redondeada, con **una palabra destacada en etiqueta naranja**
  («Informe *rival*»).
- Retratos de héroe como **cartas ligeramente inclinadas** con borde, en fila.
- Pasos/secciones con **número en círculo turquesa** y línea discontinua que los une (índice del informe, cronología).
- Fotos/mapas en **marcos** con borde claro y sombra.
- Fuente de titulares: una fuente con licencia OFL guardada en `static/fonts/` (se puede subir al repositorio); no se usa la
  fuente de Valve ni se carga de fuera. Elección concreta: del constructor.
- Mantener legibilidad de tablas y gráficos (contraste AA), colores de carril y de equipo intactos, y modo impresión.

## Decisiones tomadas en la revisión (llamadas mías, el usuario puede corregirlas)

- **Robo de midboss:** es la definición del propio usuario aplicada a datos (inició = más daño; robado = lo mata quien no lo
  inició). Solo se muestra si se verifica el daño por equipo del demo. Si no, se muestran los hechos (quién lo mata, quién lo
  reclama según metadatos, reparto de rejuvenators) sin la palabra «robo».
- **Python:** la app sigue arrancando en versiones antiguas; sin `compression.zstd` (< 3.14) los datos del demo se muestran
  como «no disponible: requiere Python 3.14+» y el trabajador no se inicia. Los tests del demo se saltan en ese caso.
- **Presupuesto de consultas:** el endpoint de consultas del demo tiene su propio límite publicado (200/h por IP), distinto del
  de los demás endpoints; el trabajador lleva su propio presupuesto (p. ej. 150/h) y espera tras un 429. El actualizador no cambia.
- **Remontada:** regla del usuario: un equipo está en remontada cuando sus almas son < 90 % de las del rival
  (`almas_detrás < 0,9 × almas_delante`). Se describe en la interfaz como la regla del 10 %.

## Verificado al planificar (2026-11-12, partida 135801973)

- Tiempo de juego = `(tick − ticks en pausa) / 64`: cuadra con los dos midboss de los metadatos (1198 y 1642 s).
- Midboss = `DamageEvent.victim_class = 8`; equipo del atacante uniendo con `CCitadelPlayerPawn.m_iTeamNum`. Verificado: el
  daño al midboss por equipo **sí** se puede leer.
- `GoldHistoryEvent` viene vacío y `CurrencyChangedEvent` usa otra numeración de fuentes (39 códigos) sin documentar. Por eso la
  economía por minuto y la remontada se calculan con las muestras de los metadatos (`stats`, cada 3–5 min, con `gold_sources` y
  `net_worth`), no con el demo.

## Lo que queda al constructor

- Esquema de guardado (tabla nueva o JSON junto a la partida), forma del resumen por partida y número de consultas por
  partida (combinar en pocas consultas para ahorrar presupuesto).
- Calibración tick → segundo y verificación del daño al midboss (si no, quitarlo).
- Presentación concreta de cada bloque nuevo en Partidas e Informe, dentro del estilo.
- Qué partidas existentes se encolan al arrancar (todas las guardadas sin datos de demo, respetando el límite).
