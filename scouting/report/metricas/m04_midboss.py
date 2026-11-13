"""Midboss: cuándo, quién lo mata y quién lo reclama, kills en la ventana y diferencia de net worth."""
from collections import Counter

from .. import metric, stats
from ... import matches as M


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
            t = e["t"] or 0
            k_us = sum(1 for d in m.deaths if d["killer_team"] == m.our and d["victim_team"] == m.their and t - win <= (d["t"] or 0) <= t)
            k_them = sum(1 for d in m.deaths if d["killer_team"] == m.their and d["victim_team"] == m.our and t - win <= (d["t"] or 0) <= t)
            cum_us = sum(1 for d in m.deaths if d["killer_team"] == m.our and d["victim_team"] == m.their and (d["t"] or 0) <= t)
            cum_them = sum(1 for d in m.deaths if d["killer_team"] == m.their and d["victim_team"] == m.our and (d["t"] or 0) <= t)
            nw = M.team_networth_at(m.mi, m.our, t) - M.team_networth_at(m.mi, m.their, t)
            events.append({
                "match_id": m.id, "n": e["n"], "t": t, "killer": m.rel(e["team_killed"]), "claimer": m.rel(e["team_claimed"]),
                "kills_us": k_us, "kills_them": k_them, "kill_adv": cum_us - cum_them,
                "nw_adv": round(nw), "won": m.won,
            })
    n = ctx.n
    blocks = [ctx.sample_warning(),
              {"type": "unavailable", "title": "Cristales del Midboss, quién lo inicia e intentos fallidos",
               "reason": "La API no registra estos datos: solo da quién lo mató, quién lo reclamó y el segundo."},
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
                   "series": [{"name": "Este equipo", "side": "us", "values": [e["t"] for e in ours]}, {"name": "Rival", "side": "them", "values": [e["t"] for e in theirs]}]})
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
    # patrones
    if n >= 3:
        if first_by["us"] / n >= 0.6:
            ctx.finding("strength", f"Se llevan el primer Midboss en {first_by['us']} de {n} partidas.", first_by["us"], n)
    return blocks
