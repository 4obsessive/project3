"""Demo: resumen de Midboss, rejuvenators y KOTH a partir de las consultas SQL del demo (parte pura, sin red)."""
import bisect

TICK_RATE = 64
# El demo numera los equipos 2 y 3; la API de partidas usa 0 y 1.
TEAM_TO_API = {2: 0, 3: 1}
SUMMARY_VERSION = 1
# Ventana tras el último daño al Midboss en la que un rejuvenator cuenta como suyo.
KILL_WINDOW_S = 30
# Rejuvenators del mismo equipo separados menos de esto pertenecen al mismo Midboss.
CLUSTER_GAP_S = 60
# koth_give_up vale ~3.4e38 mientras el cash-in sigue abierto.
GIVE_UP_INFINITE = 1e30

QUERIES = {
    "rejuv": "SELECT tick, killing_team, user_team FROM RejuvStatusEvent WHERE event_type = 4 ORDER BY tick",
    "rules": "SELECT min(tick) AS tick, \"m_pGameRules__m_nKothScoringTeam\" AS koth_team, \"m_pGameRules__m_timeKothScoring\" AS koth_scoring, \"m_pGameRules__m_timeKothCashInStarted\" AS koth_start, \"m_pGameRules__m_timeKothGiveUp\" AS koth_give_up, \"m_pGameRules__m_nTotalPausedTicks\" AS paused_ticks, \"m_pGameRules__m_flGameStartTime\" AS game_start FROM CCitadelGameRulesProxy GROUP BY 2,3,4,5,6,7 ORDER BY 1",
    "midboss": "SELECT d.entindex_victim AS victim, p.team AS team, sum(d.damage) AS dmg, min(d.tick) AS t0, max(d.tick) AS t1 FROM DamageEvent d JOIN (SELECT DISTINCT entity_index, \"m_iTeamNum\" AS team FROM CCitadelPlayerPawn WHERE \"m_iTeamNum\" IS NOT NULL) p ON d.entindex_attacker = p.entity_index WHERE d.victim_class = 8 GROUP BY 1,2 ORDER BY 4",
}


def _fila_vigente(tick, rules):
    """Última fila de `rules` con tick <= el dado (o None). `rules` viene ordenado por tick."""
    ticks = [r["tick"] for r in rules]
    i = bisect.bisect_right(ticks, tick) - 1
    return rules[i] if i >= 0 else None


def game_seconds_from_tick(tick, rules):
    """Segundos de partida de un tick: (tick - ticks pausados vigentes) / 64."""
    fila = _fila_vigente(tick, rules)
    pausados = (fila or {}).get("paused_ticks") or 0
    return (tick - pausados) / TICK_RATE


def game_seconds_from_curtime(curtime, tick, rules):
    """Segundos de partida de un valor curtime (columnas koth_*) observado en `tick`."""
    fila = _fila_vigente(tick, rules)
    if fila is None:
        return float(curtime)
    return curtime - fila["game_start"] - (fila.get("paused_ticks") or 0) / TICK_RATE


def _api(team):
    return TEAM_TO_API.get(team)


def _cumulos_rejuv(rejuv):
    """Agrupa filas de rejuvenator por killing_team, con menos de 60 s entre filas consecutivas."""
    abiertos = {}
    cumulos = []
    for r in sorted(rejuv, key=lambda x: x["tick"]):
        team = r["killing_team"]
        c = abiertos.get(team)
        if c is None or r["tick"] - c["rows"][-1]["tick"] > CLUSTER_GAP_S * TICK_RATE:
            c = {"team": team, "rows": []}
            abiertos[team] = c
            cumulos.append(c)
        c["rows"].append(r)
    return cumulos


def _contar_rejuv(rows):
    """Rejuvenators por equipo del usuario (numeración API, claves string)."""
    cuenta = {"0": 0, "1": 0}
    for r in rows:
        t = _api(r["user_team"])
        if t is not None:
            cuenta[str(t)] += 1
    return cuenta


def _midboss(results, rules):
    entidades = {}
    for r in results.get("midboss") or []:
        e = entidades.setdefault(r["victim"], {"filas": [], "t1": 0})
        e["filas"].append(r)
        e["t1"] = max(e["t1"], r["t1"])
    lista = []
    for e in entidades.values():
        dmg = {"0": 0, "1": 0}
        con_dano = [f for f in e["filas"] if f["dmg"] > 0 and _api(f["team"]) is not None]
        for f in con_dano:
            dmg[str(_api(f["team"]))] += f["dmg"]
        inicia = min(con_dano, key=lambda f: f["t0"]) if con_dano else None
        lista.append({"t_tick": e["t1"], "damage": dmg,
                      "initiator": _api(inicia["team"]) if inicia else None,
                      "killer": None, "rejuv_rows": []})
    lista.sort(key=lambda x: x["t_tick"])

    sueltos = []
    for c in _cumulos_rejuv(results.get("rejuv") or []):
        primero = c["rows"][0]["tick"]
        # Entidad más reciente cuyo último daño cae en los 30 s previos al cúmulo.
        destino = None
        for e in lista:
            if 0 <= primero - e["t_tick"] <= KILL_WINDOW_S * TICK_RATE:
                destino = e
        if destino is None:
            sueltos.append({"t_tick": primero, "damage": {"0": 0, "1": 0}, "initiator": None,
                            "killer": _api(c["team"]), "rejuv_rows": c["rows"]})
        else:
            destino["rejuv_rows"].extend(c["rows"])
            destino["killer"] = _api(c["team"])

    # Sin daño en ningún equipo y sin rejuvenators: no es un Midboss real.
    entradas = [e for e in lista if sum(e["damage"].values()) > 0 or e["rejuv_rows"]] + sueltos
    entradas.sort(key=lambda x: x["t_tick"])

    salida = []
    for n, e in enumerate(entradas, 1):
        ini, kil = e["initiator"], e["killer"]
        salida.append({
            "n": n,
            "t": round(game_seconds_from_tick(e["t_tick"], rules)),
            "damage": e["damage"],
            "initiator": ini,
            "killer": kil,
            "stolen": (kil != ini) if ini is not None and kil is not None else None,
            "rejuv": _contar_rejuv(e["rejuv_rows"]),
        })
    return salida


def _koth(rules):
    # Un cash-in = cada koth_start > 0 distinto con koth_give_up finito; se guarda la primera fila en que aparece.
    inicios = []
    vistos = set()
    for r in rules:
        s = r["koth_start"]
        if s > 0 and r["koth_give_up"] < GIVE_UP_INFINITE and s not in vistos:
            vistos.add(s)
            inicios.append(r)
    salida = []
    for n, ini in enumerate(inicios, 1):
        limite = inicios[n]["tick"] if n < len(inicios) else None
        hecho = None
        for r in rules:
            if r["tick"] < ini["tick"]:
                continue
            if limite is not None and r["tick"] >= limite:
                break
            if r["koth_team"] in TEAM_TO_API and r["koth_scoring"] >= ini["koth_start"]:
                hecho = r
                break
        salida.append({
            "n": n,
            "start_t": round(game_seconds_from_curtime(ini["koth_start"], ini["tick"], rules)),
            "completed_by": _api(hecho["koth_team"]) if hecho else None,
            "completed_t": round(game_seconds_from_curtime(hecho["koth_scoring"], hecho["tick"], rules))
            if hecho else None,
        })
    return salida


def summarize(results):
    """Resume los resultados de las consultas del demo en un dict serializable a JSON."""
    rules = sorted(results.get("rules") or [], key=lambda r: r["tick"])
    return {"version": SUMMARY_VERSION, "midboss": _midboss(results, rules), "koth": _koth(rules)}
