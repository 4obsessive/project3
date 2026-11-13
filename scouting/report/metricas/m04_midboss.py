"""Midboss: cuándo, quién lo mata y quién lo reclama, kills en la ventana y diferencia de net worth."""
from collections import Counter

from .. import metric, stats
from ... import matches as M

REGLA = "net worth (interpolado de las muestras de la partida) < 0,9 × el del rival (regla del 10 %)"


@metric("midboss", "Midboss", order=40)
def midboss(ctx):
    win = int(ctx.params.get("midboss_window_s") or 90)
    events = []
    matches_with = 0
    first_by = Counter()
    for m in ctx.matches:
        mb = M.midboss(m.mi)
        if mb:
            matches_with += 1
            first_by[m.rel(mb[0]["team_killed"])] += 1
        for e in mb:
            t = e["t"]
            if t is None:  # sin segundo: nada que contar en la ventana (dato ausente, no 0)
                k_us = k_them = kill_adv = nw_adv = None
            else:
                dt = [d for d in m.deaths if d["t"] is not None]
                k_us = sum(1 for d in dt if d["killer_team"] == m.our and d["victim_team"] == m.their and t - win <= d["t"] <= t)
                k_them = sum(1 for d in dt if d["killer_team"] == m.their and d["victim_team"] == m.our and t - win <= d["t"] <= t)
                cum_us = sum(1 for d in dt if d["killer_team"] == m.our and d["victim_team"] == m.their and d["t"] <= t)
                cum_them = sum(1 for d in dt if d["killer_team"] == m.their and d["victim_team"] == m.our and d["t"] <= t)
                kill_adv = cum_us - cum_them
                nw_adv = round(M.team_networth_at(m.mi, m.our, t) - M.team_networth_at(m.mi, m.their, t))
            events.append({
                "match_id": m.id, "n": e["n"], "t": t, "killer": m.rel(e["team_killed"]), "claimer": m.rel(e["team_claimed"]),
                "kills_us": k_us, "kills_them": k_them, "kill_adv": kill_adv,
                "nw_adv": nw_adv, "won": m.won,
            })
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "text", "tone": "info",
               "text": f"Ventana de kills previas: {win} s. La diferencia de net worth es la de ese segundo (interpolada de las muestras cada pocos minutos)."}]
    if not events:
        blocks.append({"type": "text", "tone": "confirmed", "text": f"No hay Midboss en ninguna de las {n} partidas."})
        return blocks
    ours = [e for e in events if e["killer"] == "us"]
    theirs = [e for e in events if e["killer"] == "them"]
    blocks.append({"type": "text", "tone": "confirmed",
                   "text": f"Midboss en {matches_with} de {n} partidas ({len(events)} muertes del Midboss). Lo mata este equipo {len(ours)} veces y el rival {len(theirs)}. "
                           f"El primero de la partida: este equipo {first_by['us']}, rival {first_by['them']}."})
    rows = []
    for label, evs in (("Este equipo", ours), ("Rival", theirs), ("Primer Midboss de este equipo", [e for e in ours if e["n"] == 1]),
                       ("Primer Midboss del rival", [e for e in theirs if e["n"] == 1])):
        s = stats([e["t"] for e in evs])
        rows.append({"quien": label, "veces": len(evs), "media": s["mean"], "mediana": s["median"], "min": s["min"], "max": s["max"]})
    blocks.append({"type": "table", "title": "Minuto del Midboss", "n": n,
                   "columns": [{"key": "quien", "label": "Lo mata"}, {"key": "veces", "label": "Veces"}, {"key": "media", "label": "Media", "fmt": "mmss"},
                               {"key": "mediana", "label": "Mediana", "fmt": "mmss"}, {"key": "min", "label": "Mín.", "fmt": "mmss"}, {"key": "max", "label": "Máx.", "fmt": "mmss"}],
                   "rows": rows})
    blocks.append({"type": "histogram", "title": "Minuto del Midboss", "bin_s": 120, "n": n,
                   "series": [{"name": "Este equipo", "side": "us", "values": [e["t"] for e in ours if e["t"] is not None]},
                              {"name": "Rival", "side": "them", "values": [e["t"] for e in theirs if e["t"] is not None]}]})
    scen = []
    for label, evs in (("Cuando lo mata este equipo", ours), ("Cuando lo mata el rival", theirs)):
        if not evs:
            scen.append({"escenario": label, "veces": 0})
            continue
        scen.append({
            "escenario": label, "veces": len(evs),
            "kills_us": stats([e["kills_us"] for e in evs])["mean"], "kills_them": stats([e["kills_them"] for e in evs])["mean"],
            "kill_adv": stats([e["kill_adv"] for e in evs])["median"], "nw_adv": stats([e["nw_adv"] for e in evs])["median"],
            "ganadas": sum(1 for e in evs if e["won"]),
        })
    blocks.append({"type": "table", "title": "Escenarios (desde el punto de vista de este equipo)", "n": n,
                   "columns": [{"key": "escenario", "label": "Escenario"}, {"key": "veces", "label": "Veces"},
                               {"key": "kills_us", "label": f"Kills propias en {win}s (media)", "fmt": "1"},
                               {"key": "kills_them", "label": f"Kills rivales en {win}s (media)", "fmt": "1"},
                               {"key": "kill_adv", "label": "Ventaja de kills (mediana)", "fmt": "signed"},
                               {"key": "nw_adv", "label": "Ventaja net worth (mediana)", "fmt": "signed0"},
                               {"key": "ganadas", "label": "Partidas ganadas"}],
                   "rows": scen})
    blocks.append({"type": "table", "title": "Detalle", "n": n,
                   "columns": [{"key": "match_id", "label": "Partida"}, {"key": "n", "label": "#"}, {"key": "t", "label": "Minuto", "fmt": "mmss"},
                               {"key": "killer_txt", "label": "Lo mata"}, {"key": "claimer_txt", "label": "Lo reclama"},
                               {"key": "kills_us", "label": "Kills propias"}, {"key": "kills_them", "label": "Kills rival"},
                               {"key": "kill_adv", "label": "Ventaja kills", "fmt": "signed"}, {"key": "nw_adv", "label": "Ventaja NW", "fmt": "signed0"}],
                   "rows": [dict(e, killer_txt="Este equipo" if e["killer"] == "us" else "Rival",
                                 claimer_txt="Este equipo" if e["claimer"] == "us" else "Rival") for e in events]})
    blocks.extend(_demo_blocks(ctx))
    # patrones
    if n >= 3:
        if first_by["us"] / n >= 0.6:
            ctx.finding("strength", f"Se llevan el primer Midboss en {first_by['us']} de {n} partidas.", first_by["us"], n)
    return blocks


def _yn(v):
    return "—" if v is None else ("sí" if v else "no")


def _remontada(mi, t, team):
    """«sí»/«no» si el equipo `team` estaba en remontada en t; «—» si falta el equipo, el segundo o el net worth."""
    if team is None:
        return "—"
    cb = M.comeback_team_at(mi, t)
    return "—" if cb is None else _yn(cb == team)


def _demo_blocks(ctx):
    k = ctx.demo_n
    cov = ctx.demo_coverage()
    if not k:
        return [cov, {"type": "unavailable", "title": "Daño, rejuvenators y robos del Midboss (demo)",
                      "reason": "Ninguna partida analizada tiene datos del demo (pendiente, sin demo o con error)."}]
    rows = []
    taken_us = taken_them = steals_made = steals_suffered = 0
    for m in ctx.matches:
        d = m.demo
        if not d:
            continue
        for e in d.get("midboss") or []:
            dm, rj = e.get("damage") or {}, e.get("rejuv") or {}
            taken_us += rj.get(str(m.our), 0)
            taken_them += rj.get(str(m.their), 0)
            if e.get("stolen"):
                if e.get("killer") == m.our:
                    steals_made += 1
                elif e.get("killer") == m.their:
                    steals_suffered += 1
            kt = e.get("killer")
            rows.append({
                "match_id": m.id, "n": e.get("n"), "t": e.get("t"),
                "dano_nuestro": dm.get(str(m.our)), "dano_rival": dm.get(str(m.their)),
                "iniciador": {"us": "Este equipo", "them": "Rival"}.get(m.rel(e.get("initiator")), "—"),
                "robado": _yn(e.get("stolen")),
                "rejuv_nuestros": rj.get(str(m.our)), "rejuv_rival": rj.get(str(m.their)),
                "remontada": _remontada(m.mi, e.get("t"), kt),
            })
    out = [cov]
    if not rows:
        out.append({"type": "unavailable", "title": "Daño, rejuvenators y robos del Midboss (demo)",
                    "reason": "Los demos analizados no registran ninguna muerte del Midboss."})
        return out
    out.append({"type": "text", "tone": "info",
                "text": "Iniciador: el equipo que más daño hizo al Midboss. Robado: lo mata el equipo que no lo inició (solo si hay daño registrado). "
                        f"Remontada: el equipo que lo mata tenía {REGLA} en ese segundo; «—» si no hay muestras de net worth."})
    n_mb = len(rows)
    out.append({"type": "text", "tone": "confirmed",
                "text": f"Rejuvenators cogidos en {n_mb} Midboss: este equipo {taken_us} (media {taken_us / n_mb:.1f} por Midboss), rival {taken_them} (media {taken_them / n_mb:.1f}). "
                        f"Robos: este equipo {steals_made}, sufridos {steals_suffered}. "
                        f"Midboss muertos en remontada del que lo mata: {sum(1 for r in rows if r['remontada'] == 'sí')} de {n_mb}."})
    out.append({"type": "table", "title": "Midboss: daño, rejuvenators y robo (demo)", "n": k,
                "columns": [{"key": "match_id", "label": "Partida"}, {"key": "n", "label": "#"}, {"key": "t", "label": "Minuto", "fmt": "mmss"},
                            {"key": "dano_nuestro", "label": "Daño este equipo", "fmt": "int"}, {"key": "dano_rival", "label": "Daño rival", "fmt": "int"},
                            {"key": "iniciador", "label": "Lo inicia"}, {"key": "robado", "label": "Robado"},
                            {"key": "rejuv_nuestros", "label": "Rejuv. este equipo"}, {"key": "rejuv_rival", "label": "Rejuv. rival"},
                            {"key": "remontada", "label": "En remontada"}],
                "rows": rows})
    return out
